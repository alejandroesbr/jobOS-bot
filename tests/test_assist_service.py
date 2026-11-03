from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.adapters.db.repository import ApplicationRepository
from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    CandidatePersonalInfo,
    CandidatePreferences,
    CandidateProfile,
    CandidateSalary,
    JobOffer,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.domain.qa_engine import QuestionAnswerEngine
from src.services.assist_service import AssistService, EXCLUDED_INPUT_TYPES


@pytest.fixture
def mock_profile() -> CandidateProfile:
    return CandidateProfile(
        personal=CandidatePersonalInfo(
            full_name="Candidate Test",
            email="secret.email@example.com",
            phone="+57 300 000 0000",
            city="Barranquilla",
            country="Colombia",
            linkedin_url="https://linkedin.com/in/test",
            github_url="https://github.com/test",
            portfolio_url="https://test.dev",
        ),
        preferences=CandidatePreferences(
            residency="Colombia",
            colombia_work_permit=True,
            requires_visa_sponsorship=False,
            remote_availability=True,
            hybrid_availability=True,
            notice_period="Inmediata",
            english_level="B2 - Intermedio Alto",
        ),
        salary=CandidateSalary(
            cop_monthly=5000000,
            cop_monthly_min=4500000,
            cop_monthly_max=6000000,
            usd_monthly=1500,
            usd_monthly_min=1200,
            usd_monthly_max=2000,
        ),
        experience_years={"React": 3, "Node.js": 2, "Python": 2},
    )


@pytest.fixture
def assist_service(mock_profile: CandidateProfile) -> AssistService:
    repo = ApplicationRepository(":memory:")
    qa_engine = QuestionAnswerEngine(profile=mock_profile, repository=repo)
    gemini_client = MagicMock()
    return AssistService(repository=repo, qa_engine=qa_engine, gemini_client=gemini_client)


def test_excluded_input_types_includes_password_and_search() -> None:
    assert "password" in EXCLUDED_INPUT_TYPES
    assert "search" in EXCLUDED_INPUT_TYPES
    assert "hidden" in EXCLUDED_INPUT_TYPES
    assert "submit" in EXCLUDED_INPUT_TYPES


def test_build_safe_context_does_not_leak_contact_pii_for_technical_question(
    assist_service: AssistService,
) -> None:
    ctx = assist_service._build_safe_context_for_prompt("¿Cuántos años de experiencia tienes con React?")
    assert "secret.email@example.com" not in ctx
    assert "+57 300 000 0000" not in ctx
    assert "5000000" not in ctx
    assert "React: 3 años" in ctx


def test_build_safe_context_includes_salary_only_when_asked(
    assist_service: AssistService,
) -> None:
    ctx_cop = assist_service._build_safe_context_for_prompt("¿Cuál es tu expectativa salarial en COP?")
    assert "5,000,000 COP/mes" in ctx_cop
    assert "secret.email@example.com" not in ctx_cop

    ctx_usd = assist_service._build_safe_context_for_prompt("What is your expected salary in USD?")
    assert "$1500 USD/mes" in ctx_usd


def test_can_safely_auto_submit_blocks_when_error_visible(
    assist_service: AssistService,
) -> None:
    mock_modal = MagicMock()
    mock_err = MagicMock()
    mock_err.is_visible.return_value = True
    mock_err.inner_text.return_value = "Por favor ingresa un número válido"

    def locator_mock(selector: str) -> MagicMock:
        loc = MagicMock()
        if ".artdeco-inline-feedback--error" in selector:
            loc.all.return_value = [mock_err]
        else:
            loc.all.return_value = []
        return loc

    mock_modal.locator.side_effect = locator_mock

    can_submit, reason = assist_service._can_safely_auto_submit(mock_modal)
    assert can_submit is False
    assert "Por favor ingresa un número válido" in reason


def test_can_safely_auto_submit_blocks_when_required_input_empty(
    assist_service: AssistService,
) -> None:
    mock_modal = MagicMock()
    mock_input = MagicMock()
    mock_input.get_attribute.return_value = "text"
    mock_input.input_value.return_value = "   "  # Empty whitespace

    def locator_mock(selector: str) -> MagicMock:
        loc = MagicMock()
        if "input[required]" in selector:
            loc.all.return_value = [mock_input]
        else:
            loc.all.return_value = []
        return loc

    mock_modal.locator.side_effect = locator_mock

    can_submit, reason = assist_service._can_safely_auto_submit(mock_modal)
    assert can_submit is False
    assert "Campo obligatorio vacío" in reason


def test_can_safely_auto_submit_allows_when_clean(
    assist_service: AssistService,
) -> None:
    mock_modal = MagicMock()

    def locator_mock(selector: str) -> MagicMock:
        loc = MagicMock()
        loc.all.return_value = []
        return loc

    mock_modal.locator.side_effect = locator_mock

    can_submit, reason = assist_service._can_safely_auto_submit(mock_modal)
    assert can_submit is True
    assert reason == ""


def test_verify_submission_confirmed_detects_success_dialog(
    assist_service: AssistService,
) -> None:
    mock_page = MagicMock()
    mock_modal = MagicMock()
    mock_success_el = MagicMock()
    mock_success_el.is_visible.return_value = True

    def page_locator(sel: str) -> MagicMock:
        loc = MagicMock()
        if "Tu solicitud se ha enviado" in sel:
            loc.first = mock_success_el
        else:
            first_mock = MagicMock()
            first_mock.is_visible.return_value = False
            loc.first = first_mock
        return loc

    mock_page.locator.side_effect = page_locator

    confirmed = assist_service._verify_submission_confirmed(mock_page, mock_modal)
    assert confirmed is True





def test_verify_submission_confirmed_detects_applied_button_on_page(
    assist_service: AssistService,
) -> None:
    mock_page = MagicMock()
    mock_modal = MagicMock()
    mock_modal.is_visible.return_value = False

    def page_locator(sel: str) -> MagicMock:
        loc = MagicMock()
        first_mock = MagicMock()
        if ".jobs-s-apply button:has-text('Solicitud enviada')" in sel:
            first_mock.is_visible.return_value = True
        else:
            first_mock.is_visible.return_value = False
        loc.first = first_mock
        return loc

    mock_page.locator.side_effect = page_locator

    confirmed = assist_service._verify_submission_confirmed(mock_page, mock_modal)
    assert confirmed is True


def test_detect_closed_or_expired_detects_linkedin_closed_message(
    assist_service: AssistService,
) -> None:
    mock_page = MagicMock()
    mock_closed_el = MagicMock()
    mock_closed_el.is_visible.return_value = True

    def page_locator(sel: str) -> MagicMock:
        loc = MagicMock()
        if "Ya no se aceptan solicitudes" in sel:
            loc.first = mock_closed_el
        else:
            first_mock = MagicMock()
            first_mock.is_visible.return_value = False
            loc.first = first_mock
        return loc

    mock_page.locator.side_effect = page_locator

    is_closed, reason = assist_service._detect_closed_or_expired(mock_page)
    assert is_closed is True
    assert "Ya no se aceptan solicitudes" in reason






