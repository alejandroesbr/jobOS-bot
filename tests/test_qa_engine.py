import pytest

from src.adapters.db.repository import ApplicationRepository
from src.config_loader import load_candidate_profile
from src.domain.models import (
    AnswerSource,
    CandidatePersonalInfo,
    CandidatePreferences,
    CandidateProfile,
    CandidateSalary,
    PortalName,
    QuestionCategory,
)
from src.domain.qa_engine import QuestionAnswerEngine


@pytest.fixture
def sample_profile() -> CandidateProfile:
    return CandidateProfile(
        personal=CandidatePersonalInfo(
            full_name="Alejandro Gómez",
            email="alejandro.developer@example.com",
            phone="+57 300 123 4567",
            city="Barranquilla",
            country="Colombia",
            linkedin_url="https://www.linkedin.com/in/alejandro-dev",
            github_url="https://github.com/alejandro-dev",
            portfolio_url="https://alejandro-dev.io",
        ),
        preferences=CandidatePreferences(
            residency="Barranquilla, Colombia",
            colombia_work_permit=True,
            requires_visa_sponsorship=False,
            remote_availability=True,
            hybrid_availability=True,
            notice_period="Inmediata",
            english_level="B2 - Profesional Intermedio",
        ),
        salary=CandidateSalary(
            cop_monthly=3800000,
            cop_monthly_min=3500000,
            cop_monthly_max=4500000,
            usd_monthly=1500,
            usd_monthly_min=1200,
            usd_monthly_max=2000,
        ),
        experience_years={
            "React": 2,
            "Node.js": 2,
            "NestJS": 1,
            "TypeScript": 2,
            "JavaScript": 3,
            "PostgreSQL": 2,
            "SQL": 2,
            "Git": 3,
            "AWS": 1,
        },
        default_floor_years=1,
    )


@pytest.fixture
def engine(sample_profile: CandidateProfile) -> QuestionAnswerEngine:
    return QuestionAnswerEngine(profile=sample_profile, similarity_threshold=85.0)


def test_fuzzy_experience_match_spanish_variant(engine: QuestionAnswerEngine) -> None:
    # Query has 'en' instead of 'con', question marks and accents
    match = engine.find_answer("¿Cuántos años de experiencia tienes en React?")

    assert match.is_confident_match is True
    assert match.similarity_score >= 85.0
    assert "2" in match.answer
    assert match.category == QuestionCategory.EXPERIENCE


def test_fuzzy_experience_match_english_variant(engine: QuestionAnswerEngine) -> None:
    # English phrasing with .js alias
    match = engine.find_answer("Years of experience with React.js?")

    assert match.is_confident_match is True
    assert match.similarity_score >= 85.0
    assert "2" in match.answer
    assert match.category == QuestionCategory.EXPERIENCE


def test_experience_matches_exact_technologies(engine: QuestionAnswerEngine) -> None:
    match_nest = engine.find_answer("¿Cuántos años de experiencia tienes con NestJS?")
    assert match_nest.is_confident_match is True
    assert "1" in match_nest.answer

    match_js = engine.find_answer("Experiencia con JavaScript")
    assert match_js.is_confident_match is True
    assert "3" in match_js.answer


def test_experience_floor_rule_for_unknown_tech(engine: QuestionAnswerEngine) -> None:
    # Tech not explicitly in profile (e.g. Flutter, Ruby) must return floor = 1, never 0
    match = engine.find_answer("¿Cuántos años de experiencia tienes con Flutter?", is_numeric_input=True)

    assert match.is_confident_match is True
    assert match.answer == "1"
    assert match.category == QuestionCategory.EXPERIENCE


def test_salary_detection_cop_explicit(engine: QuestionAnswerEngine) -> None:
    match = engine.find_answer("¿Cuál es tu expectativa salarial mensual en pesos colombianos?")

    assert match.is_confident_match is True
    assert match.category == QuestionCategory.SALARY_COP
    assert "3800000" in match.answer.replace(".", "").replace(",", "")


def test_salary_detection_usd_explicit(engine: QuestionAnswerEngine) -> None:
    match = engine.find_answer("What is your expected monthly salary in USD?")

    assert match.is_confident_match is True
    assert match.category == QuestionCategory.SALARY_USD
    assert "1500" in match.answer


