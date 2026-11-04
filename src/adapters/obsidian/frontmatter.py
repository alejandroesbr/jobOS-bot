"""YAML Frontmatter generation for Obsidian notes.

This module provides utilities for building and formatting YAML frontmatter
for Obsidian markdown notes following Graphify conventions.

The frontmatter schema includes:
- Core metadata: id, dedup_key, title, company, location, modality, portal, url
- Matching metrics: match_score, times_applied
- Status tracking: status, first_applied_at, last_applied_at
- Categorization: tags array
- Graphify links: company_link, skill_links, portal_link, status_link (wikilinks)

All frontmatter fields are designed to be queryable via Obsidian's Dataview plugin
and to support Graphify's bidirectional linking structure.
"""
from dataclasses import dataclass
from typing import Optional

from src.adapters.obsidian.wikilinks import sanitize_for_filename, slugify
from src.domain.models import ApplicationRecord, ApplicationStatus, PortalName, WorkModality


@dataclass(frozen=True, slots=True)
class ApplicationFrontmatter:
    """Frontmatter schema for application notes.

    Immutable data class representing the complete YAML frontmatter structure
    for a job application note in the Obsidian vault.

    All fields correspond to YAML frontmatter keys. The link fields contain
    Obsidian wikilinks ([[Target]]) for bidirectional graph navigation.

    Attributes:
        id: Database primary key
        dedup_key: Unique deduplication key (portal::external_id)
        title: Job title
        company: Company name
        location: Job location string
        modality: Work modality (Remote, Hybrid, On-site)
        portal: Source portal name
        url: Canonical URL to job posting
        match_score: Match percentage (0-100)
        times_applied: Number of applications to this offer
        status: Current application status
        first_applied_at: ISO timestamp of first application
        last_applied_at: ISO timestamp of most recent application
        tags: List of tags for categorization
        company_link: Wikilink to company hub page
        skill_links: List of wikilinks to skill hub pages
        portal_link: Wikilink to portal index page
        status_link: Wikilink to status index page

    Example:
        >>> fm = ApplicationFrontmatter(
        ...     id=1,
        ...     dedup_key="linkedin::12345",
        ...     title="Senior Python Developer",
        ...     company="TechCorp",
        ...     location="Remote",
        ...     modality="Remote",
        ...     portal="LinkedIn",
        ...     url="https://linkedin.com/jobs/12345",
        ...     match_score=85,
        ...     times_applied=1,
        ...     status="Sent",
        ...     first_applied_at="2024-01-15T10:30:00Z",
        ...     last_applied_at="2024-01-15T10:30:00Z",
        ...     tags=["job-application", "sent", "remote"],
        ...     company_link="[[TechCorp]]",
        ...     skill_links=["[[Python]]", "[[Django]]"],
        ...     portal_link="[[LinkedIn]]",
        ...     status_link="[[Sent]]"
        ... )
    """
    id: int
    dedup_key: str
    title: str
    company: str
    location: str
    modality: str
    portal: str
    url: str
    match_score: int
    times_applied: int
    status: str
    first_applied_at: Optional[str]
    last_applied_at: Optional[str]
    tags: list[str]
    # Graphify links
    company_link: str
    skill_links: list[str]
    portal_link: str
    status_link: str


PORTAL_DISPLAY_NAMES: dict[str, str] = {
    "linkedin": "LinkedIn",
    "getonbrd": "GetOnBrd",
    "computrabajo": "Computrabajo",
    "elempleo": "Elempleo",
    "glassdoor": "Glassdoor",
    "indeed": "Indeed",
}


def format_portal_display(portal_raw: str) -> str:
    return PORTAL_DISPLAY_NAMES.get(portal_raw.lower(), portal_raw)


