"""Fuzzy Cascade Matcher - 4-level progressive matching for skill normalization.

Implements Priority 2 from v2.0 architecture:
1. Exact canonical match (O(1) dict lookup)
2. Template patterns (pre-compiled regex for common variations)
3. RapidFuzz token_set_ratio (>= 85% threshold)
4. Embedding similarity (optional, for semantic matching)

Designed for O(n) average case with early exit on high-confidence matches.
"""

import re
from dataclasses import dataclass
from typing import Any, Sequence

try:
    from rapidfuzz import fuzz as _fuzz, utils as _utils
    RAPIDFUZZ_AVAILABLE = True
    fuzz: Any = _fuzz
    utils: Any = _utils
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    fuzz = None
    utils = None

from src.domain.models import KeywordWeight
from src.config_loader import TechVocabulary


@dataclass(frozen=True, slots=True)
class FuzzyMatchResult:
    """Result of fuzzy matching a keyword to vocabulary."""
    matched: bool
    canonical_keyword: str
    confidence: float        # 0.0 - 1.0
    level: int              # 1=exact, 2=template, 3=rapidfuzz, 4=embedding
    weight: KeywordWeight
    matched_variation: str | None = None


@dataclass(frozen=True, slots=True)
class TemplatePattern:
    """Pre-compiled template pattern for common skill variations."""
    pattern: re.Pattern[str]
    canonical: str
    weight: KeywordWeight
    confidence: float = 0.95  # High confidence for known patterns


# ============================================================================
# LEVEL 1: Exact Canonical Match (O(1) dictionary lookup)
# ============================================================================

def build_exact_lookup(vocabulary: TechVocabulary) -> dict[str, tuple[str, KeywordWeight]]:
    """Build O(1) lookup from normalized keyword to (canonical, weight)."""
    lookup: dict[str, tuple[str, KeywordWeight]] = {}
    for canonical in vocabulary.get_all_keywords():
        weight = vocabulary.get_weight(canonical)
        # Primary canonical form
        lookup[canonical.lower()] = (canonical, weight)
        # Also register all known aliases
        for alias in vocabulary.get_aliases(canonical):
            lookup[alias.lower()] = (canonical, weight)
    return lookup


def match_exact(
    token: str,
    exact_lookup: dict[str, tuple[str, KeywordWeight]],
) -> FuzzyMatchResult | None:
    """Level 1: Exact dictionary lookup."""
    normalized = token.lower().strip()
    if normalized in exact_lookup:
        canonical, weight = exact_lookup[normalized]
        return FuzzyMatchResult(
            matched=True,
            canonical_keyword=canonical,
            confidence=1.0,
            level=1,
            weight=weight,
            matched_variation=token,
        )
    return None


# ============================================================================
# LEVEL 2: Template Patterns (Pre-compiled regex for common variations)
# ============================================================================

