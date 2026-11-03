from collections.abc import Iterator
from pathlib import Path
import re
from unittest.mock import MagicMock

import pytest

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.pdf.cv_renderer import render_cv_html
from src.config_loader import FilterConfig, load_filter_config
from src.domain.cv_tailor import (
    SKILLS_SECTION_PATTERN,
    SUMMARY_SECTION_PATTERN,
    cv_to_markdown,
    parse_cv_markdown,
    section_text,
    tailor_cv_document,
    validate_tailored_summary,
)
from src.domain.models import (
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.services.cv_service import CvService

CV_BASE = """# Ana Pérez
**Junior Backend Developer**

- **Email:** ana@example.com
- **GitHub:** [github.com/ana](https://github.com/ana)

---

## Professional Summary
Junior developer building REST APIs with Node.js and PostgreSQL.

## Technical Skills
- **Frontend:** React, Tailwind CSS
- **Backend:** Express, Node.js, NestJS
- **Databases:** MySQL, PostgreSQL

## Projects

### Task Dashboard
- React dashboard with Tailwind CSS.

### Orders API
- REST API with Node.js, Express and PostgreSQL.

## Education
- **B.S. Software Engineering** (2024 – Present)
"""


class FakeRenderer:
    def __init__(self) -> None:
        self.rendered: list[tuple[str, Path]] = []

    def render(self, html: str, out_path: Path) -> None:
        self.rendered.append((html, out_path))


@pytest.fixture
def filter_config() -> FilterConfig:
    return load_filter_config("config/filters.yaml")


@pytest.fixture
def repo() -> Iterator[ApplicationRepository]:
    repository = ApplicationRepository(":memory:")
    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Backend Developer Node.js",
        company="Acme S.A.S",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/acme-1",
        description="Buscamos Node.js, Express y PostgreSQL.",
    )
    evaluation = MatchEvaluation(
        dedup_key="acme::backend developer node",
        canonical_url=offer.url,
        match_score=90,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="PostgreSQL", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Express", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repository.record_discovered_offer(offer, evaluation)
    yield repository
    repository.close()


def test_parse_and_render_roundtrip_keeps_sections() -> None:
    doc = parse_cv_markdown(CV_BASE)

    assert [s.title for s in doc.sections] == ["Professional Summary", "Technical Skills", "Projects", "Education"]
    assert "## Projects" in cv_to_markdown(doc)


def test_tailoring_prioritizes_offer_skills_and_projects_without_adding_anything() -> None:
    doc = parse_cv_markdown(CV_BASE)
    tailored = tailor_cv_document(doc, ["Node.js", "PostgreSQL", "Express"])

    skills = tailored.find_section(SKILLS_SECTION_PATTERN)
    assert skills is not None
    assert skills.lines[0] == "- **Backend:** Express, Node.js, NestJS"
    assert skills.lines[1] == "- **Databases:** PostgreSQL, MySQL"

    projects = tailored.sections[2]
    assert [p.title for p in projects.subsections] == ["Orders API", "Task Dashboard"]

    def words(markdown: str) -> list[str]:
        return sorted(w for w in re.split(r"[\s,]+", markdown) if w)

    assert words(cv_to_markdown(tailored)) == words(cv_to_markdown(doc))


def test_summary_validation_rejects_invented_technology_and_numbers() -> None:
    keywords = ["Node.js", "PostgreSQL", "Kubernetes", "AWS"]

    ok = "Junior backend developer focused on REST APIs with Node.js and PostgreSQL for growing teams."
    assert validate_tailored_summary(ok, CV_BASE, keywords) is None

    invented_tech = "Junior backend developer with Node.js, PostgreSQL and Kubernetes in production."
    assert "Kubernetes" in str(validate_tailored_summary(invented_tech, CV_BASE, keywords))

    invented_years = "Backend developer with 5 years building REST APIs with Node.js and PostgreSQL."
    assert "'5'" in str(validate_tailored_summary(invented_years, CV_BASE, keywords))


def test_render_html_escapes_text_and_keeps_links() -> None:
    doc = parse_cv_markdown(CV_BASE.replace("Ana Pérez", "Ana <script>"))
    html = render_cv_html(doc)

    assert "<script>" not in html
    assert '<a href="https://github.com/ana">github.com/ana</a>' in html
    assert "<h2>Technical Skills</h2>" in html


def test_cv_service_generates_pdf_with_validated_gemini_summary(
    repo: ApplicationRepository,
    filter_config: FilterConfig,
    tmp_path: Path,
) -> None:
    cv_path = tmp_path / "cv_base.md"
    cv_path.write_text(CV_BASE, encoding="utf-8")
    gemini = MagicMock(spec=GeminiClient)
    gemini.is_available = True
    gemini.last_call_failed = False
    gemini.tailor_summary.return_value = "Junior backend developer focused on Node.js, Express and PostgreSQL REST APIs."

    service = CvService(repo, gemini_client=gemini, config=filter_config, cv_base_path=cv_path, output_dir=tmp_path / "cvs")
    renderer = FakeRenderer()
    result = service.generate(1, renderer)

    assert result.summary_source == "Gemini"
    assert result.pdf_path == tmp_path / "cvs" / "1_acme-s-a-s_backend-developer-node-js.pdf"
    html = renderer.rendered[0][0]
    assert "focused on Node.js, Express and PostgreSQL" in html
    record = repo.find_by_id(1)
    assert record is not None
    assert record.cv_pdf_path == str(result.pdf_path)
    assert record.cv_summary_cache is not None


def test_cv_service_falls_back_to_base_summary_when_gemini_invents(
    repo: ApplicationRepository,
    filter_config: FilterConfig,
    tmp_path: Path,
) -> None:
    cv_path = tmp_path / "cv_base.md"
    cv_path.write_text(CV_BASE, encoding="utf-8")
    gemini = MagicMock(spec=GeminiClient)
    gemini.is_available = True
    gemini.last_call_failed = False
    gemini.tailor_summary.return_value = "Senior engineer with 8 years of Kubernetes and AWS experience."

    service = CvService(repo, gemini_client=gemini, config=filter_config, cv_base_path=cv_path, output_dir=tmp_path / "cvs")
    renderer = FakeRenderer()
    result = service.generate(1, renderer)

    assert result.summary_source.startswith("CV base (resumen IA descartado")
    assert "Kubernetes" not in renderer.rendered[0][0]
    assert section_text(parse_cv_markdown(CV_BASE).find_section(SUMMARY_SECTION_PATTERN)) in renderer.rendered[0][0]
    record = repo.find_by_id(1)
    assert record is not None
    assert record.cv_summary_cache is None


def test_cv_service_requires_personal_cv_base(
    repo: ApplicationRepository,
    filter_config: FilterConfig,
    tmp_path: Path,
) -> None:
    service = CvService(
        repo,
        gemini_client=MagicMock(spec=GeminiClient),
        config=filter_config,
        cv_base_path=tmp_path / "missing.md",
        output_dir=tmp_path / "cvs",
    )
    with pytest.raises(FileNotFoundError, match="cv_base.example.md"):
        service.generate(1, FakeRenderer())
