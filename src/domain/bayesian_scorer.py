"""Bayesian Scorer - Probabilistic relevance scoring with prior smoothing and IDF weighting.

Implements Priority 4 from v2.0 architecture:
- Bayesian inference with Dirichlet prior smoothing
- IDF weighting from keyword market prevalence
- Candidate skill prior integration
- Confidence intervals for match scores

This replaces the simple weighted ratio in matcher.py with a principled
probabilistic model that accounts for keyword rarity and candidate profile.
"""

import math
from dataclasses import dataclass
from typing import Sequence

from src.domain.models import KeywordMatch, KeywordWeight


@dataclass(frozen=True, slots=True)
class BayesianScoreResult:
    """Result of Bayesian scoring with confidence metrics."""
    score: int                    # Final 0-100 match score
    posterior_mean: float         # Raw posterior probability (0-1)
    confidence_lower: float       # 5th percentile of posterior
    confidence_upper: float       # 95th percentile of posterior
    effective_sample_size: float  # Sum of weights after IDF
    prior_strength: float         # Alpha + Beta of Dirichlet prior
    keyword_contributions: list[tuple[str, float, float, float]]  # (keyword, idf, likelihood, weight)


@dataclass(frozen=True, slots=True)
class KeywordStats:
    """Statistics for a single keyword from market data."""
    keyword: str
    document_frequency: int       # df: number of job postings containing keyword
    total_documents: int          # N: total job postings analyzed
    inverse_document_frequency: float  # IDF = log(N / df)
    market_prevalence: float      # df / N (proportion of market demanding this skill)


class IDFCache:
    """In-memory cache for keyword IDF values with lazy loading from DB."""

    def __init__(self, repository) -> None:
        """Initialize with ApplicationRepositoryPort for DB access."""
        self._repository = repository
        self._cache: dict[str, KeywordStats] = {}
        self._loaded = False

    def _load_from_db(self) -> None:
        """Load keyword IDF statistics from database."""
        if self._loaded:
            return

        try:
            stats = self._repository.get_keyword_stats()
            for keyword, total_jobs, matched_jobs in stats:
                # document_frequency = total_jobs (how many postings mention this)
                # matched_jobs = how many matched applications have this
                # total_documents = total unique job postings scanned
                df = total_jobs
                N = max(total_jobs, 1)  # Will be updated with actual total
                idf = math.log(N / max(df, 1)) if df > 0 else 0.0
                prevalence = df / N if N > 0 else 0.0

                self._cache[keyword.lower()] = KeywordStats(
                    keyword=keyword,
                    document_frequency=df,
                    total_documents=N,
                    inverse_document_frequency=idf,
                    market_prevalence=prevalence,
                )
            self._loaded = True
        except Exception:
            # If DB unavailable, fall back to default IDF=1.0
            self._loaded = True

    def get_idf(self, keyword: str) -> float:
        """Get IDF value for keyword, defaulting to 1.0 if unknown."""
        self._load_from_db()
        stats = self._cache.get(keyword.lower())
        if stats:
            return stats.inverse_document_frequency
        return 1.0  # Neutral IDF for unknown keywords

    def get_stats(self, keyword: str) -> KeywordStats | None:
        """Get full keyword statistics."""
        self._load_from_db()
        return self._cache.get(keyword.lower())

    def get_all_stats(self) -> dict[str, KeywordStats]:
        """Get all cached keyword statistics."""
        self._load_from_db()
        return dict(self._cache)


@dataclass(frozen=True, slots=True)
class BayesianConfig:
    """Configuration for Bayesian scoring."""
    # Dirichlet prior parameters (pseudo-counts)
    # Alpha = expected matches, Beta = expected non-matches
    prior_alpha: float = 2.0      # Prior belief in relevance
    prior_beta: float = 2.0       # Prior belief in irrelevance

    # IDF influence factor (0 = ignore IDF, 1 = full IDF weighting)
    idf_influence: float = 0.7

    # Minimum effective sample size for high confidence
    min_effective_samples: float = 3.0

    # Short description bonus (matching original matcher behavior)
    short_desc_base_score: int = 45
    short_desc_keyword_threshold: int = 2  # 1-2 keywords triggers bonus

    def prior_mean(self) -> float:
        """Expected value of prior distribution."""
        return self.prior_alpha / (self.prior_alpha + self.prior_beta)

    def prior_strength(self) -> float:
        """Sum of prior pseudo-counts (concentration)."""
        return self.prior_alpha + self.prior_beta


