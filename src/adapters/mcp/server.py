"""
CQS-based MCP Server for jobOS-bot.

Exposes three tools via stdio MCP:
1. run_portal_scan_and_sync - Command: scans portals concurrently, persists to SQLite, syncs to Obsidian
2. query_job_applications - Query: reads applications with filters (status, min_match, keyword)
3. sync_obsidian_vault - Command: rebuilds/syncs Obsidian vault from database

All logging goes to stderr to avoid corrupting stdio MCP communication.
"""
import json
import logging
import os
from pathlib import Path
import sys

from typing import cast
from mcp.server.mcpserver import MCPServer as FastMCP

# CQS Commands, Queries & Handlers
from src.application.commands import (
    ScanPortalsCommand,
    ScanPortalsResult,
    SyncVaultCommand,
    SyncVaultResult,
)
from src.application.handlers import (
    GetApplicationsHandler,
    ScanPortalsHandler,
    SyncVaultHandler,
)
from src.application.queries import (
    GetApplicationsQuery,
    GetApplicationsResult,
)

# Domain Services
from src.domain.matcher import OfferMatcher

# Ports (Interfaces)
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.scraper_port import MultiPortalScraperPort
from src.ports.vault_port import KnowledgeVaultPort

# Adapters (Concrete Implementations)
from src.adapters.db.repository import ApplicationRepository
from src.adapters.obsidian.adapter import ObsidianVaultAdapter
from src.adapters.scrapers.orchestrator import MultiWorkerScraperOrchestrator
from src.config_loader import FilterConfig, load_filter_config
from src.domain.models import ApplicationStatus, PortalName

# All logs strictly to stderr to prevent corrupting stdio MCP communication
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("jobos-mcp")

# MCP Server instance
mcp = FastMCP("jobOS-bot")

# Default database path
DB_PATH = "data/jobs.db"


def _get_repository() -> ApplicationRepositoryPort:
    """Get the application repository instance."""
    return ApplicationRepository(DB_PATH)


def _get_filter_config(config: FilterConfig | None = None) -> FilterConfig:
    """Get filter config, loading from file if not provided."""
    if config is not None:
        return config
    return load_filter_config()


def _get_scraper_orchestrator(max_workers: int = 4) -> MultiPortalScraperPort:
    """Get the multi-worker scraper orchestrator."""
    return cast(MultiPortalScraperPort, MultiWorkerScraperOrchestrator(max_workers=max_workers))


def _resolve_mcp_vault_path(vault_path: str | None = None) -> str:
    """Resolve external Obsidian vault path from argument or OBSIDIAN_VAULT_PATH / VAULT_PATH."""
    explicit_vault = (vault_path or "").strip()
    env_vault = (
        os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
        or os.getenv("VAULT_PATH", "").strip()
    )
    raw = explicit_vault or env_vault
    if not raw:
        raise ValueError(
            "Ruta del Vault de Obsidian no configurada. "
            "Pasa 'vault_path' o define OBSIDIAN_VAULT_PATH=/ruta/a/tu/obsidian en .env"
        )
    resolved = Path(raw).expanduser().resolve()
    project_root = Path(__file__).resolve().parents[3]
    if resolved == project_root or project_root in resolved.parents:
        raise ValueError(
            f"El Vault de Obsidian debe apuntar a tu bóveda externa fuera del repositorio (recibido: '{resolved}')."
        )

    subfolder = os.getenv("OBSIDIAN_VAULT_SUBFOLDER", "jobOS").strip() if not explicit_vault else ""
    if subfolder and resolved.name.lower() != subfolder.lower():
        resolved = resolved / subfolder

    return str(resolved)


def _get_vault_adapter(vault_path: str | None = None) -> KnowledgeVaultPort:
    """Get the Obsidian vault adapter."""
    return ObsidianVaultAdapter(_resolve_mcp_vault_path(vault_path))


def _get_matcher(config: FilterConfig) -> OfferMatcher:
    """Get the offer matcher instance."""
    return OfferMatcher(config)


# =============================================================================
# COMMAND: run_portal_scan_and_sync
# =============================================================================

@mcp.tool()
async def run_portal_scan_and_sync(
    portals: list[str],
    limit_per_portal: int = 15,
    workers: int = 4,
    headless: bool = True,
    sync_obsidian: bool = True,
    vault_path: str | None = None,
) -> str:
    """
    Scan job portals concurrently, filter offers, persist to SQLite, and sync to Obsidian vault.

    This is a COMMAND (mutation) - it modifies database state and creates files.

    Args:
        portals: List of portal names to scan (e.g., ["linkedin", "getonbrd", "computrabajo"])
        limit_per_portal: Maximum offers to collect per portal
        workers: Number of concurrent workers (1-6)
        headless: Run browsers in headless mode
        sync_obsidian: Whether to sync results to Obsidian vault
        vault_path: Path to Obsidian vault

    Returns:
        JSON string with scan results summary
    """
    try:
        # Validate and convert portal names
        portal_enums: list[PortalName] = []
        for p in portals:
            try:
                portal_enums.append(PortalName(p.lower()))
            except ValueError:
                return json.dumps({
                    "success": False,
                    "error": f"Unknown portal: '{p}'. Valid portals: {[pn.value for pn in PortalName]}"
                })

        if not portal_enums:
            return json.dumps({
                "success": False,
                "error": "No valid portals specified"
            })

        # Load configuration
        filter_config = _get_filter_config()

        # Get adapters
        repo = _get_repository()
        orchestrator = _get_scraper_orchestrator(max_workers=workers)
        resolved_vault_path = _resolve_mcp_vault_path(vault_path) if sync_obsidian else ""
        vault = _get_vault_adapter(resolved_vault_path) if sync_obsidian else None

        try:
            logger.info(f"Starting concurrent scan on {len(portal_enums)} portals with {workers} workers")
            command = ScanPortalsCommand(
                portals=portal_enums,
                limit_per_portal=limit_per_portal,
                headless=headless,
                max_workers=workers,
                sync_obsidian=sync_obsidian,
                vault_path=resolved_vault_path,
                config=filter_config,
            )
            handler = ScanPortalsHandler(
                repository=repo,
                scraper=orchestrator,
                vault=vault,
            )
            result: ScanPortalsResult = handler.handle(command)

            return json.dumps({
                "success": True,
                "result": {
                    "total_scanned": result.total_scanned,
                    "total_matched": result.total_matched,
                    "new_applications": result.new_applications,
                    "reapplications": result.reapplications,
                    "skipped_cooldown": result.skipped_cooldown,
                    "hard_rejected": result.hard_rejected,
                    "offers_by_portal": result.offers_by_portal,
                    "errors_by_portal": result.errors_by_portal,
                    "obsidian_synced": result.obsidian_synced,
                    "obsidian_created": result.obsidian_created,
                    "obsidian_updated": result.obsidian_updated,
                    "execution_time_ms": result.execution_time_ms,
                }
            })

        finally:
            repo.close()

    except Exception as ex:
        logger.error(f"run_portal_scan_and_sync failed: {ex}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(ex)
        })


