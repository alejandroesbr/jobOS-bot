import pytest

from src.domain.models import (
    ApplicationStatus,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
)
from src.domain.text_normalizer import (
    build_dedup_key,
    normalize_canonical_url,
    normalize_company_name,
    normalize_form_question,
    normalize_job_title,
)


def test_normalize_company_name_strips_legal_suffixes_and_accents() -> None:
    raw_name = "  Mercado Libre Colombia S.A.S. "
    result = normalize_company_name(raw_name)
    assert result == "mercado libre"


def test_normalize_company_name_handles_international_suffixes() -> None:
    raw_name = "EPAM Systems, Inc. - Latam"
    result = normalize_company_name(raw_name)
    assert result == "epam systems"


def test_normalize_job_title_unifies_synonyms_and_strips_modality_noise() -> None:
    raw_title = "[URGENTE] Desarrollador Fullstack Jr. (React.js / Node.js) - Remoto 100%"
    result = normalize_job_title(raw_title)
    assert result == "desarrollador full stack junior react node"


def test_build_dedup_key_produces_identical_key_across_portals() -> None:
    linkedin_key = build_dedup_key(
        company="TechCorp Colombia S.A.S",
        title="Desarrollador Fullstack Jr (React/Node.js) - Remoto",
    )
    getonbrd_key = build_dedup_key(
        company="TechCorp LLC",
        title="[Remoto] Desarrollador Full Stack Junior - React.js & Node",
    )
    assert linkedin_key == "techcorp::desarrollador full stack junior react node"
    assert getonbrd_key == linkedin_key


def test_build_dedup_key_raises_value_error_when_company_is_empty() -> None:
    with pytest.raises(ValueError, match="company and title must contain valid"):
        build_dedup_key(company="   ", title="Software Engineer")


def test_normalize_canonical_url_strips_linkedin_tracking_parameters() -> None:
    raw_url = "https://www.linkedin.com/jobs/view/4102938471/?refId=abc&trackingId=xyz&utm_source=share#details"
    result = normalize_canonical_url(raw_url)
    assert result == "https://www.linkedin.com/jobs/view/4102938471"


def test_normalize_canonical_url_preserves_linkedin_current_job_id_on_search_view() -> None:
    raw_url = "https://www.linkedin.com/jobs/search/?currentJobId=4102938471&geoId=100&utm_medium=organic"
    result = normalize_canonical_url(raw_url)
    assert result == "https://www.linkedin.com/jobs/search?currentJobId=4102938471"


def test_normalize_canonical_url_preserves_only_jk_param_on_indeed() -> None:
    raw_url = "http://co.indeed.com/viewjob?jk=9f8e7d6c&tk=1h2j3k&from=serp"
    result = normalize_canonical_url(raw_url)
    assert result == "https://co.indeed.com/viewjob?jk=9f8e7d6c"


def test_normalize_form_question_removes_punctuation_and_unifies_tech_terms() -> None:
    raw_label = "* ¿Cuántos años de experiencia tienes trabajando con React.js? (Obligatorio) :"
    result = normalize_form_question(raw_label)
    assert result == "cuantos anos de experiencia tienes trabajando con react"


def test_application_status_allows_reapplication_only_for_active_non_terminal_states() -> None:
    assert ApplicationStatus.PENDING.allows_reapplication() is True
    assert ApplicationStatus.APPLIED.allows_reapplication() is True
    assert ApplicationStatus.FOLLOW_UP_REQUIRED.allows_reapplication() is True
    assert ApplicationStatus.INTERVIEW_SCHEDULED.allows_reapplication() is False
    assert ApplicationStatus.OFFER_RECEIVED.allows_reapplication() is False
    assert ApplicationStatus.REJECTED.allows_reapplication() is False
    assert ApplicationStatus.DISCARDED.allows_reapplication() is False


def test_match_evaluation_separates_matched_and_missing_keywords() -> None:
    evaluation = MatchEvaluation(
        dedup_key="acme::junior backend developer",
        canonical_url="https://www.getonbrd.com/jobs/programming/junior-backend-acme",
        match_score=60,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="PostgreSQL", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="AWS", is_matched=False, weight=KeywordWeight.BONUS),
        ),
    )
    assert evaluation.matched_keywords == ("Node.js", "PostgreSQL")
    assert evaluation.missing_keywords == ("AWS",)

