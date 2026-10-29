from collections.abc import Iterator
import pytest

from src.adapters.db.repository import ApplicationRepository
from src.domain.models import (
    AnswerSource,
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    QuestionCategory,
    WorkModality,
)


@pytest.fixture
def repo() -> Iterator[ApplicationRepository]:
    repository = ApplicationRepository(":memory:")
    yield repository
    repository.close()


def _make_sample_offer(
    portal: PortalName = PortalName.LINKEDIN,
    url: str = "https://www.linkedin.com/jobs/view/1001",
) -> tuple[JobOffer, MatchEvaluation]:
    offer = JobOffer(
        portal=portal,
        title="Desarrollador Full Stack Junior",
        company="TechCorp Colombia",
        location="Barranquilla",
        modality=WorkModality.REMOTE,
        url=url,
        description="React, Node.js y PostgreSQL.",
    )
    evaluation = MatchEvaluation(
        dedup_key="techcorp colombia::desarrollador full stack junior",
        canonical_url=url,
        match_score=85,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="PostgreSQL", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="AWS", is_matched=False, weight=KeywordWeight.BONUS),
        ),
    )
    return offer, evaluation


def test_first_application_creates_single_record_with_count_one(
    repo: ApplicationRepository,
) -> None:
    offer, evaluation = _make_sample_offer(PortalName.LINKEDIN)
    record, applied = repo.record_submission(offer, evaluation, applied_at="2026-10-28T10:00:00Z")

    assert applied is True
    assert record.times_applied == 1
    assert record.status == ApplicationStatus.APPLIED
    assert record.first_applied_at == "2026-10-28T10:00:00Z"
    assert record.last_applied_at == "2026-10-28T10:00:00Z"
    assert len(record.submissions) == 1
    assert record.submissions[0].portal == PortalName.LINKEDIN
    assert len(record.keywords) == 4


def test_reapplication_on_different_portal_increments_count_without_duplicating_row(
    repo: ApplicationRepository,
) -> None:
    # 1. First submission on LinkedIn
    offer1, eval1 = _make_sample_offer(PortalName.LINKEDIN, "https://www.linkedin.com/jobs/view/1001")
    repo.record_submission(offer1, eval1, applied_at="2026-10-28T10:00:00Z")

    # 2. Second submission on GetOnBrd (same company and title -> same dedup_key)
    offer2, eval2 = _make_sample_offer(PortalName.GETONBRD, "https://www.getonbrd.com/jobs/dev-1002")
    record, applied = repo.record_submission(offer2, eval2, applied_at="2026-10-28T14:00:00Z")

    assert applied is True
    assert record.times_applied == 2
    assert record.first_applied_at == "2026-10-28T10:00:00Z"
    assert record.last_applied_at == "2026-10-28T14:00:00Z"
    assert len(record.submissions) == 2
    assert record.submissions[0].portal == PortalName.LINKEDIN
    assert record.submissions[1].portal == PortalName.GETONBRD

    # Verify database has strictly ONE master row in applications table
    all_apps = repo.find_all()
    assert len(all_apps) == 1
    assert all_apps[0].id == record.id


def test_reapplication_on_same_portal_blocks_during_cooldown(
    repo: ApplicationRepository,
) -> None:
    offer, evaluation = _make_sample_offer(PortalName.LINKEDIN)
    repo.record_submission(offer, evaluation, applied_at="2026-10-28T10:00:00Z")

    # Attempt to apply again on same portal only 1 day later (cooldown is 3 days)
    record, applied = repo.record_submission(
        offer, evaluation, applied_at="2026-10-29T10:00:00Z", cooldown_days=3
    )

    assert applied is False
    assert record.times_applied == 1
    assert len(record.submissions) == 1


def test_reapplication_on_same_portal_allows_after_cooldown_expires(
    repo: ApplicationRepository,
) -> None:
    offer, evaluation = _make_sample_offer(PortalName.LINKEDIN)
    repo.record_submission(offer, evaluation, applied_at="2026-10-28T10:00:00Z")

    # Apply 5 days later (exceeds 3 days cooldown)
    record, applied = repo.record_submission(
        offer, evaluation, applied_at="2026-11-02T10:00:00Z", cooldown_days=3
    )

    assert applied is True
    assert record.times_applied == 2
    assert len(record.submissions) == 2
    assert record.last_applied_at == "2026-11-02T10:00:00Z"