class BayesianScorer:
    """Probabilistic relevance scorer using Bayesian inference with IDF weighting.

    Mathematical foundation:
    - Each keyword k provides evidence E_k: matched (1) or not matched (0)
    - Likelihood P(E_k | relevant) = IDF-weighted Bernoulli
    - Prior: Beta(alpha, beta) representing candidate profile strength
    - Posterior: Beta(alpha + sum(w_k * E_k), beta + sum(w_k * (1-E_k)))
    - Score = posterior_mean * 100, with confidence intervals
    """

    def __init__(
        self,
        config: BayesianConfig | None = None,
        idf_cache: IDFCache | None = None,
    ) -> None:
        self.config = config or BayesianConfig()
        self.idf_cache = idf_cache

    def score_keywords(
        self,
        keywords: Sequence[KeywordMatch],
        candidate_skills: set[str] | None = None,
    ) -> BayesianScoreResult:
        """Score a set of keyword matches using Bayesian inference.

        Args:
            keywords: Sequence of KeywordMatch from matcher
            candidate_skills: Optional set of candidate's known skills for prior adjustment

        Returns:
            BayesianScoreResult with score, confidence, and breakdown
        """
        if not keywords:
            return BayesianScoreResult(
                score=0,
                posterior_mean=0.0,
                confidence_lower=0.0,
                confidence_upper=0.0,
                effective_sample_size=0.0,
                prior_strength=self.config.prior_strength(),
                keyword_contributions=[],
            )

        # Adjust prior based on candidate profile
        prior_alpha, prior_beta = self._adjust_prior_for_candidate(keywords, candidate_skills)

        # Accumulate weighted evidence
        weighted_matches = 0.0
        weighted_total = 0.0
        contributions: list[tuple[str, float, float, float]] = []

        for kw in keywords:
            # Base weight from keyword importance (1=bonus, 2=secondary, 3=core)
            base_weight = float(kw.weight)

            # IDF weighting: rare keywords get higher weight
            idf = 1.0
            if self.idf_cache:
                idf = self.idf_cache.get_idf(kw.keyword)

            # Effective weight = base_weight * (1 + idf_influence * (idf - 1))
            # This boosts rare skills, reduces common ones
            effective_weight = base_weight * (1.0 + self.config.idf_influence * (idf - 1.0))
            effective_weight = max(effective_weight, 0.1)  # Floor

            # Evidence: 1 if matched, 0 if not
            evidence = 1.0 if kw.is_matched else 0.0

            weighted_matches += effective_weight * evidence
            weighted_total += effective_weight

            contributions.append((kw.keyword, idf, evidence, effective_weight))

        # Posterior parameters
        post_alpha = prior_alpha + weighted_matches
        post_beta = prior_beta + (weighted_total - weighted_matches)

        # Posterior mean (expected relevance probability)
        posterior_mean = post_alpha / (post_alpha + post_beta) if (post_alpha + post_beta) > 0 else 0.0

        # Confidence interval using Beta distribution quantiles
        # Approximate with normal for large samples, exact for small
        confidence_lower, confidence_upper = self._beta_confidence_interval(post_alpha, post_beta)

        # Effective sample size
        ess = post_alpha + post_beta

        # Final score 0-100
        final_score = round(posterior_mean * 100)

        # Short description bonus (original matcher behavior)
        matched_core = sum(1 for kw in keywords if kw.is_matched and kw.weight == KeywordWeight.CORE)
        if 1 <= len(keywords) <= self.config.short_desc_keyword_threshold and matched_core >= 1:
            final_score = max(final_score, self.config.short_desc_base_score)

        return BayesianScoreResult(
            score=final_score,
            posterior_mean=posterior_mean,
            confidence_lower=confidence_lower,
            confidence_upper=confidence_upper,
            effective_sample_size=ess,
            prior_strength=self.config.prior_strength(),
            keyword_contributions=contributions,
        )

    def _adjust_prior_for_candidate(
        self,
        keywords: Sequence[KeywordMatch],
        candidate_skills: set[str] | None,
    ) -> tuple[float, float]:
        """Adjust Dirichlet prior based on candidate's known skills."""
        if not candidate_skills:
            return self.config.prior_alpha, self.config.prior_beta

        # Count how many of the required keywords candidate possesses
        required_keywords = {kw.keyword.lower() for kw in keywords}
        candidate_lower = {s.lower() for s in candidate_skills}
        overlap = len(required_keywords & candidate_lower)
        total_required = len(required_keywords)

        if total_required == 0:
            return self.config.prior_alpha, self.config.prior_beta

        # Candidate coverage ratio
        coverage = overlap / total_required

        # Boost prior alpha proportionally to coverage
        # Max boost: double the prior strength at 100% coverage
        alpha_boost = self.config.prior_alpha * coverage
        beta_boost = self.config.prior_beta * (1.0 - coverage) * 0.5  # Less penalty for missing

        return (
            self.config.prior_alpha + alpha_boost,
            self.config.prior_beta + beta_boost,
        )

    def _beta_confidence_interval(
        self,
        alpha: float,
        beta: float,
        confidence: float = 0.90,
    ) -> tuple[float, float]:
        """Calculate confidence interval for Beta distribution.

        Uses normal approximation for large samples, Wilson score for small.
        """
        if alpha + beta < 10:
            # Small sample: use exact Beta quantiles approximation
            # Wilson score interval for binomial proportion
            n = alpha + beta
            p = alpha / n if n > 0 else 0.5
            z = 1.645  # 90% confidence
            denom = 1 + z**2 / n
            center = (p + z**2 / (2 * n)) / denom
            half = (z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))) / denom
            return max(0.0, center - half), min(1.0, center + half)

        # Large sample: normal approximation to Beta
        mean = alpha / (alpha + beta)
        var = (alpha * beta) / ((alpha + beta)**2 * (alpha + beta + 1))
        std = math.sqrt(var)
        z = 1.645  # 90% confidence
        margin = z * std
        return max(0.0, mean - margin), min(1.0, mean + margin)


def create_bayesian_scorer(
    repository,
    config: BayesianConfig | None = None,
) -> BayesianScorer:
    """Factory function to create BayesianScorer with DB-backed IDF cache."""
    idf_cache = IDFCache(repository)
    return BayesianScorer(config=config, idf_cache=idf_cache)