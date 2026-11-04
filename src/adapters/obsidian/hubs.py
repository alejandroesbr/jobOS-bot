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
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from src.adapters.obsidian.frontmatter import format_portal_display
from src.adapters.obsidian.wikilinks import sanitize_for_filename, slugify
from src.domain.models import ApplicationStatus, PortalName

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


def _get_app_note_name(app: "ApplicationRecord") -> str:
    return sanitize_for_filename(app.dedup_key.replace("::", "_"))


def _escape_md_cell(text: str) -> str:
    """Escape pipe characters and newlines so Markdown tables stay intact."""
    return text.replace("|", "∣").replace("\n", " ").strip()


def _format_applications_table(apps: list["ApplicationRecord"]) -> list[str]:
    """Generate an Excel-like Markdown table for a list of applications."""
    if not apps:
        return ["*Sin vacantes registradas en esta categoría.*"]

    lines = [
        "| # | Match % | Cargo | Nota | Empresa | Modalidad | Ubicación | Portal | Estado | Skills Clave | Fecha | Acción |",
        "| :---: | :---: | :--- | :--- | :--- | :---: | :--- | :---: | :---: | :--- | :---: | :---: |",
    ]
    for idx, app in enumerate(apps, start=1):
        note_name = _get_app_note_name(app)
        safe_title = _escape_md_cell(app.title)
        safe_comp_file = sanitize_for_filename(app.company)
        safe_loc = _escape_md_cell(app.location or "Remoto")
        modality = _escape_md_cell(app.modality.value)

        portal_name = (
            format_portal_display(app.submissions[0].portal.value)
            if app.submissions
            else "unknown"
        )
        safe_portal_file = sanitize_for_filename(portal_name)
        safe_status_file = sanitize_for_filename(app.status.value)

        matched_kws = [
            f"[[{sanitize_for_filename(kw.keyword)}]]"
            for kw in app.keywords
            if kw.is_matched
        ][:4]
        skills_cell = ", ".join(matched_kws) if matched_kws else "—"

        date_str = (app.last_applied_at or app.first_applied_at or "")[:10] or "—"
        url = app.submissions[-1].canonical_url if app.submissions else ""
        action_cell = f"[🔗 Abrir]({url})" if url else "—"

        badge = "🟢" if app.match_score >= 70 else ("🟡" if app.match_score >= 40 else "⚪")

        lines.append(
            f"| {idx} "
            f"| {badge} **{app.match_score}%** "
            f"| **{safe_title}** "
            f"| [[{note_name}]] "
            f"| [[{safe_comp_file}]] "
            f"| `{modality}` "
            f"| {safe_loc} "
            f"| [[{safe_portal_file}]] "
            f"| [[{safe_status_file}]] "
            f"| {skills_cell} "
            f"| {date_str} "
            f"| {action_cell} |"
        )
    return lines


