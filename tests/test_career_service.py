from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.notion.notion_client import NotionClient
from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.services.career_service import CareerService


@pytest.fixture
def repo() -> Iterator[ApplicationRepository]:
    repository = ApplicationRepository(":memory:")
    yield repository
    repository.close()


@pytest.fixture
def populated_repo(repo: ApplicationRepository) -> ApplicationRepository:
    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Desarrollador Full Stack Junior",
        company="TechCorp Latam",
        location="Barranquilla",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/dev-1",
        description="React, Node.js y PostgreSQL.",
    )
    evaluation = MatchEvaluation(
        dedup_key="techcorp latam::desarrollador full stack junior",
        canonical_url=offer.url,
        match_score=85,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repo.record_submission(offer, evaluation, applied_at="2026-10-20T10:00:00Z")
    return repo


def test_tailor_cv_caches_analysis_in_database(populated_repo: ApplicationRepository) -> None:
    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.tailor_cv.return_value = "### Mock ATS Gap & Suggestions"

    service = CareerService(repository=populated_repo, gemini_client=mock_gemini)

    # 1. First run generates and writes to DB cache
    analysis_1 = service.tailor_cv(application_id=1)
    assert analysis_1 == "### Mock ATS Gap & Suggestions"
    assert mock_gemini.tailor_cv.call_count == 1

    # 2. Second run reads from SQLite cache without calling Gemini
    analysis_2 = service.tailor_cv(application_id=1)
    assert analysis_2 == "### Mock ATS Gap & Suggestions"
    assert mock_gemini.tailor_cv.call_count == 1


def test_prepare_interview_generates_file_and_saves_path(populated_repo: ApplicationRepository) -> None:
    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.prepare_interview.return_value = "# Mock Technical Interview Guide"

    service = CareerService(repository=populated_repo, gemini_client=mock_gemini)
    prep_path = service.prepare_interview(application_id=1)

    assert prep_path.is_file()
    assert "techcorp_latam" in str(prep_path).lower()
    assert prep_path.read_text(encoding="utf-8") == "# Mock Technical Interview Guide"

    # Verify saved in SQLite record
    rec = populated_repo.find_by_id(1)
    assert rec is not None
    assert rec.interview_prep_path == str(prep_path)


def test_check_followups_flags_stalled_applications(populated_repo: ApplicationRepository) -> None:
    service = CareerService(repository=populated_repo)

    # Offer applied on 2026-10-20 (more than 7 days ago relative to now)
    stalled = service.check_followups(days_threshold=7)
    assert len(stalled) == 1
    assert stalled[0].id == 1

    # Verify status changed to FOLLOW_UP_REQUIRED
    updated = populated_repo.find_by_id(1)
    assert updated is not None
    assert updated.status == ApplicationStatus.FOLLOW_UP_REQUIRED

    # Verify followups/pendientes.md was generated
    followup_file = Path("followups/pendientes.md")
    assert followup_file.is_file()
    content = followup_file.read_text(encoding="utf-8")
    assert "TechCorp Latam" in content
    assert "Desarrollador Full Stack Junior" in content


def test_sync_with_notion_orchestration(populated_repo: ApplicationRepository) -> None:
    mock_notion = MagicMock(spec=NotionClient)
    mock_notion.is_configured = True
    mock_notion.push_application.return_value = "page-new-123"
    mock_notion.pull_status_updates.return_value = [("page-new-123", "Entrevista Programada")]

    mock_gemini = MagicMock(spec=GeminiClient)
    mock_gemini.prepare_interview.return_value = "# Prep Content"

    service = CareerService(
        repository=populated_repo,
        gemini_client=mock_gemini,
        notion_client=mock_notion,
    )

    report = service.sync_with_notion()
    assert report.pushed_new == 1
    assert report.pulled_statuses == 1
    assert report.interview_preps_triggered == 1
