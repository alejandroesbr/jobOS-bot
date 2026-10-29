from dataclasses import dataclass
from enum import IntEnum, StrEnum


class PortalName(StrEnum):
    LINKEDIN = "linkedin"
    GETONBRD = "getonbrd"
    COMPUTRABAJO = "computrabajo"
    ELEMPLEO = "elempleo"
    GLASSDOOR = "glassdoor"
    INDEED = "indeed"


class WorkModality(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"


class ApplicationStatus(StrEnum):
    PENDING = "Pendiente"
    APPLIED = "Enviado"
    FOLLOW_UP_REQUIRED = "Requiere Seguimiento"
    INTERVIEW_SCHEDULED = "Entrevista Programada"
    OFFER_RECEIVED = "Oferta Recibida"
    REJECTED = "Rechazado"
    DISCARDED = "Descartado"

    def allows_reapplication(self) -> bool:
        return self not in {
            ApplicationStatus.INTERVIEW_SCHEDULED,
            ApplicationStatus.OFFER_RECEIVED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.DISCARDED,
        }


class KeywordWeight(IntEnum):
    BONUS = 1
    SECONDARY = 2
    CORE = 3


class QuestionCategory(StrEnum):
    SALARY_COP = "salary_cop"
    SALARY_USD = "salary_usd"
    EXPERIENCE = "experience"
    LOCATION = "location"
    GENERAL = "general"


class AnswerSource(StrEnum):
    PROFILE_SEED = "profile_seed"
    USER_CONFIRMED = "user_confirmed"


@dataclass(frozen=True, slots=True)
class CandidatePersonalInfo:
    full_name: str
    email: str
    phone: str
    city: str
    country: str
    linkedin_url: str
    github_url: str
    portfolio_url: str


@dataclass(frozen=True, slots=True)
class CandidatePreferences:
    residency: str
    colombia_work_permit: bool
    requires_visa_sponsorship: bool
    remote_availability: bool
    hybrid_availability: bool
    notice_period: str
    english_level: str


@dataclass(frozen=True, slots=True)
class CandidateSalary:
    cop_monthly: int
    cop_monthly_min: int
    cop_monthly_max: int
    usd_monthly: int
    usd_monthly_min: int
    usd_monthly_max: int


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    personal: CandidatePersonalInfo
    preferences: CandidatePreferences
    salary: CandidateSalary
    experience_years: dict[str, int]
    default_floor_years: int = 1

    def get_experience_years(self, tech_name: str) -> int:
        target = tech_name.strip().lower()
        for tech, years in self.experience_years.items():
            if tech.strip().lower() == target:
                return years
        return self.default_floor_years


@dataclass(frozen=True, slots=True)
class JobOffer:
    portal: PortalName
    title: str
    company: str
    location: str
    modality: WorkModality
    url: str
    description: str = ""
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class KeywordMatch:
    keyword: str
    is_matched: bool
    weight: KeywordWeight


@dataclass(frozen=True, slots=True)
class MatchEvaluation:
    dedup_key: str
    canonical_url: str
    match_score: int
    should_apply: bool
    is_hard_rejected: bool
    rejection_reason: str | None
    keywords: tuple[KeywordMatch, ...]

    @property
    def matched_keywords(self) -> tuple[str, ...]:
        return tuple(item.keyword for item in self.keywords if item.is_matched)

    @property
    def missing_keywords(self) -> tuple[str, ...]:
        return tuple(item.keyword for item in self.keywords if not item.is_matched)


@dataclass(frozen=True, slots=True)
class SubmissionAttempt:
    attempt_number: int
    portal: PortalName
    canonical_url: str
    applied_at: str
    external_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    id: int
    dedup_key: str
    title: str
    company: str
    location: str
    modality: WorkModality
    description: str
    match_score: int
    times_applied: int
    status: ApplicationStatus
    first_applied_at: str | None = None
    last_applied_at: str | None = None
    notion_page_id: str | None = None
    cv_tailor_cache: str | None = None
    interview_prep_path: str | None = None
    submissions: tuple[SubmissionAttempt, ...] = ()
    keywords: tuple[KeywordMatch, ...] = ()


@dataclass(frozen=True, slots=True)
class QuestionMatch:
    question_norm: str
    answer: str
    similarity_score: float
    category: QuestionCategory
    source: AnswerSource
    is_confident_match: bool