def test_salary_currency_inferred_from_portal(engine: QuestionAnswerEngine) -> None:
    # Ambiguous question: portal GetOnBrd infers USD
    match_getonbrd = engine.find_answer("¿Cuál es tu aspiración salarial?", portal=PortalName.GETONBRD)
    assert match_getonbrd.category == QuestionCategory.SALARY_USD
    assert "1500" in match_getonbrd.answer

    # Ambiguous question: portal Computrabajo infers COP
    match_computrabajo = engine.find_answer("¿Cuál es tu aspiración salarial?", portal=PortalName.COMPUTRABAJO)
    assert match_computrabajo.category == QuestionCategory.SALARY_COP
    assert "3800000" in match_computrabajo.answer.replace(".", "").replace(",", "")


def test_numeric_input_clean_formatting(engine: QuestionAnswerEngine) -> None:
    # For HTML <input type="number">, must return only digits
    match_salary_cop = engine.find_answer("Expectativa salarial (COP)", is_numeric_input=True)
    assert match_salary_cop.answer == "3800000"

    match_salary_usd = engine.find_answer("Salary expectation in USD", is_numeric_input=True)
    assert match_salary_usd.answer == "1500"

    match_exp = engine.find_answer("Años de experiencia con PostgreSQL", is_numeric_input=True)
    assert match_exp.answer == "2"


def test_ats_knockout_residency_and_visa_questions(engine: QuestionAnswerEngine) -> None:
    match_residency = engine.find_answer("¿Resides en Barranquilla / Colombia?")
    assert match_residency.is_confident_match is True
    assert match_residency.answer in {"Sí", "Yes"}

    match_permit = engine.find_answer("¿Cuentas con permiso legal para trabajar en Colombia?")
    assert match_permit.is_confident_match is True
    assert match_permit.answer in {"Sí", "Yes"}

    match_visa = engine.find_answer("¿Requieres patrocinio de visa para trabajar remoto?")
    assert match_visa.is_confident_match is True
    assert match_visa.answer == "No"

    match_notice = engine.find_answer("¿Disponibilidad de incorporación?")
    assert match_notice.is_confident_match is True
    assert "Inmediata" in match_notice.answer


def test_user_confirmed_answer_has_absolute_priority(engine: QuestionAnswerEngine) -> None:
    # 1. First query matches initial profile seed
    match_init = engine.find_answer("¿Cuántos años de experiencia tienes con React?")
    assert match_init.source == AnswerSource.PROFILE_SEED

    # 2. User confirms a customized answer
    engine.add_qa_entry(
        raw_question="¿Cuántos años de experiencia tienes con React?",
        answer="3 años liderando arquitectura frontend",
        category=QuestionCategory.EXPERIENCE,
        source=AnswerSource.USER_CONFIRMED,
    )

    # 3. Next query must return the user-confirmed answer
    match_updated = engine.find_answer("¿Cuántos años de experiencia tienes con React?")
    assert match_updated.answer == "3 años liderando arquitectura frontend"
    assert match_updated.source == AnswerSource.USER_CONFIRMED
    assert match_updated.similarity_score == 100.0


def test_unrelated_question_yields_unconfident_match(engine: QuestionAnswerEngine) -> None:
    match = engine.find_answer("¿Cuál es tu color favorito de corbata para la oficina?")

    assert match.is_confident_match is False
    assert match.similarity_score < 85.0


def test_sqlite_repository_persistence_and_hydration(sample_profile: CandidateProfile) -> None:
    repo = ApplicationRepository(":memory:")

    # 1. Engine 1 persists seeds to SQLite
    engine1 = QuestionAnswerEngine(profile=sample_profile, repository=repo)
    persisted_count = engine1.persist_seeds()
    assert persisted_count > 0

    all_db_qa = repo.get_all_qa_memory()
    assert len(all_db_qa) == persisted_count

    # 2. Engine 2 is created and hydrates from the same SQLite database
    engine2 = QuestionAnswerEngine(profile=None, repository=repo)
    match = engine2.find_answer("¿Cuántos años de experiencia tienes con React?")
    assert match.is_confident_match is True
    assert "2" in match.answer


def test_load_candidate_profile_from_example_yaml() -> None:
    profile = load_candidate_profile("config/profile.example.yaml")

    assert profile.personal.full_name == "Alejandro Gómez"
    assert profile.personal.city == "Barranquilla"
    assert profile.salary.cop_monthly == 3800000
    assert profile.salary.usd_monthly == 1500
    assert profile.get_experience_years("React") == 2
    assert profile.get_experience_years("TecnologiaInexistente") == 1
