"""
TechTokenizer: O(n) single-pass technology extraction with Aho-Corasick multi-word matching.

This module provides efficient technology tokenization from job descriptions,
preserving special characters (+#.-) within tokens and normalizing via alias maps.
"""

import re
from dataclasses import dataclass
from typing import Optional

try:
    import ahocorasick
except ImportError:
    ahocorasick = None


@dataclass(slots=True)
class TokenMatch:
    """Represents a matched technology token with metadata."""
    token: str          # Original matched text from input
    normalized: str     # Canonical form (e.g., "c#" -> "csharp")
    start: int          # Start index in source text
    end: int            # End index in source text (exclusive)
    weight: int         # 3=CORE, 2=SECONDARY, 1=BONUS


class TechVocabulary:
    """
    Technology vocabulary container with weighted terms.

    Expected structure:
    - core: set[str] - High-weight technologies (weight=3)
    - secondary: set[str] - Medium-weight technologies (weight=2)
    - bonus: set[str] - Low-weight technologies (weight=1)
    - multi_word: set[str] - Multi-word terms for Aho-Corasick (e.g., "rest api")
    """
    def __init__(
        self,
        core: set[str],
        secondary: set[str],
        bonus: set[str],
        multi_word: set[str],
    ) -> None:
        self.core = {t.lower() for t in core}
        self.secondary = {t.lower() for t in secondary}
        self.bonus = {t.lower() for t in bonus}
        self.multi_word = {t.lower() for t in multi_word}

        # Combined lookup sets
        self._all_single: set[str] = set()
        self._all_single.update(self.core)
        self._all_single.update(self.secondary)
        self._all_single.update(self.bonus)

        # Weight map for O(1) lookup
        self._weight_map: dict[str, int] = {}
        for term in self.core:
            self._weight_map[term] = 3
        for term in self.secondary:
            self._weight_map[term] = 2
        for term in self.bonus:
            self._weight_map[term] = 1
        for term in self.multi_word:
            self._weight_map[term] = 2  # Multi-word default to SECONDARY

    def get_weight(self, normalized: str) -> int:
        """Get weight for a normalized term, defaulting to BONUS (1)."""
        return self._weight_map.get(normalized.lower(), 1)

    def is_single_word(self, term: str) -> bool:
        """Check if term is in single-word vocabulary."""
        return term.lower() in self._all_single

    def is_multi_word(self, term: str) -> bool:
        """Check if term is in multi-word vocabulary."""
        return term.lower() in self.multi_word

    @property
    def all_terms(self) -> set[str]:
        """All vocabulary terms combined."""
        return self._all_single | self.multi_word