def test_reapplication_is_frozen_when_status_is_interview_or_rejected(
    repo: ApplicationRepository,
) -> None:
    offer, evaluation = _make_sample_offer(PortalName.LINKEDIN)
    record, _ = repo.record_submission(offer, evaluation, applied_at="2026-10-28T10:00:00Z")

    # User manually marks interview scheduled
    repo.update_status(record.id, ApplicationStatus.INTERVIEW_SCHEDULED)

    # Even from another portal, it must not reapply
    new_offer = JobOffer(
        portal=PortalName.COMPUTRABAJO,
        title=offer.title,
        company=offer.company,
        location=offer.location,
        modality=offer.modality,
        url="https://computrabajo.com/1003",
        description=offer.description,
    )
    new_record, applied = repo.record_submission(new_offer, evaluation, applied_at="2026-10-29T10:00:00Z")

    assert applied is False
    assert new_record.times_applied == 1
    assert new_record.status == ApplicationStatus.INTERVIEW_SCHEDULED


def test_keyword_stats_aggregates_unique_jobs_not_reapplication_count(
    repo: ApplicationRepository,
) -> None:
    # Application 1 submitted 3 times
    offer1, eval1 = _make_sample_offer(PortalName.LINKEDIN, "https://linkedin.com/1")
    repo.record_submission(offer1, eval1, applied_at="2026-10-28T10:00:00Z")

    offer1_sub2 = JobOffer(
        portal=PortalName.GETONBRD,
        title=offer1.title,
        company=offer1.company,
        location=offer1.location,
        modality=offer1.modality,
        url="https://getonbrd.com/1",
        description=offer1.description,
    )
    repo.record_submission(offer1_sub2, eval1, applied_at="2026-10-28T12:00:00Z")

    # Application 2 for a different company
    offer2 = JobOffer(
        portal=PortalName.COMPUTRABAJO,
        title="Junior React Dev",
        company="Otra Empresa",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://computrabajo.com/2",
        description="React y Node.",
    )
    eval2 = MatchEvaluation(
        dedup_key="otra empresa::junior react dev",
        canonical_url="https://computrabajo.com/2",
        match_score=90,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repo.record_submission(offer2, eval2, applied_at="2026-10-28T13:00:00Z")

    stats = repo.get_keyword_stats()
    stats_dict = {keyword: total for keyword, total, _ in stats}

    # Crucial test: React must count as 2 distinct jobs, NOT 3 or 4!
    assert stats_dict["React"] == 2
    assert stats_dict["Node.js"] == 2
    assert stats_dict["PostgreSQL"] == 1


def test_qa_memory_upsert_and_retrieve(repo: ApplicationRepository) -> None:
    repo.upsert_qa_memory(
        question_norm="cuantos anos de experiencia tienes con react",
        raw_example="¿Cuántos años de experiencia tienes con React?",
        answer="2 años desarrollando proyectos full stack",
        category=QuestionCategory.EXPERIENCE,
        source=AnswerSource.PROFILE_SEED,
    )

    all_qa = repo.get_all_qa_memory()
    assert len(all_qa) == 1
    assert all_qa[0][0] == "cuantos anos de experiencia tienes con react"
    assert all_qa[0][2] == "2 años desarrollando proyectos full stack"

    # Update with confirmed answer
    repo.upsert_qa_memory(
        question_norm="cuantos anos de experiencia tienes con react",
        raw_example="Años de experiencia con React.js:",
        answer="3 años demostrables en portafolio y proyectos",
        category=QuestionCategory.EXPERIENCE,
        source=AnswerSource.USER_CONFIRMED,
    )

    updated_qa = repo.get_all_qa_memory()
    assert len(updated_qa) == 1
    assert updated_qa[0][2] == "3 años demostrables en portafolio y proyectos"


def test_insert_or_ignore_keywords_does_not_raise_on_duplicate_association(
    repo: ApplicationRepository,
) -> None:
    offer1, eval1 = _make_sample_offer(PortalName.LINKEDIN, "https://linkedin.com/duplicate-kw-1")
    record, applied = repo.record_submission(offer1, eval1, applied_at="2026-10-28T10:00:00Z")
    assert applied is True
    assert len(record.keywords) == 4

    # Re-apply on another portal with the same evaluation keywords (cooldown doesn't apply to different portals)
    offer2 = JobOffer(
        portal=PortalName.GETONBRD,
        title=offer1.title,
        company=offer1.company,
        location=offer1.location,
        modality=offer1.modality,
        url="https://getonbrd.com/duplicate-kw-2",
        description=offer1.description,
    )
    # This invokes _update_existing_reapplication which re-inserts keywords with INSERT OR IGNORE
    reapplied_record, reapplied = repo.record_submission(offer2, eval1, applied_at="2026-10-28T11:00:00Z")
    assert reapplied is True
    assert reapplied_record.times_applied == 2
    # Keywords are still cleanly intact without exceptions
    assert len(reapplied_record.keywords) == 4

