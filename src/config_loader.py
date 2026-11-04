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


DEFAULT_TECH_ALIASES: dict[str, str] = {
    # C-family
    "c#": "csharp",
    "csharp": "csharp",
    "c sharp": "csharp",
    "c++": "cpp",
    "cpp": "cpp",
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
    "docker compose": "docker compose",
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
    "ci-cd": "cicd",
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
    "ts-node": "tsnode",
    "tsnode": "tsnode",
    "nodemon": "nodemon",
    "pm2": "pm2",
    "nginx": "nginx",
    "apache": "apache",
    "varnish": "varnish",
    "haproxy": "haproxy",
}


def normalize_tech_token(token: str) -> str:
    """Clean leading/trailing punctuation (preserving .net) and normalize via alias map."""
    raw = token.strip().lower()
    if raw.startswith(".net"):
        cleaned = raw.rstrip(".-")
    else:
        cleaned = raw.strip(".-")
    if not cleaned:
        return ""
    return DEFAULT_TECH_ALIASES.get(cleaned, cleaned)


@dataclass(frozen=True, slots=True)
class MatchingRules:
    min_match_score: int = 40
    reapply_cooldown_days: int = 3
    short_description_base_score: int = 65


@dataclass(frozen=True, slots=True)
class TechVocabulary:
    core: tuple[str, ...] = ()
    secondary: tuple[str, ...] = ()
    bonus: tuple[str, ...] = ()
    multi_word: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "core", tuple(self.core))
        object.__setattr__(self, "secondary", tuple(self.secondary))
        object.__setattr__(self, "bonus", tuple(self.bonus))
        if self.multi_word:
            object.__setattr__(self, "multi_word", tuple(self.multi_word))
        else:
            mw = tuple(
                kw
                for kw in (*self.core, *self.secondary, *self.bonus)
                if " " in kw or "/" in kw
            )
            object.__setattr__(self, "multi_word", mw)

    def get_weight(self, keyword: str) -> KeywordWeight:
        keyword_lower = keyword.strip().lower()
        keyword_norm = normalize_tech_token(keyword)
        for k in self.core:
            if keyword_lower == k.lower() or (keyword_norm and keyword_norm == normalize_tech_token(k)):
                return KeywordWeight.CORE
        for k in self.secondary:
            if keyword_lower == k.lower() or (keyword_norm and keyword_norm == normalize_tech_token(k)):
                return KeywordWeight.SECONDARY
        for k in self.bonus:
            if keyword_lower == k.lower() or (keyword_norm and keyword_norm == normalize_tech_token(k)):
                return KeywordWeight.BONUS
        if any(keyword_lower == m.lower() or (keyword_norm and keyword_norm == normalize_tech_token(m)) for m in self.multi_word):
            return KeywordWeight.SECONDARY
        return KeywordWeight.BONUS

    def get_all_keywords(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for kw in (*self.core, *self.secondary, *self.bonus, *self.multi_word):
            low = kw.lower()
            if low not in seen:
                seen.add(low)
                result.append(kw)
        return result

    def get_aliases(self, canonical: str) -> list[str]:
        norm = normalize_tech_token(canonical)
        aliases: list[str] = []
        seen: set[str] = set()
        for candidate_alias, target_norm in DEFAULT_TECH_ALIASES.items():
            if target_norm == norm and candidate_alias not in seen:
                seen.add(candidate_alias)
                aliases.append(candidate_alias)
        if canonical.lower() not in seen:
            aliases.append(canonical.lower())
        return aliases

    def is_single_word(self, token: str) -> bool:
        norm = normalize_tech_token(token)
        if not norm:
            return False
        for kw in (*self.core, *self.secondary, *self.bonus):
            if token.lower() == kw.lower() or norm == normalize_tech_token(kw):
                return True
        return False

    def is_multi_word(self, term: str) -> bool:
        low = term.strip().lower()
        if any(low == m.lower() for m in self.multi_word):
            return True
        for kw in (*self.core, *self.secondary, *self.bonus):
            if (" " in kw or "/" in kw) and (low == kw.lower() or normalize_tech_token(low) == normalize_tech_token(kw)):
                return True
        return False

    @property
    def all_terms(self) -> set[str]:
        return {kw.lower() for kw in self.get_all_keywords()}


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