def build_companies_index(applications: list["ApplicationRecord"], companies_dir: Path) -> None:
    """Build company index page with an Excel-style summary table."""
    company_apps_map: dict[str, list["ApplicationRecord"]] = defaultdict(list)
    for app in applications:
        company_apps_map[app.company].append(app)

    sorted_companies = sorted(
        company_apps_map.items(),
        key=lambda item: (-len(item[1]), item[0].lower()),
    )

    lines = [
        "---",
        "tags: [hub, companies]",
        "---",
        "",
        "# 🏢 Hub de Empresas Contratantes",
        "",
        f"**Total empresas registradas:** {len(sorted_companies)}",
        "",
        "## 📊 Tabla de Empresas",
        "",
        "| # | Empresa | Vacantes | Mejor Match % | Match Promedio | Última Vacante |",
        "| :---: | :--- | :---: | :---: | :---: | :--- |",
    ]
    for idx, (company, c_apps) in enumerate(sorted_companies, start=1):
        safe_company = sanitize_for_filename(company)
        best_score = max((a.match_score for a in c_apps), default=0)
        avg_score = round(sum(a.match_score for a in c_apps) / len(c_apps)) if c_apps else 0
        top_app = max(c_apps, key=lambda a: a.match_score)
        top_note = _get_app_note_name(top_app)
        lines.append(
            f"| {idx} | [[{safe_company}]] "
            f"| **{len(c_apps)}** | **{best_score}%** | {avg_score}% "
            f"| [[{top_note}]] ({_escape_md_cell(top_app.title)}) |"
        )
    lines.append("")

    index_path = companies_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_skills_index(applications: list["ApplicationRecord"], skills_dir: Path) -> None:
    """Build skills index page with an Excel-style demand table."""
    skill_counts: Counter[str] = Counter()
    skill_matched: dict[str, bool] = {}
    skill_weights: dict[str, int] = {}

    for app in applications:
        for kw in app.keywords:
            skill_counts[kw.keyword] += 1
            skill_matched[kw.keyword] = skill_matched.get(kw.keyword, False) or kw.is_matched
            skill_weights[kw.keyword] = max(skill_weights.get(kw.keyword, 0), int(kw.weight))

    sorted_skills = sorted(skill_counts.items(), key=lambda x: (-x[1], x[0].lower()))

    lines = [
        "---",
        "tags: [hub, skills]",
        "---",
        "",
        "# 🛠️ Hub de Tecnologías (Skills)",
        "",
        f"**Total tecnologías detectadas:** {len(sorted_skills)}",
        "",
        "## 📊 Tabla de Tecnologías por Demanda",
        "",
        "| # | Tecnología | En tu CV | Categoría | Vacantes que la piden | % del Mercado |",
        "| :---: | :--- | :---: | :---: | :---: | :---: |",
    ]
    total_apps = max(len(applications), 1)
    for idx, (skill, count) in enumerate(sorted_skills, start=1):
        safe_skill = sanitize_for_filename(skill)
        in_cv = "✅ Sí" if skill_matched.get(skill, False) else "❌ Falta"
        tier = {3: "CORE", 2: "SECONDARY", 1: "BONUS"}.get(skill_weights.get(skill, 1), "OTHER")
        pct = round((count / total_apps) * 100)
        lines.append(
            f"| {idx} | [[{safe_skill}]] "
            f"| {in_cv} | `{tier}` | **{count}** | {pct}% |"
        )

    index_path = skills_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_portals_index(applications: list["ApplicationRecord"], portals_dir: Path) -> None:
    """Build portals index page with an Excel-style summary table."""
    portal_apps: dict[str, list["ApplicationRecord"]] = defaultdict(list)
    for p in PortalName:
        portal_apps[format_portal_display(p.value)] = []
    for app in applications:
        if app.submissions:
            p_display = format_portal_display(app.submissions[0].portal.value)
            portal_apps[p_display].append(app)

    lines = [
        "---",
        "tags: [hub, portals]",
        "---",
        "",
        "# 🌐 Hub de Portales de Empleo",
        "",
        "## 📊 Tabla Comparativa por Portal",
        "",
        "| Portal | Total Vacantes | Alta Afinidad (≥70%) | Match Promedio |",
        "| :--- | :---: | :---: | :---: |",
    ]
    for portal, p_list in sorted(portal_apps.items(), key=lambda x: -len(x[1])):
        safe_portal = sanitize_for_filename(portal)
        high_c = sum(1 for a in p_list if a.match_score >= 70)
        avg_m = f"{round(sum(a.match_score for a in p_list) / len(p_list))}%" if p_list else "—"
        lines.append(f"| [[{safe_portal}]] | **{len(p_list)}** | {high_c} | {avg_m} |")

    index_path = portals_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def build_status_index(applications: list["ApplicationRecord"], status_dir: Path) -> None:
    """Build status index page with an Excel-style pipeline table."""
    status_apps: dict[str, list["ApplicationRecord"]] = {
        status.value: [] for status in ApplicationStatus
    }
    for app in applications:
        status_apps.setdefault(app.status.value, []).append(app)

    lines = [
        "---",
        "tags: [hub, status]",
        "---",
        "",
        "# 📊 Hub de Estados de Postulación",
        "",
        "## 📋 Resumen por Estado del Pipeline",
        "",
        "| Estado | Cantidad de Vacantes | % del Total |",
        "| :--- | :---: | :---: |",
    ]
    total_apps = max(len(applications), 1)
    for status in ApplicationStatus:
        s_name = status.value
        safe_status = sanitize_for_filename(s_name)
        count = len(status_apps.get(s_name, []))
        pct = round((count / total_apps) * 100) if applications else 0
        lines.append(f"| [[{safe_status}]] | **{count}** | {pct}% |")

    index_path = status_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")


def create_company_hubs(applications: list["ApplicationRecord"], companies_dir: Path) -> None:
    """Create individual company hub pages with an Excel-like table of applications."""
    companies = sorted({app.company for app in applications})

    for company in companies:
        company_apps = sorted(
            [app for app in applications if app.company == company],
            key=lambda a: a.match_score,
            reverse=True,
        )
        company_tag = slugify(company) or "empresa"

        lines = [
            "---",
            f"tags: [company, {company_tag}]",
            "---",
            "",
            f"# 🏢 {company}",
            "",
            f"**Total vacantes:** {len(company_apps)}",
            "",
            "## 📊 Tabla de Vacantes en esta Empresa",
            "",
            *_format_applications_table(company_apps),
        ]

        safe_name = sanitize_for_filename(company)
        file_path = companies_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")


