import re
from typing import Sequence

from src.config_loader import FilterConfig, TechVocabulary
from src.domain.models import (
    JobOffer,
    KeywordMatch,
    MatchEvaluation,
)
from src.domain.text_normalizer import (
    build_dedup_key,
    normalize_canonical_url,
    strip_accents,
)

SPECIAL_KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {
    "c#": re.compile(r"(?:^|[^\w])c#(?=[^\w]|$)", re.IGNORECASE),
    ".net": re.compile(r"(?:^|[^\w])\.net(?=[^\w]|$)", re.IGNORECASE),
    "node.js": re.compile(r"\bnode(?:\.js)?\b", re.IGNORECASE),
    "react": re.compile(r"\breact(?:\.js)?\b", re.IGNORECASE),
    "next.js": re.compile(r"\bnext(?:\.js)?\b", re.IGNORECASE),
    "nestjs": re.compile(r"\bnest(?:\.js)?\b", re.IGNORECASE),
    "typescript": re.compile(r"\btypescript\b|(?<![\./])\bts\b", re.IGNORECASE),
    "javascript": re.compile(r"\bjavascript\b|(?<![\./])\bjs\b", re.IGNORECASE),
    "postgresql": re.compile(r"\bpostgres(?:ql)?\b", re.IGNORECASE),
    "ci/cd": re.compile(r"\bci[/-]cd\b", re.IGNORECASE),
}


def _matches_pattern(text: str, keyword: str) -> bool:
    key_lower = keyword.lower()
    if key_lower in SPECIAL_KEYWORD_PATTERNS:
        return bool(SPECIAL_KEYWORD_PATTERNS[key_lower].search(text))
    escaped = re.escape(keyword)
    pattern = rf"\b{escaped}\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def check_hard_rejects(
    title: str,
    company: str,
    location: str,
    config: FilterConfig,
) -> str | None:
    norm_company = strip_accents(company).lower()
    for blacklisted_co in config.company_blacklist:
        if strip_accents(blacklisted_co).lower() in norm_company:
            return f"Company '{company}' is blacklisted."

    norm_title = strip_accents(title).lower()
    for blacklisted_term in config.title_blacklist:
        term_clean = strip_accents(blacklisted_term).lower()
        if _matches_pattern(norm_title, term_clean):
            return f"Title contains blacklisted term: '{blacklisted_term}'."

    if config.location_whitelist and "any" not in config.location_whitelist:
        norm_loc = strip_accents(location).lower()
        if norm_loc:
            has_valid_loc = any(
                strip_accents(loc).lower() in norm_loc for loc in config.location_whitelist
            )
            if not has_valid_loc:
                return f"Location '{location}' is outside the allowed list."

    return None


def extract_keywords(text: str, vocabulary: TechVocabulary) -> tuple[str, ...]:
    all_keywords: list[str] = list(vocabulary.core) + list(vocabulary.secondary) + list(vocabulary.bonus)
    matched: list[str] = []
    seen: set[str] = set()

    for kw in all_keywords:
        kw_norm = kw.lower()
        if kw_norm in seen:
            continue
        if _matches_pattern(text, kw):
            matched.append(kw)
            seen.add(kw_norm)

    return tuple(matched)


class OfferMatcher:
    def __init__(self, config: FilterConfig) -> None:
        self._config = config

    def evaluate(self, offer: JobOffer) -> MatchEvaluation:
        dedup_key = build_dedup_key(offer.company, offer.title)
        canonical_url = normalize_canonical_url(offer.url)

        rejection_reason = check_hard_rejects(
            title=offer.title,
            company=offer.company,
            location=offer.location,
            config=self._config,
        )

        if rejection_reason is not None:
            return MatchEvaluation(
                dedup_key=dedup_key,
                canonical_url=canonical_url,
                match_score=0,
                should_apply=False,
                is_hard_rejected=True,
                rejection_reason=rejection_reason,
                keywords=(),
            )

        full_text = f"{offer.title}\n{offer.description}"
        detected_keywords = extract_keywords(full_text, self._config.tech_vocabulary)

        if not detected_keywords:
            return MatchEvaluation(
                dedup_key=dedup_key,
                canonical_url=canonical_url,
                match_score=0,
                should_apply=False,
                is_hard_rejected=False,
                rejection_reason="No relevant technologies detected in offer description.",
                keywords=(),
            )

        keyword_matches: list[KeywordMatch] = []
        total_possible_weight = 0
        earned_weight = 0

        for kw in detected_keywords:
            weight = self._config.tech_vocabulary.get_weight(kw)
            is_matched = kw.lower() in self._config.candidate_skills
            keyword_matches.append(KeywordMatch(keyword=kw, is_matched=is_matched, weight=weight))
            total_possible_weight += int(weight)
            if is_matched:
                earned_weight += int(weight)

        calculated_score = round((earned_weight / total_possible_weight) * 100) if total_possible_weight > 0 else 0

        # Short description rule: if offer mentions 1-2 keywords and at least one is in candidate's Core stack
        final_score = calculated_score
        if 1 <= len(detected_keywords) <= 2:
            has_core_match = any(
                km.is_matched and km.weight == 3 for km in keyword_matches
            )
            if has_core_match:
                final_score = max(calculated_score, self._config.matching.short_description_base_score)

        should_apply = final_score >= self._config.matching.min_match_score

        return MatchEvaluation(
            dedup_key=dedup_key,
            canonical_url=canonical_url,
            match_score=final_score,
            should_apply=should_apply,
            is_hard_rejected=False,
            rejection_reason=None if should_apply else f"Match score ({final_score}%) is below minimum threshold ({self._config.matching.min_match_score}%).",
            keywords=tuple(keyword_matches),
        )
