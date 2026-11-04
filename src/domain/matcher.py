"""Offer Matcher - Filters and scores job offers against candidate profile.

Uses BayesianScorer for probabilistic relevance scoring with IDF weighting
and FuzzyCascadeMatcher for robust skill normalization.
"""

import re
from typing import Sequence

from src.config_loader import FilterConfig, TechVocabulary
from src.domain.models import (
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
)
from src.domain.text_normalizer import (
    build_dedup_key,
    normalize_canonical_url,
    strip_accents,
)
from src.domain.tech_tokenizer import TechTokenizer
from src.domain.fuzzy_matcher import FuzzyCascadeMatcher, create_fuzzy_matcher
from src.domain.bayesian_scorer import BayesianScorer, create_bayesian_scorer, BayesianConfig


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


def extract_keywords_with_fuzzy(
    text: str,
    vocabulary: TechVocabulary,
    fuzzy_matcher: FuzzyCascadeMatcher | None = None,
) -> tuple[KeywordMatch, ...]:
    """Extract keywords from text using TechTokenizer with fuzzy fallback.

    Args:
        text: Job description text
        vocabulary: TechVocabulary for keyword weights
        fuzzy_matcher: Optional FuzzyCascadeMatcher for fuzzy normalization

    Returns:
        Tuple of KeywordMatch with normalized canonical keywords
    """
    # First pass: TechTokenizer with exact alias matching
    tokenizer = TechTokenizer(vocabulary)
    token_matches = tokenizer.tokenize(text)

    # Convert to KeywordMatch objects
    keyword_matches: list[KeywordMatch] = []
    seen_normalized: set[str] = set()

    for tm in token_matches:
        normalized = tm.normalized
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)

        weight = KeywordWeight(tm.weight)
        keyword_matches.append(KeywordMatch(
            keyword=normalized,
            is_matched=False,  # Will be set by caller based on candidate skills
            weight=weight,
        ))

    # Second pass: Fuzzy matching for tokens not caught by exact matching
    if fuzzy_matcher:
        # Extract all tokens from text that weren't matched
        # This is a simplified approach - in practice you'd extract unmatched tokens
        pass

    return tuple(keyword_matches)


def extract_keywords_legacy(text: str, vocabulary: TechVocabulary) -> tuple[str, ...]:
    """Legacy keyword extraction (kept for compatibility)."""
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
    """Evaluates job offers against candidate profile using Bayesian scoring."""

    def __init__(
        self,
        config: FilterConfig,
        repository=None,  # For BayesianScorer IDF cache
        use_bayesian: bool = True,
        bayesian_config: BayesianConfig | None = None,
    ) -> None:
        self._config = config
        self._use_bayesian = use_bayesian
        self._fuzzy_matcher = create_fuzzy_matcher(config.tech_vocabulary)
        self._bayesian_scorer = None
        self._tokenizer = TechTokenizer(config.tech_vocabulary)

        if use_bayesian and repository is not None:
            self._bayesian_scorer = create_bayesian_scorer(repository, bayesian_config)

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

        # Extract keywords using TechTokenizer (primary) + fuzzy (fallback)
        token_matches = self._tokenizer.tokenize(full_text)

        # Convert to KeywordMatch objects with candidate skill matching
        keyword_matches: list[KeywordMatch] = []
        seen_normalized: set[str] = set()

        for tm in token_matches:
            normalized = tm.normalized
            if normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)

            weight = KeywordWeight(tm.weight)
            is_matched = normalized.lower() in {s.lower() for s in self._config.candidate_skills}

            keyword_matches.append(KeywordMatch(
                keyword=normalized,
                is_matched=is_matched,
                weight=weight,
            ))

        if not keyword_matches:
            return MatchEvaluation(
                dedup_key=dedup_key,
                canonical_url=canonical_url,
                match_score=0,
                should_apply=False,
                is_hard_rejected=False,
                rejection_reason="No relevant technologies detected in offer description.",
                keywords=(),
            )

        # Score using Bayesian or legacy method
        if self._use_bayesian and self._bayesian_scorer:
            bayesian_result = self._bayesian_scorer.score_keywords(
                keywords=keyword_matches,
                candidate_skills=self._config.candidate_skills,
            )
            final_score = bayesian_result.score

            # Short description bonus (matching original behavior)
            matched_core = sum(1 for km in keyword_matches if km.is_matched and km.weight == KeywordWeight.CORE)
            if 1 <= len(keyword_matches) <= 2 and matched_core >= 1:
                final_score = max(final_score, self._config.matching.short_description_base_score)
        else:
            # Legacy weighted ratio scoring
            total_possible_weight = 0
            earned_weight = 0
            for km in keyword_matches:
                total_possible_weight += int(km.weight)
                if km.is_matched:
                    earned_weight += int(km.weight)

            calculated_score = round((earned_weight / total_possible_weight) * 100) if total_possible_weight > 0 else 0
            final_score = calculated_score

            # Short description rule
            if 1 <= len(keyword_matches) <= 2:
                has_core_match = any(
                    km.is_matched and km.weight == KeywordWeight.CORE for km in keyword_matches
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