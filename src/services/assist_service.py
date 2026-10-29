from dataclasses import dataclass
import logging
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.scrapers.browser import DEFAULT_USER_AGENT, DEFAULT_VIEWPORT
from src.config_loader import load_candidate_profile
from src.domain.models import AnswerSource, QuestionCategory
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

    def run_assist(self, url: str) -> AssistReport:
        print_banner("jobOS-bot — Copiloto Human-in-the-Loop", f"Asistiendo formulario en: {url}")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport=DEFAULT_VIEWPORT,
                locale="es-419,es;q=0.9",
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as ex:
                print_error(f"No se pudo cargar la URL: {ex}")
                browser.close()
                return AssistReport(url, 0, 0, 0, 0)

            # Discover input fields
            inputs = page.locator("input:visible, textarea:visible, select:visible").all()
            field_results: list[FieldAssistResult] = []

            for field_el in inputs:
                field_type = field_el.get_attribute("type") or "text"
                if field_type in {"hidden", "submit", "button", "checkbox", "radio", "file"}:
                    continue

                label_text = self._extract_field_label(field_el, page)
                if not label_text:
                    continue

                is_numeric = field_type == "number"
                match = self.qa_engine.find_answer(label_text, is_numeric_input=is_numeric)

                if match.is_confident_match and match.answer:
                    # Confident: fill and highlight GREEN
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
                    # Fallback to Gemini: fill and highlight YELLOW
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

            context.close()
            browser.close()

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
