"""Hub creation for Graphify-compatible Obsidian structure.

This module provides functions for creating and maintaining hub pages in the
Obsidian vault. Hubs are index and entity pages that form the navigation
structure of the Graphify knowledge graph.

Hub types:
- Index hubs: Top-level index pages (companies/index.md, skills/index.md, etc.)
- Entity hubs: Individual pages for each company, skill, portal, status

All hubs use YAML frontmatter with tags for categorization and wikilinks
for bidirectional navigation. The structure enables graph visualization
and filtered views in Obsidian.
"""
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.adapters.obsidian.adapter import ObsidianVaultAdapter
    from src.domain.models import ApplicationRecord


HUB_TEMPLATES = {
    "companies": {
        "filename": "index.md",
        "content": """---
tags: [hub, companies]
---

# Hub de Empresas

Este directorio contiene las notas índice para cada empresa contratante.
Cada empresa enlaza a sus vacantes mediante wikilinks bidireccionales.

## Empresas Registradas

{{COMPANIES_LIST}}
""",
    },
    "skills": {
        "filename": "index.md",
        "content": """---
tags: [hub, skills]
---

# Hub de Tecnologías (Skills)

Clúster de tecnologías detectadas en el mercado laboral.
Cada skill enlaza a las vacantes que la requieren.

## Tecnologías por Demanda

{{SKILLS_LIST}}
""",
    },
    "portals": {
        "filename": "index.md",
        "content": """---
tags: [hub, portals]
---

# Hub de Portales de Empleo

Origen de las vacantes rastreadas.

## Portales Activos

- [[LinkedIn]]
- [[GetOnBrd]]
- [[Computrabajo]]
- [[Elempleo]]
- [[Glassdoor]]
- [[Indeed]]
""",
    },
    "status": {
        "filename": "index.md",
        "content": """---
tags: [hub, status]
---

# Hub de Estados de Postulación

Estados del pipeline de aplicación.

## Estados

- [[Pendiente]]
- [[Enviado]]
- [[Requiere Seguimiento]]
- [[Entrevista Programada]]
- [[Oferta Recibida]]
- [[Rechazado]]
- [[Descartado]]
""",
    },
}


def create_hub_files(adapter: "ObsidianVaultAdapter") -> None:
    """Create all hub index files.

    Generates the static index pages for each hub category (companies, skills,
    portals, status) using predefined templates. Only creates files that don't
    already exist to preserve any user customizations.

    Args:
        adapter: ObsidianVaultAdapter instance providing directory paths

    Example:
        >>> adapter = ObsidianVaultAdapter("vault")
        >>> create_hub_files(adapter)
        >>> # Creates: companies/index.md, skills/index.md, portals/index.md, status/index.md
    """
    for hub_name, template in HUB_TEMPLATES.items():
        hub_dir = getattr(adapter, f"{hub_name}_dir")
        index_path = hub_dir / template["filename"]
        if not index_path.exists():
            index_path.write_text(template["content"], encoding="utf-8")


def ensure_hub_directories(adapter: "ObsidianVaultAdapter") -> None:
    """Ensure hub directories exist.

    Creates the four hub subdirectories if they don't exist:
    companies/, skills/, portals/, status/

    Args:
        adapter: ObsidianVaultAdapter instance providing directory paths

    Example:
        >>> adapter = ObsidianVaultAdapter("vault")
        >>> ensure_hub_directories(adapter)
    """
    for hub_name in ["companies", "skills", "portals", "status"]:
        hub_dir = getattr(adapter, f"{hub_name}_dir")
        hub_dir.mkdir(parents=True, exist_ok=True)


