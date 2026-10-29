from dataclasses import dataclass
from pathlib import Path
import yaml

from src.domain.models import (
    CandidatePersonalInfo,
    CandidatePreferences,
    CandidateProfile,
    CandidateSalary,
    KeywordWeight,
)


@dataclass(frozen=True, slots=True)
class MatchingRules:
    min_match_score: int = 40
    reapply_cooldown_days: int = 3
    short_description_base_score: int = 65


@dataclass(frozen=True, slots=True)
class TechVocabulary:
    core: tuple[str, ...]
    secondary: tuple[str, ...]
    bonus: tuple[str, ...]

    def get_weight(self, keyword: str) -> KeywordWeight:
        keyword_lower = keyword.lower()
        if any(keyword_lower == k.lower() for k in self.core):
            return KeywordWeight.CORE
        if any(keyword_lower == k.lower() for k in self.secondary):
            return KeywordWeight.SECONDARY
        return KeywordWeight.BONUS


@dataclass(frozen=True, slots=True)
class FilterConfig:
    matching: MatchingRules
    candidate_skills: frozenset[str]
    title_blacklist: tuple[str, ...]
    title_whitelist: tuple[str, ...]
    company_blacklist: tuple[str, ...]
    location_whitelist: tuple[str, ...]
    tech_vocabulary: TechVocabulary


def _extract_string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    items = data.get(key, [])
    if not isinstance(items, list):
        return ()
    return tuple(str(item).strip() for item in items if str(item).strip())


def load_filter_config(config_path: Path | str = "config/filters.yaml") -> FilterConfig:
    path = Path(config_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found at: {path}")

    with path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file)

    if not isinstance(raw_data, dict):
        raise ValueError(f"Invalid configuration format in {path}: expected dictionary root.")

    matching_raw = raw_data.get("matching", {})
    matching_dict = matching_raw if isinstance(matching_raw, dict) else {}
    matching = MatchingRules(
        min_match_score=int(matching_dict.get("min_match_score", 40)),
        reapply_cooldown_days=int(matching_dict.get("reapply_cooldown_days", 3)),
        short_description_base_score=int(matching_dict.get("short_description_base_score", 65)),
    )

    profile_raw = raw_data.get("candidate_profile", {})
    skills_list = profile_raw.get("skills", []) if isinstance(profile_raw, dict) else []
    candidate_skills = frozenset(str(s).strip().lower() for s in skills_list if str(s).strip())

    vocab_raw = raw_data.get("tech_vocabulary", {})
    vocab_dict = vocab_raw if isinstance(vocab_raw, dict) else {}

    core_raw = vocab_dict.get("core", {})
    secondary_raw = vocab_dict.get("secondary", {})
    bonus_raw = vocab_dict.get("bonus", {})

    core_items = core_raw.get("keywords", []) if isinstance(core_raw, dict) else []
    secondary_items = secondary_raw.get("keywords", []) if isinstance(secondary_raw, dict) else []
    bonus_items = bonus_raw.get("keywords", []) if isinstance(bonus_raw, dict) else []

    tech_vocabulary = TechVocabulary(
        core=tuple(str(k).strip() for k in core_items if str(k).strip()),
        secondary=tuple(str(k).strip() for k in secondary_items if str(k).strip()),
        bonus=tuple(str(k).strip() for k in bonus_items if str(k).strip()),
    )

    return FilterConfig(
        matching=matching,
        candidate_skills=candidate_skills,
        title_blacklist=_extract_string_tuple(raw_data, "title_blacklist"),
        title_whitelist=_extract_string_tuple(raw_data, "title_whitelist"),
        company_blacklist=_extract_string_tuple(raw_data, "company_blacklist"),
        location_whitelist=_extract_string_tuple(raw_data, "location_whitelist"),
        tech_vocabulary=tech_vocabulary,
    )


def load_candidate_profile(config_path: Path | str = "config/profile.yaml") -> CandidateProfile:
    path = Path(config_path)
    if not path.is_file():
        fallback_path = path.parent / "profile.example.yaml"
        if fallback_path.is_file():
            path = fallback_path
        else:
            raise FileNotFoundError(
                f"Candidate profile configuration file not found at: {path} (fallback: {fallback_path})"
            )

    with path.open("r", encoding="utf-8") as file:
        raw_data = yaml.safe_load(file)

    if not isinstance(raw_data, dict):
        raise ValueError(f"Invalid profile format in {path}: expected dictionary root.")

    personal_raw = raw_data.get("personal", {})
    personal_dict = personal_raw if isinstance(personal_raw, dict) else {}
    personal = CandidatePersonalInfo(
        full_name=str(personal_dict.get("full_name", "")),
        email=str(personal_dict.get("email", "")),
        phone=str(personal_dict.get("phone", "")),
        city=str(personal_dict.get("city", "")),
        country=str(personal_dict.get("country", "")),
        linkedin_url=str(personal_dict.get("linkedin_url", "")),
        github_url=str(personal_dict.get("github_url", "")),
        portfolio_url=str(personal_dict.get("portfolio_url", "")),
    )

    pref_raw = raw_data.get("preferences", {})
    pref_dict = pref_raw if isinstance(pref_raw, dict) else {}
    preferences = CandidatePreferences(
        residency=str(pref_dict.get("residency", "Barranquilla, Colombia")),
        colombia_work_permit=bool(pref_dict.get("colombia_work_permit", True)),
        requires_visa_sponsorship=bool(pref_dict.get("requires_visa_sponsorship", False)),
        remote_availability=bool(pref_dict.get("remote_availability", True)),
        hybrid_availability=bool(pref_dict.get("hybrid_availability", True)),
        notice_period=str(pref_dict.get("notice_period", "Inmediata")),
        english_level=str(pref_dict.get("english_level", "B2")),
    )

    salary_raw = raw_data.get("salary", {})
    salary_dict = salary_raw if isinstance(salary_raw, dict) else {}
    salary = CandidateSalary(
        cop_monthly=int(salary_dict.get("cop_monthly", 3800000)),
        cop_monthly_min=int(salary_dict.get("cop_monthly_min", 3500000)),
        cop_monthly_max=int(salary_dict.get("cop_monthly_max", 4500000)),
        usd_monthly=int(salary_dict.get("usd_monthly", 1500)),
        usd_monthly_min=int(salary_dict.get("usd_monthly_min", 1200)),
        usd_monthly_max=int(salary_dict.get("usd_monthly_max", 2000)),
    )

    exp_raw = raw_data.get("experience", {})
    exp_dict = exp_raw if isinstance(exp_raw, dict) else {}
    default_floor_years = int(exp_dict.get("default_floor_years", 1))

    tech_dict = exp_dict.get("technologies", {})
    experience_years: dict[str, int] = {}
    if isinstance(tech_dict, dict):
        for tech, years in tech_dict.items():
            experience_years[str(tech)] = int(years)

    return CandidateProfile(
        personal=personal,
        preferences=preferences,
        salary=salary,
        experience_years=experience_years,
        default_floor_years=default_floor_years,
    )
