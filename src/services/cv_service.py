from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Protocol

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.pdf.cv_renderer import render_cv_html
from src.config_loader import FilterConfig, load_filter_config
from src.domain.cv_tailor import (
    SUMMARY_SECTION_PATTERN,
    parse_cv_markdown,
    section_text,
    tailor_cv_document,
    validate_tailored_summary,
)
from src.domain.models import ApplicationRecord
from src.domain.text_normalizer import strip_accents

logger = logging.getLogger(__name__)

DEFAULT_CV_BASE = Path("config/cv_base.md")
DEFAULT_OUTPUT_DIR = Path("cvs")


class PdfRenderer(Protocol):
    def render(self, html: str, out_path: Path) -> None: ...


@dataclass(frozen=True, slots=True)
class CvGenerationResult:
    application_id: int
    pdf_path: Path
    summary_source: str
    reused_existing: bool = False


def _slug(text: str, max_len: int = 40) -> str:
    ascii_text = strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:max_len].strip("-") or "vacante"


class CvService:
    def __init__(
        self,
        repository: ApplicationRepository,
        gemini_client: GeminiClient | None = None,
        config: FilterConfig | None = None,
        cv_base_path: Path | str = DEFAULT_CV_BASE,
        output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    ) -> None:
        self.repository = repository
        self.gemini_client = gemini_client or GeminiClient()
        self.config = config if config is not None else load_filter_config()
        self.cv_base_path = Path(cv_base_path)
        self.output_dir = Path(output_dir)

    def _read_cv_base(self) -> str:
        if not self.cv_base_path.is_file():
            raise FileNotFoundError(
                f"No existe '{self.cv_base_path}'. Cópialo desde 'config/cv_base.example.md' y pon tus datos reales."
            )
        return self.cv_base_path.read_text(encoding="utf-8")

    def _known_keywords(self) -> list[str]:
        vocab = self.config.tech_vocabulary
        return list(dict.fromkeys([*vocab.core, *vocab.secondary, *vocab.bonus]))

    def _resolve_summary(self, record: ApplicationRecord, cv_markdown: str, current_summary: str) -> tuple[str | None, str]:
        if record.cv_summary_cache:
            return record.cv_summary_cache, "caché"
        if not current_summary or not self.gemini_client.is_available:
            return None, "CV base"

        candidate = self.gemini_client.tailor_summary(
            job_title=record.title,
            job_description=record.description,
            cv_base_markdown=cv_markdown,
            current_summary=current_summary,
        )
        if self.gemini_client.last_call_failed is True or not candidate:
            return None, "CV base (Gemini no respondió)"

        rejection = validate_tailored_summary(candidate, cv_markdown, self._known_keywords())
        if rejection is not None:
            logger.warning("Resumen de Gemini descartado para la vacante #%s: %s", record.id, rejection)
            return None, f"CV base (resumen IA descartado: {rejection})"

        self.repository.save_cv_summary_cache(record.id, candidate)
        return candidate, "Gemini"

    def generate(self, application_id: int, renderer: PdfRenderer, force: bool = False) -> CvGenerationResult:
        record = self.repository.find_by_id(application_id)
        if record is None:
            raise ValueError(f"La vacante #{application_id} no existe en la base de datos.")

        if not force and record.cv_pdf_path and Path(record.cv_pdf_path).is_file():
            return CvGenerationResult(application_id, Path(record.cv_pdf_path), "existente", reused_existing=True)

        cv_markdown = self._read_cv_base()
        doc = parse_cv_markdown(cv_markdown)
        current_summary = section_text(doc.find_section(SUMMARY_SECTION_PATTERN))
        summary, summary_source = self._resolve_summary(record, cv_markdown, current_summary)

        offer_keywords = [kw.keyword for kw in record.keywords]
        tailored = tailor_cv_document(doc, offer_keywords, summary=summary)

        out_path = self.output_dir / f"{record.id}_{_slug(record.company)}_{_slug(record.title)}.pdf"
        renderer.render(render_cv_html(tailored), out_path)
        self.repository.save_cv_pdf_path(record.id, str(out_path))
        return CvGenerationResult(record.id, out_path, summary_source)