def create_skill_hubs(applications: list["ApplicationRecord"], skills_dir: Path) -> None:
    """Create individual skill hub pages with an Excel-like table of applications."""
    skill_to_apps: dict[str, list["ApplicationRecord"]] = defaultdict(list)
    for app in applications:
        for kw in app.keywords:
            skill_to_apps[kw.keyword].append(app)

    for skill, apps in skill_to_apps.items():
        sorted_apps = sorted(apps, key=lambda a: a.match_score, reverse=True)
        skill_tag = slugify(skill) or "tech"
        lines = [
            "---",
            f"tags: [skill, {skill_tag}]",
            "---",
            "",
            f"# 🛠️ {skill}",
            "",
            f"**Demanda:** {len(sorted_apps)} vacantes",
            "",
            "## 📊 Vacantes que requieren esta habilidad",
            "",
            *_format_applications_table(sorted_apps),
        ]

        safe_name = sanitize_for_filename(skill)
        file_path = skills_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")


def create_portal_hubs(applications: list["ApplicationRecord"], portals_dir: Path) -> None:
    """Create individual portal hub pages in vault/portals/<portal>.md with a table."""
    portal_to_apps: dict[str, list["ApplicationRecord"]] = defaultdict(list)
    for portal_enum in PortalName:
        portal_to_apps[format_portal_display(portal_enum.value)] = []

    for app in applications:
        portal_val = format_portal_display(app.submissions[0].portal.value) if app.submissions else "unknown"
        portal_to_apps[portal_val].append(app)

    for portal_name, apps in portal_to_apps.items():
        if not apps and portal_name == "unknown":
            continue
        sorted_apps = sorted(apps, key=lambda a: a.match_score, reverse=True)
        portal_tag = slugify(portal_name) or "portal"
        lines = [
            "---",
            f"tags: [portal, {portal_tag}]",
            "---",
            "",
            f"# 🌐 Portal: {portal_name}",
            "",
            f"**Total vacantes:** {len(sorted_apps)}",
            "",
            "## 📊 Tabla de Vacantes Rastreadas",
            "",
            *_format_applications_table(sorted_apps),
        ]

        safe_name = sanitize_for_filename(portal_name)
        file_path = portals_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")


def create_status_hubs(applications: list["ApplicationRecord"], status_dir: Path) -> None:
    """Create individual status hub pages in vault/status/<status>.md with a table."""
    status_to_apps: dict[str, list["ApplicationRecord"]] = {
        status.value: [] for status in ApplicationStatus
    }
    for app in applications:
        status_to_apps.setdefault(app.status.value, []).append(app)

    for status_name, apps in status_to_apps.items():
        sorted_apps = sorted(apps, key=lambda a: a.match_score, reverse=True)
        status_tag = slugify(status_name) or "status"
        lines = [
            "---",
            f"tags: [status, {status_tag}]",
            "---",
            "",
            f"# 📋 Estado: {status_name}",
            "",
            f"**Total vacantes:** {len(sorted_apps)}",
            "",
            "## 📊 Vacantes en este Estado",
            "",
            *_format_applications_table(sorted_apps),
        ]

        safe_name = sanitize_for_filename(status_name)
        file_path = status_dir / f"{safe_name}.md"
        file_path.write_text("\n".join(lines), encoding="utf-8")


