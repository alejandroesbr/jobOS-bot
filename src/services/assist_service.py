from dataclasses import dataclass
import logging
from pathlib import Path
import re
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
from src.domain.models import AnswerSource, ApplicationStatus, PortalName, QuestionCategory
from src.domain.qa_engine import QuestionAnswerEngine, SALARY_INTENT_PATTERN
from src.domain.text_normalizer import normalize_form_question
from src.ui.console import console, print_banner, print_error

logger = logging.getLogger(__name__)

EXCLUDED_INPUT_TYPES = {
    "hidden",
    "submit",
    "button",
    "checkbox",
    "radio",
    "file",
    "password",
    "search",
    "reset",
}


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
        """Busca el archivo de currículum en formato PDF en rutas estándar sin nombres propios en código."""
        candidates = [
            Path("config/cv.pdf"),
            Path("data/cv.pdf"),
            Path("cv.pdf"),
        ]
        for p in candidates:
            if p.is_file():
                return p
        for p in Path("config").glob("*.pdf"):
            if p.is_file():
                return p
        for p in Path("data").glob("*.pdf"):
            if p.is_file():
                return p
        return None

    def _is_nav_or_search_element(self, element: Any) -> bool:
        """Verifica si un elemento pertenece a la cabecera, navegación o buscador global de la página."""
        try:
            return bool(
                element.evaluate(
                    """el => {
                        return el.closest('header, nav, [role="search"], [role="navigation"], .global-nav, .jobs-search-box') !== null;
                    }"""
                )
            )
        except Exception:
            return False

    def _build_safe_context_for_prompt(self, question: str) -> str:
        """Construye un contexto seguro para el fallback de Gemini.

        Protege datos personales (email, teléfono, dirección, salarios) salvo que la pregunta
        los requiera explícitamente.
        """
        profile = self.qa_engine.profile
        if not profile:
            return ""

        q_lower = question.lower()
        context_parts: list[str] = []

        if profile.experience_years:
            skills_str = ", ".join(f"{tech}: {years} años" for tech, years in profile.experience_years.items())
            context_parts.append(f"Años de experiencia por tecnología: {skills_str}")

        if profile.preferences:
            context_parts.append(f"Nivel de inglés: {profile.preferences.english_level}")
            context_parts.append(f"Disponibilidad de inicio: {profile.preferences.notice_period}")

        if SALARY_INTENT_PATTERN.search(q_lower):
            if "usd" in q_lower or "dolar" in q_lower or "dollar" in q_lower:
                context_parts.append(f"Aspiración salarial USD: ${profile.salary.usd_monthly} USD/mes")
            else:
                context_parts.append(f"Aspiración salarial COP: ${profile.salary.cop_monthly:,} COP/mes")

        if any(term in q_lower for term in ["ciudad", "pais", "país", "ubicacion", "ubicación", "residencia", "city", "country", "location"]):
            context_parts.append(f"Ubicación actual: {profile.personal.city}, {profile.personal.country}")

        return "\n".join(context_parts)

    def _detect_closed_or_expired(self, page: Page) -> tuple[bool, str]:
        """Detecta si la vacante fue cerrada, expiró o ya no acepta solicitudes en el portal."""
        closed_signals = [
            ("span:has-text('Ya no se aceptan solicitudes')", "Ya no se aceptan solicitudes"),
            ("div:has-text('Ya no se aceptan solicitudes')", "Ya no se aceptan solicitudes"),
            ("p:has-text('Ya no se aceptan solicitudes')", "Ya no se aceptan solicitudes"),
            ("span:has-text('No longer accepting applications')", "No longer accepting applications"),
            ("div:has-text('No longer accepting applications')", "No longer accepting applications"),
            (".jobs-details__top-card--closed", "Vacante cerrada en LinkedIn"),
            (":has-text('Esta oferta ya no está disponible')", "Oferta ya no disponible"),
            (":has-text('Esta oferta ha finalizado')", "Oferta finalizada"),
            (":has-text('Esta vacante ha expirado')", "Vacante expirada"),
            (":has-text('Esta búsqueda ha finalizado')", "Búsqueda finalizada"),
            (":has-text('This job is no longer available')", "Job no longer available"),
        ]
        for sel, label in closed_signals:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    return True, label
            except Exception:
                pass
        return False, ""

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
                try:
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
                except Exception:
                    pass

            # 2. Rellenar inputs de texto / número / tel / email
            inputs = modal.locator("input:visible, textarea:visible").all()
            for field_el in inputs:
                field_type = field_el.get_attribute("type") or "text"
                if field_type in EXCLUDED_INPUT_TYPES or self._is_nav_or_search_element(field_el):
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
                    safe_ctx = self._build_safe_context_for_prompt(label_text)
                    try:
                        suggested = self.gemini_client.generate_qa_fallback(label_text, field_type, safe_ctx)
                    except Exception:
                        suggested = ""

                    if suggested:
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

            # 3. Preguntas de Selección Única / Radio
            fieldsets = modal.locator("fieldset").all()
            for fs in fieldsets:
                try:
                    legend_el = fs.locator("legend").first
                    if not legend_el.is_visible():
                        continue
                    legend_text = legend_el.inner_text().strip()
                    if not legend_text:
                        continue

                    qa_match = self.qa_engine.find_answer(legend_text)
                    if not qa_match.is_confident_match or not qa_match.answer:
                        console.print(f"[yellow]ℹ Pregunta de opción única sin respuesta segura: '{legend_text[:50]}...'. Dejada sin marcar para revisión.[/yellow]")
                        continue

                    target_answer = qa_match.answer.strip().lower()
                    labels = fs.locator("label").all()
                    clicked = False
                    for lbl in labels:
                        lbl_text = lbl.inner_text().strip().lower()
                        if target_answer in {"sí", "si", "yes"}:
                            if lbl_text in {"sí", "si", "yes", "true"} or lbl_text.startswith("sí") or lbl_text.startswith("yes"):
                                lbl.click()
                                clicked = True
                                break
                        elif target_answer in {"no", "false"}:
                            if lbl_text in {"no", "false"} or lbl_text.startswith("no"):
                                lbl.click()
                                clicked = True
                                break
                        elif target_answer == lbl_text or target_answer in lbl_text:
                            lbl.click()
                            clicked = True
                            break

                    if clicked:
                        field_results.append(
                            FieldAssistResult(legend_text[:40], qa_match.answer, is_confident=True, source=qa_match.source.value)
                        )
                except Exception as ex:
                    logger.debug("Error procesando radio fieldset: %s", ex)

            # 4. Selectores desplegables (<select>)
            selects = modal.locator("select:visible").all()
            for sel_el in selects:
                if self._is_nav_or_search_element(sel_el):
                    continue
                try:
                    label_text = self._extract_field_label(sel_el, page)
                    is_country_or_phone = any(
                        term in label_text.lower() for term in ["pais", "país", "country", "código", "codigo", "phone code"]
                    )
                    options = sel_el.locator("option").all()

                    if is_country_or_phone:
                        for opt in options:
                            opt_text = opt.inner_text().strip().lower()
                            if "colombia" in opt_text or "+57" in opt_text:
                                sel_el.select_option(value=opt.get_attribute("value") or opt.inner_text())
                                field_results.append(
                                    FieldAssistResult(label_text or "Country/Phone Code", "Colombia (+57)", is_confident=True, source="rules_ats")
                                )
                                break
                    elif label_text:
                        qa_match = self.qa_engine.find_answer(label_text)
                        if qa_match.is_confident_match and qa_match.answer:
                            target_val = qa_match.answer.strip().lower()
                            for opt in options:
                                opt_text = opt.inner_text().strip().lower()
                                if target_val == opt_text or target_val in opt_text:
                                    sel_el.select_option(value=opt.get_attribute("value") or opt.inner_text())
                                    field_results.append(
                                        FieldAssistResult(label_text, qa_match.answer, is_confident=True, source=qa_match.source.value)
                                    )
                                    break
                except Exception as ex:
                    logger.debug("Error procesando select: %s", ex)

            page.wait_for_timeout(800)

            # 5. Navegación del Wizard
            submit_btn = modal.locator(
                "button:has-text('Enviar solicitud'), button:has-text('Submit application'), button[aria-label*='Enviar solicitud']"
            ).first
            if submit_btn.is_visible():
                # Regla del proyecto: el bot nunca hace clic en enviar; la revisión final es humana.
                console.print("[bold green]✓ Todos los pasos completados.[/bold green]")
                console.print("[bold yellow]Paso final: Revisa y haz clic en 'Enviar solicitud' en el navegador.[/bold yellow]")
                break

            review_btn = modal.locator("button:has-text('Revisar'), button:has-text('Review')").first
            if review_btn.is_visible():
                review_btn.click()
                page.wait_for_timeout(1500)
                continue

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

        inputs = page.locator("input:visible, textarea:visible, select:visible").all()
        for field_el in inputs:
            field_type = field_el.get_attribute("type") or "text"
            if field_type in EXCLUDED_INPUT_TYPES or self._is_nav_or_search_element(field_el):
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
                safe_ctx = self._build_safe_context_for_prompt(label_text)
                try:
                    suggested = self.gemini_client.generate_qa_fallback(label_text, field_type, safe_ctx)
                except Exception:
                    suggested = ""

                if suggested:
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
        headless: bool = False,
    ) -> AssistReport:
        subtitle = f"Vacante #{application_id} | URL: {url}" if application_id else f"URL: {url}"
        print_banner("jobOS-bot — Copiloto Human-in-the-Loop", subtitle)

        storage_state = Path("data/storage_state.json")
        user_dir = Path("data/browser_profile")

        with create_browser_session(
            headless=headless,
            user_data_dir=user_dir,
            storage_state_path=storage_state if storage_state.is_file() else None,
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2000)
            except Exception as ex:
                if "ERR_TOO_MANY_REDIRECTS" in str(ex):
                    console.print("\n[bold yellow]⚠ Bucle de redirecciones detectado en LinkedIn (ERR_TOO_MANY_REDIRECTS).[/bold yellow]")
                    console.print("[dim]Limpiando cookies de sesión en conflicto y reintentando navegación limpia...[/dim]")
                    try:
                        context.clear_cookies()
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(2000)
                    except Exception as retry_ex:
                        if "Target page, context or browser has been closed" in str(retry_ex):
                            console.print("[yellow]Ventana del navegador cerrada por el usuario.[/yellow]")
                            return AssistReport(url, 0, 0, 0, 0)
                        print_error(f"No se pudo cargar la URL tras limpiar cookies: {retry_ex}")
                        return AssistReport(url, 0, 0, 0, 0)
                elif "Target page, context or browser has been closed" in str(ex):
                    console.print("[yellow]Ventana del navegador cerrada por el usuario.[/yellow]")
                    return AssistReport(url, 0, 0, 0, 0)
                else:
                    print_error(f"No se pudo cargar la URL: {ex}")
                    return AssistReport(url, 0, 0, 0, 0)

            # Detectar si LinkedIn redirigió a pantalla de inicio de sesión o authwall
            try:
                is_auth_needed = (
                    "/login" in page.url
                    or "/authwall" in page.url
                    or "/checkpoint/" in page.url
                    or page.locator("input#username, input#session_key").count() > 0
                )
            except Exception:
                is_auth_needed = False

            if is_auth_needed:
                console.print("\n[bold yellow]⚠ LinkedIn solicita inicio de sesión en el navegador:[/bold yellow]")
                console.print("[cyan]Por favor inicia sesión con tu cuenta en la ventana que está abierta.[/cyan]")
                console.print("[dim]jobOS-bot detectará tu ingreso, guardará tus cookies y continuará automáticamente...[/dim]\n")

                logged_in = False
                for _ in range(60):
                    page.wait_for_timeout(2000)
                    try:
                        if "/login" not in page.url and "/authwall" not in page.url and "/checkpoint/" not in page.url:
                            logged_in = True
                            break
                    except Exception:
                        break

                if logged_in:
                    console.print("[bold green]✓ ¡Sesión iniciada con éxito! Actualizando cookies de sesión...[/bold green]")
                    try:
                        context.storage_state(path=str(storage_state))
                    except Exception:
                        pass
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass
                else:
                    console.print("[yellow]No se completó el inicio de sesión o la ventana fue cerrada. Postulación pausada.[/yellow]")
                    return AssistReport(url, 0, 0, 0, 0)

            # Validar si la vacante fue cerrada o ya no acepta solicitudes
            is_closed, closed_reason = self._detect_closed_or_expired(page)
            if is_closed:
                console.print(f"\n[bold yellow]⚠ Oferta no disponible:[/bold yellow] [bold red]{closed_reason}[/bold red]")
                if application_id is not None:
                    self.repository.update_status(application_id, ApplicationStatus.DISCARDED)
                    console.print(
                        f"[dim]✓ Vacante #{application_id} marcada como '{ApplicationStatus.DISCARDED.value}' en la base de datos para sacarla de la cola.[/dim]\n"
                    )
                return AssistReport(url, 0, 0, 0, 0)

            cv_pdf = self._find_candidate_cv_pdf()

            try:
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
                    field_results = self._handle_easy_apply_modal(page, cv_pdf)
                else:
                    field_results = self._fill_standard_form(page, cv_pdf)
            except Exception as ex:
                if "Target page, context or browser has been closed" in str(ex):
                    console.print("[yellow]Ventana del navegador cerrada por el usuario. Postulación pausada.[/yellow]")
                    return AssistReport(url, 0, 0, 0, 0)
                raise

            confident_count = sum(1 for f in field_results if f.is_confident)
            suggested_count = len(field_results) - confident_count

            console.print(f"\n[green]Campos reconocidos con memoria local: {confident_count}[/green]")
            if suggested_count > 0:
                console.print(f"[bold yellow]Campos sugeridos con IA (Borde Amarillo): {suggested_count}[/bold yellow]")
                console.print("[yellow]Por favor revisa y edita los campos en amarillo en el navegador antes de enviar.[/yellow]")

            user_confirmed_sent = self._ask_yes_no("¿Enviaste la postulación en el navegador? [s/N]: ")

            saved_answers = 0
            if user_confirmed_sent:
                saved_answers = self._save_confirmed_suggestions(field_results)

                if application_id is not None:
                    rec = self.repository.find_by_id(application_id)
                    portal = rec.portal if (rec and rec.portal) else PortalName.LINKEDIN
                    self.repository.mark_applied(
                        application_id=application_id,
                        portal=portal,
                        canonical_url=url,
                    )
                    console.print(f"[bold green]✓ Vacante #{application_id} registrada como '{ApplicationStatus.APPLIED.value}'.[/bold green]")
            else:
                console.print("[yellow]Postulación no marcada como enviada. Permanecerá en estado 'Pendiente'.[/yellow]")

            return AssistReport(
                url=url,
                total_fields=len(field_results),
                confident_fields=confident_count,
                suggested_fields=suggested_count,
                saved_answers=saved_answers,
            )

    def _ask_yes_no(self, prompt: str) -> bool:
        """Pregunta en la terminal; cualquier respuesta distinta de 'sí' (incluido ENTER o EOF) cuenta como no."""
        console.print(f"\n[bold cyan]{prompt}[/bold cyan]", end="")
        try:
            return input().strip().lower() in {"s", "si", "sí", "y", "yes"}
        except EOFError:
            return False

    def _save_confirmed_suggestions(self, field_results: list[FieldAssistResult]) -> int:
        """Guarda en memoria solo las respuestas de IA que el usuario confirma o corrige en la terminal."""
        saved = 0
        for f in field_results:
            if f.is_confident or not f.filled_value:
                continue
            norm_q = normalize_form_question(f.label)
            if not norm_q:
                continue
            console.print(
                f"\n[yellow]Pregunta:[/yellow] {f.label}\n[yellow]Sugerencia IA:[/yellow] {f.filled_value}\n"
                "[cyan]ENTER = no guardar | 's' = guardar tal cual | otro texto = guardar ese texto: [/cyan]",
                end="",
            )
            try:
                reply = input().strip()
            except EOFError:
                break
            if not reply:
                continue
            answer = f.filled_value if reply.lower() in {"s", "si", "sí", "y", "yes"} else reply
            self.repository.upsert_qa_memory(
                question_norm=norm_q,
                raw_example=f.label,
                answer=answer,
                category=QuestionCategory.GENERAL,
                source=AnswerSource.USER_CONFIRMED,
            )
            saved += 1
        return saved

    def _extract_field_label(self, element: Any, page: Page) -> str:
        aria = element.get_attribute("aria-label")
        if aria and str(aria).strip():
            return str(aria).strip()

        placeholder = element.get_attribute("placeholder")
        if placeholder and str(placeholder).strip():
            return str(placeholder).strip()

        elem_id = element.get_attribute("id")
        if elem_id:
            try:
                label_for = page.locator(f"label[for='{elem_id}']").first
                if label_for.count():
                    return label_for.inner_text().strip()
            except Exception:
                pass

        name = element.get_attribute("name")
        if name:
            return str(name).replace("_", " ").replace("-", " ").strip()

        return ""
