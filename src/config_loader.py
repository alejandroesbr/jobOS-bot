from dataclasses import dataclass
from pathlib import Path
import yaml

from src.domain.models import KeywordWeight


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