def build_template_patterns(vocabulary: TechVocabulary) -> list[TemplatePattern]:
    """Build pre-compiled regex patterns for common skill variations.

    These handle known abbreviations, case variations, and common typos
    that exact matching would miss.
    """
    patterns: list[TemplatePattern] = []

    # Core technology patterns with common variations
    template_defs = [
        # JavaScript ecosystem
        (r"^(?:js|javascript|ecmascript)$", "javascript", KeywordWeight.CORE, 0.98),
        (r"^(?:ts|typescript)$", "typescript", KeywordWeight.CORE, 0.98),
        (r"^(?:node|nodejs|node\.js)$", "node.js", KeywordWeight.CORE, 0.98),
        (r"^(?:react|reactjs|react\.js)$", "react", KeywordWeight.CORE, 0.98),
        (r"^(?:next|nextjs|next\.js)$", "next.js", KeywordWeight.CORE, 0.95),
        (r"^(?:nest|nestjs|nest\.js)$", "nestjs", KeywordWeight.CORE, 0.95),
        (r"^(?:vue|vuejs|vue\.js)$", "vue.js", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:angular|angularjs|angular\.js)$", "angular", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:svelte|sveltekit)$", "svelte", KeywordWeight.SECONDARY, 0.95),

        # Python ecosystem
        (r"^(?:py|python3?)$", "python", KeywordWeight.CORE, 0.98),
        (r"^(?:django|djangorest|drf)$", "django", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:flask|flaskrest)$", "flask", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:fastapi|starlette)$", "fastapi", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:pandas|pd)$", "pandas", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:numpy|np)$", "numpy", KeywordWeight.SECONDARY, 0.9),

        # Databases
        (r"^(?:postgres|postgresql|psql)$", "postgresql", KeywordWeight.CORE, 0.98),
        (r"^(?:mysql|mariadb)$", "mysql", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:mongo|mongodb)$", "mongodb", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:redis|rediscache)$", "redis", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:sql|sqlserver|mssql|tsql)$", "sql server", KeywordWeight.SECONDARY, 0.9),

        # Cloud & DevOps
        (r"^(?:aws|amazon web services)$", "aws", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:gcp|google cloud|google cloud platform)$", "gcp", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:azure|microsoft azure)$", "azure", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:docker|container)$", "docker", KeywordWeight.CORE, 0.95),
        (r"^(?:k8s|kubernetes|kube)$", "kubernetes", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:ci[/-]?cd|cicd|jenkins|gitlab ci|github actions)$", "ci/cd", KeywordWeight.SECONDARY, 0.9),

        # Languages
        (r"^(?:c#|csharp|dotnet|csharp\.net)$", "c#", KeywordWeight.CORE, 0.98),
        (r"^(?:\.net|dotnet|netcore|aspnet)$", ".net", KeywordWeight.CORE, 0.98),
        (r"^(?:java|openjdk)$", "java", KeywordWeight.CORE, 0.98),
        (r"^(?:go|golang)$", "go", KeywordWeight.SECONDARY, 0.95),
        (r"^(?:rust|rs)$", "rust", KeywordWeight.SECONDARY, 0.9),

        # Testing
        (r"^(?:jest|vitest|testing library)$", "jest", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:pytest|py\.test)$", "pytest", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:cypress|playwright|e2e)$", "cypress", KeywordWeight.SECONDARY, 0.9),

        # Architecture
        (r"^(?:microservices?|micro services?)$", "microservices", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:rest|restful|rest api)$", "rest", KeywordWeight.SECONDARY, 0.85),
        (r"^(?:graphql|gql)$", "graphql", KeywordWeight.SECONDARY, 0.9),
        (r"^(?:event driven|event driven architecture)$", "event driven", KeywordWeight.BONUS, 0.85),
    ]

    vocab_by_lower: dict[str, str] = {kw.lower(): kw for kw in vocabulary.get_all_keywords()}
    for kw in vocabulary.get_all_keywords():
        for alias in vocabulary.get_aliases(kw):
            vocab_by_lower.setdefault(alias.lower(), kw)

    for pattern_str, canonical, _default_weight, confidence in template_defs:
        # Only add if the canonical is in vocabulary
        matched_canonical = vocab_by_lower.get(canonical.lower())
        if matched_canonical is not None:
            actual_weight = vocabulary.get_weight(matched_canonical)
            patterns.append(TemplatePattern(
                pattern=re.compile(pattern_str, re.IGNORECASE),
                canonical=matched_canonical,
                weight=actual_weight,
                confidence=confidence,
            ))

    return patterns


def match_templates(
    token: str,
    template_patterns: list[TemplatePattern],
) -> FuzzyMatchResult | None:
    """Level 2: Template pattern matching."""
    normalized = token.lower().strip()
    for tmpl in template_patterns:
        if tmpl.pattern.fullmatch(normalized):
            return FuzzyMatchResult(
                matched=True,
                canonical_keyword=tmpl.canonical,
                confidence=tmpl.confidence,
                level=2,
                weight=tmpl.weight,
                matched_variation=token,
            )
    return None


# ============================================================================
# LEVEL 3: RapidFuzz Token Set Ratio (>= 85% threshold)
# ============================================================================