# =============================================================================
# QUERY: query_job_applications
# =============================================================================

@mcp.tool()
async def query_job_applications(
    status: str | None = None,
    min_match: int | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """
    Query job applications with filters (read-only operation).

    This is a QUERY (read-only) - it does not modify any state.

    Args:
        status: Filter by application status (e.g., "Enviado", "Pendiente", "Entrevista Programada")
        min_match: Minimum match score percentage
        keyword: Search keyword in title, company, description, or keywords
        limit: Maximum results to return
        offset: Pagination offset

    Returns:
        JSON string with applications list and metadata
    """
    try:
        repo = _get_repository()

        try:
            # Validate status if provided
            if status:
                try:
                    ApplicationStatus(status)
                except ValueError:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid status: '{status}'. Valid: {[s.value for s in ApplicationStatus]}"
                    })

            query = GetApplicationsQuery(
                status=status,
                min_match_score=min_match,
                keyword=keyword,
                limit=limit,
                offset=offset,
            )
            handler = GetApplicationsHandler(repository=repo)
            result: GetApplicationsResult = handler.handle(query)

            # Convert to serializable format
            apps_data: list[dict[str, object]] = []
            for app in result.applications:
                first_url = app.submissions[0].canonical_url if app.submissions else "#"
                first_portal = app.submissions[0].portal.value if app.submissions else "unknown"

                apps_data.append({
                    "id": app.id,
                    "dedup_key": app.dedup_key,
                    "title": app.title,
                    "company": app.company,
                    "location": app.location,
                    "modality": app.modality.value,
                    "match_score": app.match_score,
                    "times_applied": app.times_applied,
                    "status": app.status.value,
                    "first_applied_at": app.first_applied_at,
                    "last_applied_at": app.last_applied_at,
                    "portal": first_portal,
                    "url": first_url,
                    "matched_keywords": [kw.keyword for kw in app.keywords if kw.is_matched],
                    "missing_keywords": [kw.keyword for kw in app.keywords if not kw.is_matched],
                })

            return json.dumps({
                "success": True,
                "result": {
                    "applications": apps_data,
                    "total_count": result.total_count,
                    "limit": result.limit,
                    "offset": result.offset,
                    "execution_time_ms": result.execution_time_ms,
                }
            })

        finally:
            repo.close()

    except Exception as ex:
        logger.error(f"query_job_applications failed: {ex}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(ex)
        })


# =============================================================================
# COMMAND: sync_obsidian_vault
# =============================================================================

@mcp.tool()
async def sync_obsidian_vault(
    vault_path: str | None = None,
    full_rebuild: bool = False,
) -> str:
    """
    Synchronize or rebuild Obsidian vault from SQLite database.

    This is a COMMAND (mutation) - it creates/updates files in the vault.

    Args:
        vault_path: External path to your Obsidian vault (or read from OBSIDIAN_VAULT_PATH)
        full_rebuild: If true, delete existing notes and rebuild completely

    Returns:
        JSON string with sync results
    """
    try:
        resolved_vault_path = _resolve_mcp_vault_path(vault_path)
        repo = _get_repository()
        vault = _get_vault_adapter(resolved_vault_path)

        try:
            all_apps = repo.find_all(limit=5000)
            logger.info(f"Syncing {len(all_apps)} applications to Obsidian vault at {resolved_vault_path}")

            command = SyncVaultCommand(
                applications=all_apps,
                vault_path=resolved_vault_path,
                full_rebuild=full_rebuild,
            )
            handler = SyncVaultHandler(vault=vault)
            result: SyncVaultResult = handler.handle(command)

            return json.dumps({
                "success": True,
                "result": {
                    "created": result.created,
                    "updated": result.updated,
                    "total_applications": result.total_applications,
                    "vault_path": result.vault_path,
                    "hub_files": result.hubs_updated,
                    "full_rebuild": full_rebuild,
                    "execution_time_ms": result.execution_time_ms,
                }
            })

        finally:
            repo.close()

    except Exception as ex:
        logger.error(f"sync_obsidian_vault failed: {ex}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(ex)
        })


# =============================================================================
# MCP Server Entry Point
# =============================================================================

def main() -> None:
    """Entry point for stdio MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()