def build_dashboard_hub(applications: list["ApplicationRecord"], vault_root: Path) -> None:
    """Build master 00-Dashboard.md and 01-Tabla-Maestra-Vacantes.md in Excel-like table format."""
    sorted_apps = sorted(applications, key=lambda a: a.match_score, reverse=True)
    high_match = [a for a in sorted_apps if a.match_score >= 70]
    mid_match = [a for a in sorted_apps if 40 <= a.match_score < 70]
    low_match = [a for a in sorted_apps if a.match_score < 40]
    companies_count = len({a.company for a in applications})
    skills_counter: Counter[str] = Counter()
    for app in applications:
        for kw in app.keywords:
            skills_counter[kw.keyword] += 1

    status_counts: Counter[str] = Counter(a.status.value for a in applications)

    # 1. Write 01-Tabla-Maestra-Vacantes.md (Full Excel-like Master Spreadsheet)
    master_lines = [
        "---",
        "tags: [spreadsheet, jobos, table]",
        "cssclasses: [wide-page, max]",
        "---",
        "",
        "# 📊 Tabla Maestra de Vacantes (Vista Hoja de Cálculo)",
        "",
        f"Base de datos tabular completa con las **{len(sorted_apps)} vacantes** ordenadas de mayor a menor afinidad.",
        "Puedes hacer clic en cualquier **Cargo**, **Empresa**, **Portal**, **Estado**, **Skill** o en **🔗 Abrir** para ir directo a la oferta.",
        "",
        "## 📋 Todas las Vacantes Registradas",
        "",
        *_format_applications_table(sorted_apps),
        "",
        "---",
        "",
        "## ⚡ Vista Dinámica (Plugin Dataview — Opcional)",
        "> [!TIP] Si instalas el plugin comunitario **Dataview** o **DB Folder** en Obsidian, el siguiente bloque se convierte en una tabla dinámica filtrable automáticamente:",
        "",
        "```dataview",
        "TABLE WITHOUT ID",
        '  file.link AS "Vacante",',
        '  company_link AS "Empresa",',
        '  match_score + "%" AS "Match",',
        '  modality AS "Modalidad",',
        '  portal_link AS "Portal",',
        '  status_link AS "Estado",',
        '  first_applied_at AS "Fecha"',
        'FROM "jobOS/applications"',
        "SORT match_score DESC",
        "```",
    ]
    master_table_path = vault_root / "01-Tabla-Maestra-Vacantes.md"
    master_table_path.write_text("\n".join(master_lines), encoding="utf-8")

    # 2. Write 00-Dashboard.md with KPI table + Categorized Excel-like Tables
    lines = [
        "---",
        "tags: [dashboard, jobos, moc]",
        "cssclasses: [wide-page, max]",
        "---",
        "",
        "# 🎯 jobOS — Cuartel de Inteligencia Laboral",
        "",
        "Panel central organizado en formato **Tabla / Hoja de Cálculo**.",
        "",
        "## 🗂️ Navegación Rápida",
        "",
        "| Vista / Carpeta | Descripción | Cantidad |",
        "| :--- | :--- | :---: |",
        f"| 📊 **[[01-Tabla-Maestra-Vacantes\\|Tabla Maestra Completa (Tipo Excel)]]** | Todas las vacantes en una sola hoja de cálculo | **{len(applications)}** |",
        f"| 🏢 **[[companies/index\\|Tabla de Empresas (companies/)]]** | Empresas contratantes y su mejor Match % | **{companies_count}** |",
        f"| 🛠️ **[[skills/index\\|Tabla de Tecnologías (skills/)]]** | Ranking de tecnologías más pedidas en el mercado | **{len(skills_counter)}** |",
        "| 🌐 **[[portals/index\\|Tabla de Portales (portals/)]]** | Comparativa por portal (LinkedIn, GetOnBrd, Computrabajo...) | **6** |",
        "| 📋 **[[status/index\\|Tabla de Estados (status/)]]** | Seguimiento del pipeline de postulaciones | **7** |",
        "",
        "## 📈 Indicadores Clave (KPIs)",
        "",
        "| Total Vacantes | 🟢 Alta Afinidad (≥ 70%) | 🟡 Afinidad Media (40–69%) | Empresas Únicas | Skills Detectadas |",
        "| :---: | :---: | :---: | :---: | :---: |",
        f"| **{len(applications)}** | **{len(high_match)}** | **{len(mid_match)}** | **{companies_count}** | **{len(skills_counter)}** |",
        "",
        f"## 🔥 Tabla de Vacantes — Alta Afinidad (≥ 70%) [{len(high_match)}]",
        "",
        *_format_applications_table(high_match),
        "",
        f"## ⚡ Tabla de Vacantes — Afinidad Media (40% – 69%) [{len(mid_match)}]",
        "",
        *_format_applications_table(mid_match),
    ]

    if low_match:
        lines.extend([
            "",
            f"## 📌 Tabla de Otras Vacantes (< 40%) [{len(low_match)}]",
            "",
            *_format_applications_table(low_match),
        ])

    lines.extend([
        "",
        "## 🛠️ Top 15 Tecnologías Más Demandadas",
        "",
        "| # | Tecnología | Vacantes que la solicitan |",
        "| :---: | :--- | :---: |",
    ])
    for idx, (skill, count) in enumerate(skills_counter.most_common(15), start=1):
        safe_sk = sanitize_for_filename(skill)
        lines.append(f"| {idx} | [[{safe_sk}\\|{_escape_md_cell(skill)}]] | **{count}** |")

    dashboard_path = vault_root / "00-Dashboard.md"
    dashboard_path.write_text("\n".join(lines), encoding="utf-8")