def match_rapidfuzz(
    token: str,
    vocabulary: TechVocabulary,
    threshold: int = 85,
) -> FuzzyMatchResult | None:
    """Level 3: Fuzzy matching using RapidFuzz token_set_ratio.

    Token set ratio is ideal for skill matching because it handles:
    - Word order differences: "react native" vs "native react"
    - Extra words: "react js developer" vs "react"
    - Partial matches: "postgresql database" vs "postgresql"
    """
    if not RAPIDFUZZ_AVAILABLE or fuzz is None or utils is None:
        return None

    normalized = token.lower().strip()
    if len(normalized) < 3:  # Too short for meaningful fuzzy match
        return None

    best_match: tuple[str, KeywordWeight, int] | None = None
    best_score = 0

    for canonical in vocabulary.get_all_keywords():
        weight = vocabulary.get_weight(canonical)
        # Token set ratio handles word reordering and extra tokens
        score = fuzz.token_set_ratio(
            normalized,
            canonical.lower(),
            processor=utils.default_process,
            score_cutoff=threshold,
        )
        score_int = int(round(score))
        if score_int >= threshold and score_int > best_score:
            best_score = score_int
            best_match = (canonical, weight, score_int)

    if best_match:
        canonical, weight, score_int = best_match
        # Confidence scales with score: 85% -> 0.7, 100% -> 0.95
        confidence = 0.5 + (score_int - 85) * 0.45 / 15
        return FuzzyMatchResult(
            matched=True,
            canonical_keyword=canonical,
            confidence=confidence,
            level=3,
            weight=weight,
            matched_variation=token,
        )

    return None


# ============================================================================
# LEVEL 4: Embedding Similarity (Optional - placeholder for future)
# ============================================================================

def match_embeddings(
    token: str,
    vocabulary: TechVocabulary,
    threshold: float = 0.82,
) -> FuzzyMatchResult | None:
    """Level 4: Semantic embedding similarity (placeholder).

    This would use sentence transformers or similar to match
    semantically related skills (e.g., "k8s" ~ "kubernetes" ~ "container orchestration").
    Currently returns None - requires embedding model integration.
    """
    # TODO: Integrate sentence-transformers or similar
    # For now, this level is skipped
    return None


# ============================================================================
# MAIN CASCADE MATCHER
# ============================================================================

class FuzzyCascadeMatcher:
    """4-level cascade matcher for technology skill normalization.

    Matching priority (early exit on high confidence):
    1. Exact canonical/alias lookup (confidence 1.0)
    2. Template regex patterns (confidence ~0.95)
    3. RapidFuzz token_set_ratio >= 85% (confidence 0.7-0.95)
    4. Embedding similarity >= 0.82 (confidence 0.8-0.95)

    Average case O(1) for known skills, O(vocab) worst case.
    """

    def __init__(
        self,
        vocabulary: TechVocabulary,
        rapidfuzz_threshold: int = 85,
        embedding_threshold: float = 0.82,
        enable_embeddings: bool = False,
    ) -> None:
        self.vocabulary = vocabulary
        self.rapidfuzz_threshold = rapidfuzz_threshold
        self.embedding_threshold = embedding_threshold
        self.enable_embeddings = enable_embeddings

        # Pre-build lookup structures
        self._exact_lookup = build_exact_lookup(vocabulary)
        self._template_patterns = build_template_patterns(vocabulary)

    def match(self, token: str) -> FuzzyMatchResult | None:
        """Match a single token through the cascade."""
        # Level 1: Exact match (fastest)
        result = match_exact(token, self._exact_lookup)
        if result:
            return result

        # Level 2: Template patterns
        result = match_templates(token, self._template_patterns)
        if result:
            return result

        # Level 3: RapidFuzz
        result = match_rapidfuzz(token, self.vocabulary, self.rapidfuzz_threshold)
        if result:
            return result

        # Level 4: Embeddings (optional)
        if self.enable_embeddings:
            result = match_embeddings(token, self.vocabulary, self.embedding_threshold)
            if result:
                return result

        return None

    def match_all(self, tokens: Sequence[str]) -> list[FuzzyMatchResult]:
        """Match multiple tokens, returning only successful matches."""
        results = []
        for token in tokens:
            match = self.match(token)
            if match:
                results.append(match)
        return results

    def get_canonical_keywords(self, tokens: Sequence[str]) -> list[str]:
        """Extract canonical keywords from tokens (for TechTokenizer integration)."""
        matches = self.match_all(tokens)
        # Deduplicate by canonical keyword, keep highest confidence
        best_by_canonical: dict[str, FuzzyMatchResult] = {}
        for match in matches:
            existing = best_by_canonical.get(match.canonical_keyword)
            if not existing or match.confidence > existing.confidence:
                best_by_canonical[match.canonical_keyword] = match
        return list(best_by_canonical.keys())


def create_fuzzy_matcher(vocabulary: TechVocabulary) -> FuzzyCascadeMatcher:
    """Factory function to create configured FuzzyCascadeMatcher."""
    return FuzzyCascadeMatcher(vocabulary)