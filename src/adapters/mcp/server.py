import logging
from pathlib import Path
import sys

from mcp.server.mcpserver import MCPServer

from src.adapters.db.repository import ApplicationRepository
from src.domain.models import ApplicationStatus
from src.services.career_service import CareerService

# All logs strictly to stderr to prevent corrupting stdio MCP communication
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("jobos-mcp")

mcp = MCPServer("jobos-bot")
DB_PATH = "data/jobs.db"


def _get_repository() -> ApplicationRepository:
    return ApplicationRepository(DB_PATH)


@mcp.tool()
def get_pipeline_overview() -> str:
    """Obtiene un resumen ejecutivo del pipeline de postulaciones: total de vacantes, distribución por estado, re-postulaciones y seguimiento."""
    repo = _get_repository()
    try:
        records = repo.find_all(limit=500)
        status_counts: dict[str, int] = {}
        total_reapps = 0

        for r in records:
            status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1
            if r.times_applied > 1:
                total_reapps += (r.times_applied - 1)

        lines = [
            "# Resumen del Pipeline de Postulaciones (jobOS-bot)",
            f"- **Total Vacantes Maestras:** {len(records)}",
            f"- **Re-postulaciones Históricas:** {total_reapps}\n",
            "## Estado Actual",
        ]
        for st, count in status_counts.items():
            lines.append(f"- **{st}:** {count}")

        followup_count = status_counts.get(ApplicationStatus.FOLLOW_UP_REQUIRED.value, 0)
        if followup_count > 0:
            lines.append(f"\n> [!WARNING] Tienes **{followup_count}** postulación(es) en 'Requiere Seguimiento' (+7 días sin respuesta).")

        return "\n".join(lines)
    finally:
        repo.close()


@mcp.tool()
def search_applications(
    query: str = "",
    min_match_score: int = 40,
    status: str = "",
    limit: int = 15,
) -> str:
    """Busca y filtra vacantes guardadas por texto (cargo/empresa), puntaje mínimo de compatibilidad o estado."""
    repo = _get_repository()
    try:
        app_status = ApplicationStatus(status) if status in ApplicationStatus._value2member_map_ else None
        records = repo.find_all(status=app_status, limit=200)

        q_lower = query.lower().strip()
        filtered = [
            r
            for r in records
            if r.match_score >= min_match_score
            and (
                not q_lower
                or q_lower in r.title.lower()
                or q_lower in r.company.lower()
                or q_lower in r.description.lower()
                or any(q_lower in kw.keyword.lower() for kw in r.keywords)
            )
        ][:limit]

        if not filtered:
            return "No se encontraron vacantes con los criterios especificados."

        lines = [f"# Vacantes Encontradas ({len(filtered)} resultados)\n"]
        for r in filtered:
            lines.append(f"### [#{r.id}] {r.title} — {r.company}")
            lines.append(f"- **Estado:** {r.status.value} | **Match:** {r.match_score}% | **Veces Postulado:** {r.times_applied}")
            lines.append(f"- **Modalidad / Ubicación:** {r.modality.value} ({r.location})")
            if r.submissions:
                lines.append(f"- **Portal / URL:** {r.submissions[0].portal.value} — {r.submissions[0].canonical_url}")
            lines.append("")

        return "\n".join(lines)
    finally:
        repo.close()


@mcp.tool()
def get_market_stack_radar() -> str:
    """Muestra el radar de tecnologías más demandadas en el mercado según todas las vacantes analizadas y tu nivel de cobertura."""
    repo = _get_repository()
    try:
        stats = repo.get_keyword_stats()
        if not stats:
            return "No hay suficientes datos de tecnologías registrados en la base de datos."

        lines = [
            "# Radar de Tecnologías del Mercado (jobOS-bot)",
            "| Tecnología | Ofertas que la Piden | Coincidencias en tu Perfil | Cobertura |",
            "| :--- | :---: | :---: | :---: |",
        ]
        for kw, total, matched in stats[:20]:
            pct = int((matched / total) * 100) if total > 0 else 0
            lines.append(f"| **{kw}** | {total} | {matched} | {pct}% |")

        return "\n".join(lines)
    finally:
        repo.close()


@mcp.tool()
def prepare_job_application_kit(application_id: int) -> str:
    """Prepara el kit completo de postulación para una vacante: brecha de keywords ATS (tailor) y guía técnica de entrevista (prep)."""
    repo = _get_repository()
    try:
        service = CareerService(repository=repo)
        app = repo.find_by_id(application_id)
        if not app:
            return f"Error: No se encontró la vacante con ID {application_id}."

        tailor_md = service.tailor_cv(application_id)
        prep_path = service.prepare_interview(application_id)

        lines = [
            f"# Kit de Postulación — [#{app.id}] {app.title} en {app.company}",
            f"- **Match Score:** {app.match_score}% | **Estado:** {app.status.value}",
            f"- **Guía de Entrevista generada en:** `{prep_path}`\n",
            "---",
            "## Optimización de Hoja de Vida (CV Tailor)",
            tailor_md,
        ]
        return "\n".join(lines)
    finally:
        repo.close()


@mcp.tool()
def sync_pipeline_with_notion() -> str:
    """Sincroniza la base de datos local con Notion (Push de nuevas, Pull de cambios de estado, detección de follow-ups y bootstrap si es un PC nuevo)."""
    repo = _get_repository()
    try:
        service = CareerService(repository=repo)
        report = service.sync_with_notion()

        lines = [
            "# Informe de Sincronización con Notion",
            f"- **Vacantes nuevas enviadas a Notion (Push):** {report.pushed_new}",
            f"- **Re-postulaciones actualizadas en Notion:** {report.updated_existing}",
            f"- **Cambios de estado detectados desde Notion (Pull):** {report.pulled_statuses}",
            f"- **Guías técnicas generadas por pasar a Entrevista:** {report.interview_preps_triggered}",
            f"- **Postulaciones marcadas para seguimiento (+7 días):** {report.stalled_followups}",
        ]
        if report.bootstrapped_from_notion > 0:
            lines.append(f"- **Vacantes restauradas desde Notion (Bootstrap Multi-PC):** {report.bootstrapped_from_notion}")

        return "\n".join(lines)
    finally:
        repo.close()


def main() -> None:
    """Punto de entrada para ejecutar el servidor MCP sobre stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