class TechTokenizer:
    """
    Single-pass technology tokenizer using Aho-Corasick for multi-word terms
    and hash lookup for single-word tokens.

    Preserves technology-specific characters (+ # . -) within tokens.
    Normalizes via alias dictionary (e.g., "c#" -> "csharp", "js" -> "javascript").
    """

    # Regex pattern for tokenization: preserves + # . - within words
    TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9+#.\-]+")

    def __init__(self, vocabulary: TechVocabulary) -> None:
        """
        Initialize tokenizer with a TechVocabulary.

        Args:
            vocabulary: TechVocabulary instance with core/secondary/bonus/multi_word terms
        """
        self.vocabulary = vocabulary
        self._alias_map: dict[str, str] = self._build_alias_map()
        self._automaton: Optional[ahocorasick.Automaton] = None
        self._build_automaton()

    def _build_alias_map(self) -> dict[str, str]:
        """
        Build comprehensive alias map for technology normalization.

        Maps common variants to canonical forms.
        """
        aliases = {
            # C-family
            "c#": "csharp",
            "c sharp": "csharp",
            "c++": "cpp",
            "c plus plus": "cpp",
            "c": "c",

            # .NET ecosystem
            ".net": "dotnet",
            "dotnet": "dotnet",
            "dot net": "dotnet",
            "asp.net": "aspnet",
            "aspnet": "aspnet",
            "asp.net core": "aspnetcore",
            "aspnetcore": "aspnetcore",
            ".net core": "dotnetcore",
            "dotnet core": "dotnetcore",
            "dotnetcore": "dotnetcore",
            ".net framework": "dotnetframework",
            "dotnet framework": "dotnetframework",
            "entity framework": "entityframework",
            "entityframework": "entityframework",
            "ef core": "efcore",
            "efcore": "efcore",

            # JavaScript/TypeScript
            "js": "javascript",
            "javascript": "javascript",
            "ecmascript": "javascript",
            "es6": "javascript",
            "es2015": "javascript",
            "ts": "typescript",
            "typescript": "typescript",
            "node.js": "nodejs",
            "nodejs": "nodejs",
            "node": "nodejs",
            "deno": "deno",
            "bun": "bun",

            # Frontend frameworks
            "react.js": "react",
            "reactjs": "react",
            "react": "react",
            "next.js": "nextjs",
            "nextjs": "nextjs",
            "next": "nextjs",
            "vue.js": "vue",
            "vuejs": "vue",
            "vue": "vue",
            "nuxt.js": "nuxt",
            "nuxtjs": "nuxt",
            "svelte": "svelte",
            "sveltekit": "sveltekit",
            "angular": "angular",
            "angularjs": "angularjs",

            # Backend frameworks
            "express.js": "express",
            "expressjs": "express",
            "express": "express",
            "nest.js": "nestjs",
            "nestjs": "nestjs",
            "nest": "nestjs",
            "fastify": "fastify",
            "koa": "koa",
            "hapi": "hapi",
            "spring boot": "springboot",
            "springboot": "springboot",
            "spring": "spring",
            "django": "django",
            "flask": "flask",
            "fastapi": "fastapi",
            "gin": "gin",
            "echo": "echo",

            # Databases
            "postgresql": "postgresql",
            "postgres": "postgresql",
            "pg": "postgresql",
            "mysql": "mysql",
            "mariadb": "mariadb",
            "sqlite": "sqlite",
            "sqlite3": "sqlite",
            "mongodb": "mongodb",
            "mongo": "mongodb",
            "redis": "redis",
            "cassandra": "cassandra",
            "dynamodb": "dynamodb",
            "elasticsearch": "elasticsearch",
            "elastic": "elasticsearch",
            "sql server": "sqlserver",
            "sqlserver": "sqlserver",
            "mssql": "sqlserver",
            "oracle": "oracle",
            "oracle db": "oracle",

            # ORMs
            "prisma": "prisma",
            "typeorm": "typeorm",
            "sequelize": "sequelize",
            "knex": "knex",
            "drizzle": "drizzle",
            "sqlalchemy": "sqlalchemy",
            "gorm": "gorm",
            "hibernate": "hibernate",
            "jpa": "jpa",

            # Cloud & DevOps
            "aws": "aws",
            "amazon web services": "aws",
            "azure": "azure",
            "gcp": "gcp",
            "google cloud": "gcp",
            "google cloud platform": "gcp",
            "docker": "docker",
            "kubernetes": "kubernetes",
            "k8s": "kubernetes",
            "terraform": "terraform",
            "ansible": "ansible",
            "jenkins": "jenkins",
            "github actions": "githubactions",
            "githubactions": "githubactions",
            "gitlab ci": "gitlabci",
            "gitlabci": "gitlabci",
            "circleci": "circleci",
            "travis": "travis",
            "travis ci": "travis",

            # APIs & Protocols
            "rest api": "restapi",
            "restapi": "restapi",
            "rest": "restapi",
            "graphql": "graphql",
            "grpc": "grpc",
            "websocket": "websocket",
            "websockets": "websocket",
            "api": "api",

            # Testing
            "jest": "jest",
            "vitest": "vitest",
            "mocha": "mocha",
            "chai": "chai",
            "cypress": "cypress",
            "playwright": "playwright",
            "selenium": "selenium",
            "pytest": "pytest",
            "junit": "junit",
            "testng": "testng",

            # Other tools
            "git": "git",
            "github": "github",
            "gitlab": "gitlab",
            "bitbucket": "bitbucket",
            "linux": "linux",
            "unix": "unix",
            "bash": "bash",
            "shell": "shell",
            "ci/cd": "cicd",
            "cicd": "cicd",
            "ci cd": "cicd",
            "tailwind": "tailwind",
            "tailwind css": "tailwind",
            "bootstrap": "bootstrap",
            "sass": "sass",
            "scss": "sass",
            "less": "less",
            "webpack": "webpack",
            "vite": "vite",
            "rollup": "rollup",
            "esbuild": "esbuild",
            "babel": "babel",
            "eslint": "eslint",
            "prettier": "prettier",
            "typescript": "typescript",
            "ts-node": "tsnode",
            "tsnode": "tsnode",
            "nodemon": "nodemon",
            "pm2": "pm2",
            "nginx": "nginx",
            "apache": "apache",
            "varnish": "varnish",
            "haproxy": "haproxy",
        }
        return aliases

    def _build_automaton(self) -> None:
        """Build Aho-Corasick automaton for multi-word term matching."""
        if ahocorasick is None:
            self._automaton = None
            return

        self._automaton = ahocorasick.Automaton()

        # Add all multi-word terms to automaton
        for term in self.vocabulary.multi_word:
            normalized = self._normalize(term)
            # Store both original and normalized for matching
            self._automaton.add_word(term, (term, normalized))

        self._automaton.make_automaton()

    def _normalize(self, token: str) -> str:
        """
        Normalize a token using the alias map.

        Args:
            token: Raw token to normalize

        Returns:
            Canonical form of the token
        """
        lower = token.lower().strip()
        return self._alias_map.get(lower, lower)

    def _get_weight(self, normalized: str) -> int:
        """Get weight for a normalized token."""
        return self.vocabulary.get_weight(normalized)

    def tokenize(self, text: str) -> list[TokenMatch]:
        """
        Single-pass tokenization of input text.

        Uses hash lookup for single-word tokens and Aho-Corasick
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

        # 1. Aho-Corasick multi-word matching (if available)
        if self._automaton is not None:
            for end_idx, (original, normalized) in self._automaton.iter(text_lower):
                start_idx = end_idx - len(original) + 1
                # Verify word boundaries
                if self._is_word_boundary(text_lower, start_idx, end_idx + 1):
                    weight = self._get_weight(normalized)
                    matches.append(TokenMatch(
                        token=text[start_idx:end_idx + 1],
                        normalized=normalized,
                        start=start_idx,
                        end=end_idx + 1,
                        weight=weight,
                    ))

        # 2. Single-pass tokenization for single-word terms
        # Use regex to find all tokens preserving +#.-
        for match in self.TOKEN_PATTERN.finditer(text):
            token = match.group()
            start = match.start()
            end = match.end()

            # Normalize and check vocabulary
            normalized = self._normalize(token)

            if self.vocabulary.is_single_word(normalized):
                weight = self._get_weight(normalized)
                matches.append(TokenMatch(
                    token=token,
                    normalized=normalized,
                    start=start,
                    end=end,
                    weight=weight,
                ))

        # 3. Deduplicate overlapping matches (keep highest weight)
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

        # Sort by start, then by weight descending
        matches.sort(key=lambda m: (m.start, -m.weight, m.end))

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

        result = {
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


def create_tech_vocabulary_from_config(config: dict) -> TechVocabulary:
    """
    Factory function to create TechVocabulary from config dictionary.

    Expected config structure:
    {
        "core": ["React", "Node.js", "TypeScript", ...],
        "secondary": ["Docker", "AWS", "GraphQL", ...],
        "bonus": ["Git", "Linux", "CI/CD", ...],
        "multi_word": ["rest api", "amazon web services", ...]
    }
    """
    return TechVocabulary(
        core=set(config.get("core", [])),
        secondary=set(config.get("secondary", [])),
        bonus=set(config.get("bonus", [])),
        multi_word=set(config.get("multi_word", [])),
    )


# Example usage and default vocabulary
if __name__ == "__main__":
    # Default vocabulary matching config/filters.yaml
    default_vocab = TechVocabulary(
        core={
            "react", "nodejs", "nestjs", "typescript", "javascript",
            "postgresql", "nextjs", "express",
        },
        secondary={
            "sql", "prisma", "typeorm", "docker", "git", "restapi",
            "graphql", "jest", "testing", "aws", "linux", "cicd",
            "redis", "tailwind",
        },
        bonus={
            "html", "css", "sass", "webpack", "vite", "eslint",
            "prettier", "github", "gitlab", "nginx", "apache",
        },
        multi_word={
            "rest api", "restapi", "amazon web services", "google cloud platform",
            "github actions", "gitlab ci", "ci cd", "ci/cd", "sql server",
            "visual studio code", "vs code", "visual studio",
        },
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