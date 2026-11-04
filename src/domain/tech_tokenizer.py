"""
TechTokenizer: O(n) single-pass technology extraction with Aho-Corasick multi-word matching.

This module provides efficient technology tokenization from job descriptions,
preserving special characters (+#.-) within tokens and normalizing via alias maps.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from src.config_loader import DEFAULT_TECH_ALIASES, TechVocabulary as TechVocabulary

try:
    import ahocorasick  # type: ignore[import-not-found]
except ImportError:
    ahocorasick = None


@dataclass(slots=True)
class TokenMatch:
    """Represents a matched technology token with metadata."""
    token: str          # Original matched text from input
    normalized: str     # Canonical form from vocabulary (e.g., "Node.js", "React")
    start: int          # Start index in source text
    end: int            # End index in source text (exclusive)
    weight: int         # 3=CORE, 2=SECONDARY, 1=BONUS


class TechTokenizer:
    """
    Single-pass technology tokenizer using Aho-Corasick for multi-word terms
    and hash lookup for single-word tokens.

    Preserves technology-specific characters (+ # . -) within tokens.
    Normalizes via alias dictionary (e.g., "c#" -> "csharp", "js" -> "javascript").
    """

    # Regex pattern for tokenization: preserves + # . - within words
    TOKEN_PATTERN: re.Pattern[str] = re.compile(r"[a-zA-Z0-9+#.\-]+")

    def __init__(self, vocabulary: TechVocabulary) -> None:
        """
        Initialize tokenizer with a TechVocabulary.

        Args:
            vocabulary: TechVocabulary instance with core/secondary/bonus/multi_word terms
        """
        self.vocabulary = vocabulary
        self._alias_map: dict[str, str] = self._build_alias_map()
        self._canonical_by_norm: dict[str, str] = {}
        for kw in self.vocabulary.get_all_keywords():
            norm = self._normalize(kw)
            if norm and norm not in self._canonical_by_norm:
                self._canonical_by_norm[norm] = kw

        self._multi_word_phrases: list[tuple[str, str]] = self._build_multi_word_phrases()
        self._automaton: Any = None
        self._build_automaton()

    def _build_alias_map(self) -> dict[str, str]:
        """
        Build comprehensive alias map for technology normalization.

        Maps common variants to canonical forms.
        """
        return dict(DEFAULT_TECH_ALIASES)

    def _build_multi_word_phrases(self) -> list[tuple[str, str]]:
        """Collect multi-word and slash-separated phrases mapped to canonical vocab names."""
        phrases: dict[str, str] = {}
        for term in (*self.vocabulary.multi_word, *self.vocabulary.get_all_keywords()):
            low = term.strip().lower()
            if " " in low or "/" in low:
                norm = self._normalize(low)
                canonical = self._canonical_by_norm.get(norm, term)
                phrases[low] = canonical

        for alias, target_norm in self._alias_map.items():
            if (" " in alias or "/" in alias) and target_norm in self._canonical_by_norm:
                phrases[alias] = self._canonical_by_norm[target_norm]

        return list(phrases.items())

    def _build_automaton(self) -> None:
        """Build Aho-Corasick automaton for multi-word term matching."""
        if ahocorasick is None or not self._multi_word_phrases:
            self._automaton = None
            return

        automaton = ahocorasick.Automaton()

        for phrase_lower, canonical in self._multi_word_phrases:
            automaton.add_word(phrase_lower, (phrase_lower, canonical))

        automaton.make_automaton()
        self._automaton = automaton

    def _normalize(self, token: str) -> str:
        """
        Normalize a token using the alias map after stripping boundary punctuation.

        Args:
            token: Raw token to normalize

        Returns:
            Canonical normalized key of the token
        """
        lower = token.strip().lower()
        if lower.startswith(".net"):
            cleaned = lower.rstrip(".-")
        else:
            cleaned = lower.strip(".-")
        if not cleaned:
            return ""
        return self._alias_map.get(cleaned, cleaned)

    def _get_weight(self, normalized: str) -> int:
        """Get weight for a normalized token."""
        return int(self.vocabulary.get_weight(normalized))

    def tokenize(self, text: str) -> list[TokenMatch]:
        """
        Single-pass tokenization of input text.

        Uses hash lookup for single-word tokens and Aho-Corasick (or substring fallback)
        for multi-word terms. Preserves technology characters (+#.-).

        Args:
            text: Input text to tokenize

        Returns:
            List of TokenMatch objects sorted by start position
        """
        if not text:
            return []

        matches: list[TokenMatch] = []
        text_lower = text.lower()

        # 1. Multi-word matching via Aho-Corasick or clean fallback
        if self._automaton is not None:
            for end_idx, (phrase_lower, canonical) in self._automaton.iter(text_lower):
                start_idx = end_idx - len(phrase_lower) + 1
                if self._is_word_boundary(text_lower, start_idx, end_idx + 1):
                    weight = self._get_weight(canonical)
                    matches.append(TokenMatch(
                        token=text[start_idx:end_idx + 1],
                        normalized=canonical,
                        start=start_idx,
                        end=end_idx + 1,
                        weight=weight,
                    ))
        else:
            for phrase_lower, canonical in self._multi_word_phrases:
                search_start = 0
                phrase_len = len(phrase_lower)
                while True:
                    idx = text_lower.find(phrase_lower, search_start)
                    if idx == -1:
                        break
                    end_pos = idx + phrase_len
                    if self._is_word_boundary(text_lower, idx, end_pos):
                        weight = self._get_weight(canonical)
                        matches.append(TokenMatch(
                            token=text[idx:end_pos],
                            normalized=canonical,
                            start=idx,
                            end=end_pos,
                            weight=weight,
                        ))
                    search_start = idx + 1

        # 2. Single-pass tokenization for single-word terms
        for match in self.TOKEN_PATTERN.finditer(text):
            raw_token = match.group()
            start = match.start()

            if raw_token.lower().startswith(".net"):
                cleaned_token = raw_token.rstrip(".-")
                lead_trimmed = 0
            else:
                stripped_left = raw_token.lstrip(".-")
                lead_trimmed = len(raw_token) - len(stripped_left)
                cleaned_token = stripped_left.rstrip(".-")

            if not cleaned_token:
                continue

            adj_start = start + lead_trimmed
            adj_end = adj_start + len(cleaned_token)

            norm = self._normalize(cleaned_token)
            if norm in self._canonical_by_norm:
                canonical = self._canonical_by_norm[norm]
                weight = self._get_weight(canonical)
                matches.append(TokenMatch(
                    token=cleaned_token,
                    normalized=canonical,
                    start=adj_start,
                    end=adj_end,
                    weight=weight,
                ))

        # 3. Deduplicate overlapping matches (keep highest weight / longest span)
        matches = self._deduplicate_matches(matches)

        # 4. Sort by position
        matches.sort(key=lambda m: m.start)

        return matches

    def _is_word_boundary(self, text: str, start: int, end: int) -> bool:
        """
        Check if match is at word boundaries.

        Args:
            text: Lowercase source text
            start: Start index of match
            end: End index of match (exclusive)

        Returns:
            True if match is bounded by non-alphanumeric chars or string boundaries
        """
        # Check character before
        if start > 0:
            prev_char = text[start - 1]
            if prev_char.isalnum() or prev_char in '+#.-':
                return False

        # Check character after
        if end < len(text):
            next_char = text[end]
            if next_char.isalnum() or next_char in '+#.-':
                return False

        return True

    def _deduplicate_matches(self, matches: list[TokenMatch]) -> list[TokenMatch]:
        """
        Remove overlapping matches, keeping highest weight.

        Args:
            matches: List of potentially overlapping TokenMatch objects

        Returns:
            Deduplicated list
        """
        if not matches:
            return []

        # Sort by start, then by weight descending, then by span length descending
        matches.sort(key=lambda m: (m.start, -m.weight, -m.end))

        result: list[TokenMatch] = []
        last_end = -1

        for match in matches:
            if match.start >= last_end:
                result.append(match)
                last_end = match.end
            elif match.weight > result[-1].weight:
                # Replace with higher weight match
                result[-1] = match
                last_end = match.end

        return result

    def extract_technologies(self, text: str) -> dict[str, list[TokenMatch]]:
        """
        Extract and group technologies by weight category.

        Args:
            text: Input text to analyze

        Returns:
            Dict with keys 'core', 'secondary', 'bonus' containing TokenMatch lists
        """
        matches = self.tokenize(text)

        result: dict[str, list[TokenMatch]] = {
            "core": [],
            "secondary": [],
            "bonus": [],
        }

        for match in matches:
            if match.weight == 3:
                result["core"].append(match)
            elif match.weight == 2:
                result["secondary"].append(match)
            else:
                result["bonus"].append(match)

        return result

    def get_unique_technologies(self, text: str) -> set[str]:
        """
        Get unique normalized technologies found in text.

        Args:
            text: Input text to analyze

        Returns:
            Set of normalized technology names
        """
        matches = self.tokenize(text)
        return {m.normalized for m in matches}


def create_tech_vocabulary_from_config(config: dict[str, Any]) -> TechVocabulary:
    """
    Factory function to create TechVocabulary from config dictionary.
    """
    return TechVocabulary(
        core=tuple(config.get("core", ())),
        secondary=tuple(config.get("secondary", ())),
        bonus=tuple(config.get("bonus", ())),
        multi_word=tuple(config.get("multi_word", ())),
    )


# Example usage and default vocabulary
if __name__ == "__main__":
    # Default vocabulary matching config/filters.yaml
    default_vocab = TechVocabulary(
        core=(
            "react", "nodejs", "nestjs", "typescript", "javascript",
            "postgresql", "nextjs", "express",
        ),
        secondary=(
            "sql", "prisma", "typeorm", "docker", "git", "restapi",
            "graphql", "jest", "testing", "aws", "linux", "cicd",
            "redis", "tailwind",
        ),
        bonus=(
            "html", "css", "sass", "webpack", "vite", "eslint",
            "prettier", "github", "gitlab", "nginx", "apache",
        ),
        multi_word=(
            "rest api", "restapi", "amazon web services", "google cloud platform",
            "github actions", "gitlab ci", "ci cd", "ci/cd", "sql server",
            "visual studio code", "vs code", "visual studio",
        ),
    )

    tokenizer = TechTokenizer(default_vocab)

    # Test
    test_text = """
    We are looking for a Junior Full Stack Developer with React, Node.js,
    TypeScript, and PostgreSQL experience. Knowledge of REST API, Docker,
    AWS, and CI/CD pipelines is a plus. Familiarity with Git, Linux,
    and testing frameworks like Jest is appreciated.
    """

    matches = tokenizer.tokenize(test_text)
    print("Token matches:")
    for m in matches:
        print(f"  {m.token!r} -> {m.normalized!r} [{m.start}:{m.end}] weight={m.weight}")

    print("\nBy category:")
    categorized = tokenizer.extract_technologies(test_text)
    for cat, items in categorized.items():
        if items:
            print(f"  {cat.upper()}: {[m.normalized for m in items]}")

    print(f"\nUnique technologies: {tokenizer.get_unique_technologies(test_text)}")