def build_frontmatter(record: ApplicationRecord, skills: list[str]) -> ApplicationFrontmatter:
    """Build frontmatter from ApplicationRecord.

    Constructs an ApplicationFrontmatter object by extracting and transforming
    data from the ApplicationRecord. Generates wikilinks for Graphify navigation.

    Args:
        record: ApplicationRecord with complete application data including
            submissions, keywords, and metadata
        skills: List of matched skill keywords to include as skill_links

    Returns:
        ApplicationFrontmatter object ready for YAML serialization
    """
    skill_links = [f"[[{sanitize_for_filename(skill)}]]" for skill in skills]

    portal_value = record.submissions[0].portal.value if record.submissions else "unknown"
    portal_display = format_portal_display(portal_value)
    url_value = record.submissions[0].canonical_url if record.submissions else ""
    safe_company = sanitize_for_filename(record.company)
    safe_portal = sanitize_for_filename(portal_display)
    safe_status = sanitize_for_filename(record.status.value)

    raw_tags = ["job-application", record.status.value, record.modality.value]
    clean_tags = [slugify(tag) for tag in raw_tags if slugify(tag)]

    return ApplicationFrontmatter(
        id=record.id,
        dedup_key=record.dedup_key,
        title=record.title,
        company=record.company,
        location=record.location,
        modality=record.modality.value,
        portal=portal_value,
        url=url_value,
        match_score=record.match_score,
        times_applied=record.times_applied,
        status=record.status.value,
        first_applied_at=record.first_applied_at,
        last_applied_at=record.last_applied_at,
        tags=clean_tags,
        company_link=f"[[{safe_company}]]",
        skill_links=skill_links,
        portal_link=f"[[{safe_portal}]]",
        status_link=f"[[{safe_status}]]",
    )


def _escape_yaml_str(val: str) -> str:
    return val.replace("\\", "\\\\").replace('"', '\\"')


def format_yaml_frontmatter(fm: ApplicationFrontmatter) -> str:
    """Format frontmatter as YAML string.

    Serializes an ApplicationFrontmatter object to a valid YAML frontmatter
    block with proper escaping and formatting. The output includes the
    opening and closing `---` delimiters.

    Args:
        fm: ApplicationFrontmatter object to serialize

    Returns:
        Complete YAML frontmatter string including `---` delimiters

    Example:
        >>> fm = build_frontmatter(record, skills)
        >>> yaml = format_yaml_frontmatter(fm)
        >>> print(yaml)
        ---
        id: 1
        dedup_key: "linkedin::12345"
        title: "Senior Python Developer"
        ...
        ---
    """
    clean_tags = [slugify(tag) for tag in fm.tags if slugify(tag)]
    quoted_skill_links = ", ".join(f'"{_escape_yaml_str(link)}"' for link in fm.skill_links)

    lines = ["---"]
    lines.append(f"id: {fm.id}")
    lines.append(f'dedup_key: "{_escape_yaml_str(fm.dedup_key)}"')
    lines.append(f'title: "{_escape_yaml_str(fm.title)}"')
    lines.append(f'company: "{_escape_yaml_str(fm.company)}"')
    lines.append(f'location: "{_escape_yaml_str(fm.location)}"')
    lines.append(f"modality: {fm.modality}")
    lines.append(f"portal: {fm.portal}")
    lines.append(f'url: "{_escape_yaml_str(fm.url)}"')
    lines.append(f"match_score: {fm.match_score}")
    lines.append(f"times_applied: {fm.times_applied}")
    lines.append(f'status: "{_escape_yaml_str(fm.status)}"')
    if fm.first_applied_at:
        lines.append(f"first_applied_at: {fm.first_applied_at}")
    if fm.last_applied_at:
        lines.append(f"last_applied_at: {fm.last_applied_at}")
    lines.append(f"tags: [{', '.join(clean_tags)}]")
    lines.append(f'company_link: "{_escape_yaml_str(fm.company_link)}"')
    lines.append(f"skill_links: [{quoted_skill_links}]")
    lines.append(f'portal_link: "{_escape_yaml_str(fm.portal_link)}"')
    lines.append(f'status_link: "{_escape_yaml_str(fm.status_link)}"')
    lines.append("---")
    return "\n".join(lines)