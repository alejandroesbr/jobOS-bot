from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.scrapers.browser import (
    DEFAULT_USER_AGENT,
    DEFAULT_VIEWPORT,
    create_browser_session,
)
from src.config_loader import load_candidate_profile
from src.domain.models import AnswerSource, ApplicationStatus, QuestionCategory
from src.domain.qa_engine import QuestionAnswerEngine
from src.domain.text_normalizer import normalize_form_question
from src.ui.console import console, print_banner, print_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FieldAssistResult:
    label: str
    filled_value: str
    is_confident: bool
    source: str


@dataclass(frozen=True, slots=True)
class AssistReport:
    url: str
    total_fields: int
    confident_fields: int
    suggested_fields: int
    saved_answers: int


class AssistService:
    def __init__(
        self,
        repository: ApplicationRepository,
        qa_engine: QuestionAnswerEngine | None = None,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self.repository = repository
        self.gemini_client = gemini_client or GeminiClient()

        if qa_engine is not None:
            self.qa_engine = qa_engine
        else:
            profile = load_candidate_profile()
            self.qa_engine = QuestionAnswerEngine(profile=profile, repository=repository)

    def _find_candidate_cv_pdf(self) -> Path | None:
        for p in [
            Path("config/CV_Ancizar_Escobar.pdf"),
            Path("config/cv.pdf"),
            Path("data/cv.pdf"),
        ]:
            if p.is_file():
                return p
        for p in Path("config").glob("*.pdf"):
            if p.is_file():
                return p
        return None

    def _open_easy_apply_if_present(self, page: Page) -> bool:
        selectors = [
            "button.jobs-apply-button",
            "button:has-text('Solicitud sencilla')",
            "button:has-text('Easy Apply')",
            "button[aria-label*='Solicitud sencilla']",
            "button[aria-label*='Easy Apply']",
            ".jobs-apply-button--top-card button",
            "[data-job-id] button.jobs-apply-button",
            "button:has-text('Postularme')",
            ".jobs-s-apply button",
        ]
        for sel in selectors:
            loc = page.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=4000)
                loc.click()
                console.print("[bold green]✓ Clic automático en 'Solicitud sencilla'. Abriendo formulario...[/bold green]")
                page.wait_for_timeout(2500)
                return True
            except Exception:
                continue
        return False

    def _handle_easy_apply_modal(
        self,
        page: Page,
        cv_pdf: Path | None,
        auto_submit: bool = False,
    ) -> list[FieldAssistResult]:
        field_results: list[FieldAssistResult] = []
        max_steps = 8
        step = 0

        while step < max_steps:
            step += 1
            modal = page.locator("div.jobs-easy-apply-modal, div[role='dialog']").first
            try:
                modal.wait_for(state="visible", timeout=3000)
            except Exception:
                break

            console.print(f"[dim]Completando paso {step} del formulario...[/dim]")

            # 1. Adjuntar o seleccionar CV si hay campo de archivo
            if cv_pdf:
                file_inputs = modal.locator("input[type='file']").all()
                for file_el in file_inputs:
                    try:
                        file_el.set_input_files(str(cv_pdf.resolve()))
                        console.print(f"[bold green]✓ CV adjuntado automáticamente:[/bold green] [cyan]{cv_pdf.name}[/cyan]")
                        field_results.append(
                            FieldAssistResult("Archivo CV / Resume", cv_pdf.name, is_confident=True, source="cv_pdf_upload")
                        )
                    except Exception as ex:
                        logger.debug("No se pudo adjuntar CV: %s", ex)

            # 2. Rellenar inputs de texto / número / tel / email
            inputs = modal.locator("input:visible, textarea:visible").all()
            for field_el in inputs:
                field_type = field_el.get_attribute("type") or "text"
                if field_type in {"hidden", "submit", "button", "checkbox", "radio", "file"}:
                    continue

                try:
                    current_val = field_el.input_value()
                    if current_val and current_val.strip():
                        continue
                except Exception:
                    pass

                label_text = self._extract_field_label(field_el, page)
                if not label_text:
                    continue

                is_numeric = field_type in {"number", "tel"}
                match = self.qa_engine.find_answer(label_text, is_numeric_input=is_numeric)

                if match.is_confident_match and match.answer:
                    try:
                        field_el.fill(match.answer)
                        field_el.evaluate(
                            "el => { el.style.border = '2px solid #10b981'; el.style.boxShadow = '0 0 6px #10b981'; }"
                        )
                        field_results.append(
                            FieldAssistResult(label_text, match.answer, is_confident=True, source=match.source.value)
                        )
                    except Exception:
                        pass
                else:
                    profile_ctx = str(self.qa_engine.profile) if self.qa_engine.profile else ""
                    suggested = self.gemini_client.generate_qa_fallback(label_text, field_type, profile_ctx)
                    try:
                        field_el.fill(suggested)
                        field_el.evaluate(
                            "el => { el.style.border = '2px solid #f59e0b'; el.style.boxShadow = '0 0 8px #f59e0b'; }"
                        )
                        field_results.append(
                            FieldAssistResult(label_text, suggested, is_confident=False, source="gemini_fallback")
                        )
                    except Exception:
                        pass

            # 3. Preguntas de Selección Única / Radio (Sí / No, Permisos, etc.)
            fieldsets = modal.locator("fieldset").all()
            for fs in fieldsets:
                try:
                    legend_el = fs.locator("legend").first
                    legend_text = legend_el.inner_text().strip().lower() if legend_el.is_visible() else ""
                    if not legend_text:
                        continue

                    # Regla ATS: Patrocinio de visa = No, Autorización/Residencia/Legalidad = Sí
                    is_visa_sponsor = any(k in legend_text for k in ["patrocinio", "visa", "sponsor"])
                    target_choice = "No" if is_visa_sponsor else "Sí"

                    radio_label = fs.locator(
                        f"label:has-text('{target_choice}'), label:has-text('{target_choice.lower()}'), label:has-text('Yes' if '{target_choice}' == 'Sí' else 'No')"
                    ).first
                    if radio_label.is_visible():
                        radio_label.click()
                        field_results.append(
                            FieldAssistResult(legend_text[:40], target_choice, is_confident=True, source="rules_ats")
                        )
                except Exception:
                    pass

            # 4. Selectores desplegables (<select>)
            selects = modal.locator("select:visible").all()
            for sel_el in selects:
                try:
                    options = sel_el.locator("option").all()
                    for opt in options:
                        opt_text = opt.inner_text().lower()
                        if "colombia" in opt_text or "+57" in opt_text:
                            sel_el.select_option(value=opt.get_attribute("value") or "")
                            break
                        elif "sí" in opt_text or "yes" in opt_text:
                            sel_el.select_option(value=opt.get_attribute("value") or "")
                            break
                except Exception:
                    pass

            page.wait_for_timeout(800)

            # 5. Navegación del Wizard
            # Si estamos en el paso final con botón 'Enviar solicitud'
            submit_btn = modal.locator(
                "button:has-text('Enviar solicitud'), button:has-text('Submit application'), button[aria-label*='Enviar solicitud']"
            ).first
            if submit_btn.is_visible():
                console.print("[bold green]✓ Todos los pasos completados y CV adjuntado.[/bold green]")
                if auto_submit:
                    submit_btn.click()
                    console.print("[bold green]✓ Clic automático en 'Enviar solicitud' realizado.[/bold green]")
                    page.wait_for_timeout(2500)
                else:
                    console.print("[bold yellow]Paso final: Revisa y haz clic en 'Enviar solicitud' en el navegador.[/bold yellow]")
                break

            # Si hay botón 'Revisar' (Review)
            review_btn = modal.locator("button:has-text('Revisar'), button:has-text('Review')").first
            if review_btn.is_visible():
                review_btn.click()
                page.wait_for_timeout(1500)
                continue

            # Si hay botón 'Siguiente' (Next)
            next_btn = modal.locator(
                "button:has-text('Siguiente'), button:has-text('Next'), button[aria-label*='siguiente']"
            ).first
            if next_btn.is_visible():
                next_btn.click()
                page.wait_for_timeout(1500)
                continue

            break

        return field_results

    def _fill_standard_form(
        self,
        page: Page,
        cv_pdf: Path | None,
    ) -> list[FieldAssistResult]:
        field_results: list[FieldAssistResult] = []

        # 1. Adjuntar CV si hay campo de archivo
        if cv_pdf:
            try:
                file_inputs = page.locator("input[type='file']").all()
                for file_el in file_inputs:
                    try:
                        file_el.set_input_files(str(cv_pdf.resolve()))
                        console.print(f"[bold green]✓ CV adjuntado automáticamente:[/bold green] [cyan]{cv_pdf.name}[/cyan]")
                        field_results.append(
                            FieldAssistResult("Archivo CV / Resume", cv_pdf.name, is_confident=True, source="cv_pdf_upload")
                        )
                    except Exception as ex:
                        logger.debug("No se pudo adjuntar CV: %s", ex)
            except Exception as ex:
                logger.debug("Error al buscar inputs file: %s", ex)

        # 2. Descubrir y rellenar inputs de texto/número
        inputs = page.locator("input:visible, textarea:visible, select:visible").all()
        for field_el in inputs:
            field_type = field_el.get_attribute("type") or "text"
            if field_type in {"hidden", "submit", "button", "checkbox", "radio", "file"}:
                continue

            label_text = self._extract_field_label(field_el, page)
            if not label_text:
                continue

            is_numeric = field_type in {"number", "tel"}
            match = self.qa_engine.find_answer(label_text, is_numeric_input=is_numeric)

            if match.is_confident_match and match.answer:
                try:
                    field_el.fill(match.answer)
                    field_el.evaluate(
                        "el => { el.style.border = '2px solid #10b981'; el.style.boxShadow = '0 0 6px #10b981'; }"
                    )
                    field_results.append(
                        FieldAssistResult(label_text, match.answer, is_confident=True, source=match.source.value)
                    )
                except Exception:
                    pass
            else:
                profile_ctx = str(self.qa_engine.profile) if self.qa_engine.profile else ""
                suggested = self.gemini_client.generate_qa_fallback(label_text, field_type, profile_ctx)
                try:
                    field_el.fill(suggested)
                    field_el.evaluate(
                        "el => { el.style.border = '2px solid #f59e0b'; el.style.boxShadow = '0 0 8px #f59e0b'; }"
                    )
                    field_results.append(
                        FieldAssistResult(label_text, suggested, is_confident=False, source="gemini_fallback")
                    )
                except Exception:
                    pass

        return field_results

    def run_assist(
        self,
        url: str,
        application_id: int | None = None,
        auto_submit: bool = False,
    ) -> AssistReport:
        subtitle = f"Vacante #{application_id} | URL: {url}" if application_id else f"URL: {url}"
        print_banner("jobOS-bot — Copiloto Human-in-the-Loop", subtitle)

        storage_state = Path("data/storage_state.json")
        user_dir = Path("data/browser_profile")

        with create_browser_session(
            headless=False,
            user_data_dir=user_dir,
            storage_state_path=storage_state if storage_state.is_file() else None,
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)
            except Exception as ex:
                print_error(f"No se pudo cargar la URL: {ex}")
                return AssistReport(url, 0, 0, 0, 0)

            cv_pdf = self._find_candidate_cv_pdf()

            # Detectar y desplegar modal de Solicitud Rápida / Easy Apply si existe
            modal_opened = self._open_easy_apply_if_present(page)
            modal_loc = page.locator("div.jobs-easy-apply-modal, div[role='dialog']").first

            is_modal_active = modal_opened
            if not is_modal_active:
                try:
                    modal_loc.wait_for(state="visible", timeout=2000)
                    is_modal_active = True
                except Exception:
                    is_modal_active = False

            if is_modal_active:
                field_results = self._handle_easy_apply_modal(page, cv_pdf, auto_submit=auto_submit)
            else:
                field_results = self._fill_standard_form(page, cv_pdf)

            confident_count = sum(1 for f in field_results if f.is_confident)
            suggested_count = len(field_results) - confident_count

            console.print(f"\n[green]Campos reconocidos con memoria local: {confident_count}[/green]")
            if suggested_count > 0:
                console.print(f"[bold yellow]Campos sugeridos con IA (Borde Amarillo): {suggested_count}[/bold yellow]")
                console.print("[yellow]Por favor revisa y edita los campos en amarillo en el navegador antes de enviar.[/yellow]")

            console.print("\n[bold cyan]Presiona ENTER en esta terminal una vez hayas enviado el formulario para memorizar tus respuestas...[/bold cyan]")
            try:
                input()
            except EOFError:
                pass

            # Continuous learning: read user answers and persist
            saved_answers = 0
            for f in field_results:
                if not f.is_confident and f.filled_value:
                    self.repository.upsert_qa_memory(
                        question_norm=normalize_form_question(f.label),
                        raw_example=f.label,
                        answer=f.filled_value,
                        category=QuestionCategory.GENERAL,
                        source=AnswerSource.USER_CONFIRMED,
                    )
                    saved_answers += 1

            if application_id is not None:
                self.repository.update_status(application_id, ApplicationStatus.APPLIED)
                console.print(f"[bold green]✓ Vacante #{application_id} actualizada a estado '{ApplicationStatus.APPLIED.value}'.[/bold green]")

            return AssistReport(
                url=url,
                total_fields=len(field_results),
                confident_fields=confident_count,
                suggested_fields=suggested_count,
                saved_answers=saved_answers,
            )

    def _extract_field_label(self, element: Any, page: Page) -> str:
        # Check aria-label
        aria = element.get_attribute("aria-label")
        if aria and str(aria).strip():
            return str(aria).strip()

        # Check placeholder
        placeholder = element.get_attribute("placeholder")
        if placeholder and str(placeholder).strip():
            return str(placeholder).strip()

        # Check name or id
        elem_id = element.get_attribute("id")
        if elem_id:
            label_for = page.locator(f"label[for='{elem_id}']").first
            if label_for.count():
                return label_for.inner_text().strip()

        name = element.get_attribute("name")
        if name:
            return str(name).replace("_", " ").replace("-", " ").strip()

        return ""
