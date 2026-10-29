import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

COMPANY_SUFFIX_PATTERN = re.compile(
    r"\b(?:s\.?a\.?s\.?|s\.?a\.?|ltda\.?|inc\.?|llc\.?|corp\.?|corporation|b\.?v\.?|gmbh|colombia|latam)\b",
    re.IGNORECASE,
)

TITLE_NOISE_PATTERN = re.compile(
    r"\b(?:urgente|remoto|remote|hibrido|hybrid|barranquilla|colombia|latam)\b|100\s*%",
    re.IGNORECASE,
)

QUESTION_NOISE_PATTERN = re.compile(
    r"\((?:obligatorio|required|opcional|optional)\)",
    re.IGNORECASE,
)

NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9.\s]+")
WHITESPACE_PATTERN = re.compile(r"\s+")

TITLE_SYNONYMS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bjr\.?\b"), "junior"),
    (re.compile(r"\bsr\.?\b"), "senior"),
    (re.compile(r"\bfullstack\b"), "full stack"),
    (re.compile(r"\bnode\.?js\b"), "node"),
    (re.compile(r"\breact\.?js\b"), "react"),
    (re.compile(r"\bnext\.?js\b"), "nextjs"),
    (re.compile(r"\bnest\.?js\b"), "nestjs"),
    (re.compile(r"\bpostgres\b"), "postgresql"),
)

ALLOWED_QUERY_PARAMS_BY_HOST: dict[str, frozenset[str]] = {
    "linkedin.com": frozenset({"currentJobId"}),
    "indeed.com": frozenset({"jk"}),
}


def strip_accents(text: str) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def normalize_company_name(raw_company: str) -> str:
    if not raw_company:
        return ""
    ascii_text = strip_accents(raw_company).lower()
    without_suffixes = COMPANY_SUFFIX_PATTERN.sub(" ", ascii_text)
    alphanumeric = re.sub(r"[^a-z0-9\s]+", " ", without_suffixes)
    return collapse_whitespace(alphanumeric)


def normalize_job_title(raw_title: str) -> str:
    if not raw_title:
        return ""
    text = strip_accents(raw_title).lower()
    for pattern, replacement in TITLE_SYNONYMS:
        text = pattern.sub(replacement, text)
    text = TITLE_NOISE_PATTERN.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return collapse_whitespace(text)


def build_dedup_key(company: str, title: str) -> str:
    company_norm = normalize_company_name(company)
    title_norm = normalize_job_title(title)
    if not company_norm or not title_norm:
        raise ValueError("Both company and title must contain valid alphanumeric characters.")
    return f"{company_norm}::{title_norm}"


def _filter_allowed_query_params(netloc: str, path: str, query: str) -> str:
    if "linkedin.com" in netloc and "/jobs/view/" in path:
        return ""
    allowed_keys: frozenset[str] = frozenset()
    for domain, keys in ALLOWED_QUERY_PARAMS_BY_HOST.items():
        if domain in netloc:
            allowed_keys = keys
            break
    if not allowed_keys:
        return ""
    filtered_pairs = [(k, v) for k, v in parse_qsl(query) if k in allowed_keys]
    return urlencode(filtered_pairs)


def normalize_canonical_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty.")
    parts = urlsplit(cleaned)
    scheme = "https" if parts.scheme in {"http", "https", ""} else parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query = _filter_allowed_query_params(netloc, path, parts.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def normalize_form_question(raw_label: str) -> str:
    if not raw_label:
        return ""
    text = strip_accents(raw_label).lower()
    text = QUESTION_NOISE_PATTERN.sub(" ", text)
    for pattern, replacement in TITLE_SYNONYMS:
        text = pattern.sub(replacement, text)
    text = NON_ALPHANUMERIC_PATTERN.sub(" ", text).replace(".", " ")
    return collapse_whitespace(text)