def build_companies_index(applications: list["ApplicationRecord"], companies_dir: Path) -> None:
    """Build company index page with links to all companies.

    Generates an alphabetically sorted index of all unique companies found
    in the applications list, with wikilinks to each company's hub page.

    Args:
        applications: List of ApplicationRecord objects to extract companies from
        companies_dir: Directory path for company hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> build_companies_index(apps, Path("vault/companies"))
    """
    companies = sorted({app.company for app in applications})
    lines = [
        "---",
        "tags: [hub, companies]",
        "---",
        "",
        "# Hub de Empresas",
        "",
        "Este directorio contiene las notas índice para cada empresa contratante.",
        "Cada empresa enlaza a sus vacantes mediante wikilinks bidireccionales.",
        "",
        "## Empresas Registradas",
        "",
    ]
    for company in companies:
        lines.append(f"- [[{company}]]")
    lines.append("")

    index_path = companies_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_skills_index(applications: list["ApplicationRecord"], skills_dir: Path) -> None:
    """Build skills index page with links to all skills, sorted by demand.

    Aggregates all keywords from applications, counts occurrences across
    job postings, and generates an index sorted by demand (most requested first).

    Args:
        applications: List of ApplicationRecord objects to extract skills from
        skills_dir: Directory path for skill hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> build_skills_index(apps, Path("vault/skills"))
    """
    from collections import Counter

    skill_counts = Counter()
    for app in applications:
        for kw in app.keywords:
            skill_counts[kw.keyword] += 1

    sorted_skills = sorted(skill_counts.items(), key=lambda x: -x[1])

    lines = [
        "---",
        "tags: [hub, skills]",
        "---",
        "",
        "# Hub de Tecnologías (Skills)",
        "",
        "Clúster de tecnologías detectadas en el mercado laboral.",
        "Cada skill enlaza a las vacantes que la requieren.",
        "",
        "## Tecnologías por Demanda",
        "",
    ]
    for skill, count in sorted_skills:
        lines.append(f"- [[{skill}]] — {count} ofertas")

    index_path = skills_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_portals_index(applications: list["ApplicationRecord"], portals_dir: Path) -> None:
    """Build portals index page.

    Generates an index of all unique portals found in the applications list
    with wikilinks to each portal's hub page.

    Args:
        applications: List of ApplicationRecord objects to extract portals from
        portals_dir: Directory path for portal hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> build_portals_index(apps, Path("vault/portals"))
    """
    portals = sorted({app.submissions[0].portal.value for app in applications if app.submissions})

    lines = [
        "---",
        "tags: [hub, portals]",
        "---",
        "",
        "# Hub de Portales de Empleo",
        "",
        "Origen de las vacantes rastreadas.",
        "",
        "## Portales Activos",
        "",
    ]
    for portal in portals:
        lines.append(f"- [[{portal}]]")

    index_path = portals_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_status_index(applications: list["ApplicationRecord"], status_dir: Path) -> None:
    """Build status index page.

    Generates an index of all possible application statuses with wikilinks.
    Unlike other hubs, this includes all defined statuses regardless of
    whether they appear in the current applications.

    Args:
        applications: List of ApplicationRecord objects (used for consistency)
        status_dir: Directory path for status hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> build_status_index(apps, Path("vault/status"))
    """
    from src.domain.models import ApplicationStatus

    lines = [
        "---",
        "tags: [hub, status]",
        "---",
        "",
        "# Hub de Estados de Postulación",
        "",
        "Estados del pipeline de aplicación.",
        "",
        "## Estados",
        "",
    ]
    for status in ApplicationStatus:
        lines.append(f"- [[{status.value}]]")

    index_path = status_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def create_company_hubs(applications: list["ApplicationRecord"], companies_dir: Path) -> None:
    """Create individual company hub pages.

    For each unique company in the applications list, creates a hub page
    listing all applications for that company with key metadata and wikilinks.

    Args:
        applications: List of ApplicationRecord objects to derive hubs from
        companies_dir: Directory path for company hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> create_company_hubs(apps, Path("vault/companies"))
    """
    companies = sorted({app.company for app in applications})

    for company in companies:
        company_apps = [app for app in applications if app.company == company]

        lines = [
            "---",
            f"tags: [company, {company.lower()}]",
            "---",
            "",
            f"# {company}",
            "",
            f"**Total vacantes:** {len(company_apps)}",
            "",
            "## Vacantes",
            "",
        ]

        for app in company_apps:
            portal = app.submissions[0].portal.value if app.submissions else "unknown"
            lines.append(
                f"- [[{app.dedup_key.replace('::', '_').replace(' ', '-').lower()}]] — "
                f"{app.title} ({app.match_score}%) — {portal} — [[{app.status.value}]]"
            )

        safe_name = company.replace("/", "-").replace("\\", "-")
        file_path = companies_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")


def create_skill_hubs(applications: list["ApplicationRecord"], skills_dir: Path) -> None:
    """Create individual skill hub pages.

    For each unique skill/keyword found in applications, creates a hub page
    listing all applications requiring that skill with match status indicators.

    Args:
        applications: List of ApplicationRecord objects to derive hubs from
        skills_dir: Directory path for skill hub files

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> create_skill_hubs(apps, Path("vault/skills"))
    """
    from collections import defaultdict

    skill_to_apps = defaultdict(list)
    for app in applications:
        for kw in app.keywords:
            skill_to_apps[kw.keyword].append(app)

    for skill, apps in skill_to_apps.items():
        lines = [
            "---",
            f"tags: [skill, {skill.lower()}]",
            "---",
            "",
            f"# {skill}",
            "",
            f"**Demanda:** {len(apps)} vacantes",
            "",
            "## Vacantes que requieren esta habilidad",
            "",
        ]

        for app in apps:
            portal = app.submissions[0].portal.value if app.submissions else "unknown"
            matched = "✅" if any(kw.keyword == skill and kw.is_matched for kw in app.keywords) else "❌"
            lines.append(
                f"- {matched} [[{app.dedup_key.replace('::', '_').replace(' ', '-').lower()}]] — "
                f"{app.title} @ {app.company} ({app.match_score}%) — {portal}"
            )

        safe_name = skill.replace("/", "-").replace("\\", "-").replace("#", "sharp").replace("+", "plus")
        file_path = skills_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")