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
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server import Server

# CQS Commands & Queries
from src.application.commands import (
    ScanPortalsCommand,
    ScanPortalsResult,
    SyncVaultCommand,
    SyncVaultResult,
)
from src.application.queries import (
    GetApplicationsQuery,
    GetApplicationsResult,
)

# Domain Services
from src.domain.matcher import OfferMatcher

# Ports (Interfaces)
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.scraper_port import MultiPortalScraperPort, PortalScanResult
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
mcp = Server("jobos-bot")

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
    return MultiWorkerScraperOrchestrator(max_workers=max_workers)


def _get_vault_adapter(vault_path: str = "vault") -> KnowledgeVaultPort:
    """Get the Obsidian vault adapter."""
    return ObsidianVaultAdapter(vault_path)


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
    vault_path: str = "vault",
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
    start_time = time.perf_counter()

    try:
        # Validate and convert portal names
        portal_enums = []
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
        matcher = _get_matcher(filter_config)

        # Get adapters
        repo = _get_repository()
        orchestrator = _get_scraper_orchestrator(max_workers=workers)
        vault = _get_vault_adapter(vault_path) if sync_obsidian else None

        try:
            # Run concurrent scan across portals
            logger.info(f"Starting concurrent scan on {len(portal_enums)} portals with {workers} workers")
            scan_results: dict[PortalName, PortalScanResult] = orchestrator.run_scan(
                portals=portal_enums,
                config=filter_config,
                limit_per_portal=limit_per_portal,
                headless=headless,
            )

            # Process results: evaluate, persist, collect stats
            total_scanned = 0
            total_matched = 0
            new_applications = 0
            reapplications = 0
            skipped_cooldown = 0
            hard_rejected = 0
            offers_by_portal: dict[str, int] = {}
            errors_by_portal: dict[str, str] = {}
            all_evaluated_offers: list[tuple[Any, Any]] = []  # (JobOffer, MatchEvaluation)

            for portal, result in scan_results.items():
                portal_name = portal.value
                offers_by_portal[portal_name] = len(result.offers)

                if result.error_message:
                    errors_by_portal[portal_name] = result.error_message
                    logger.warning(f"[{portal_name}] Scan error: {result.error_message}")
                    continue

                total_scanned += len(result.offers)

                # Evaluate each offer
                for offer in result.offers:
                    evaluation = matcher.evaluate(offer)

                    if evaluation.is_hard_rejected:
                        hard_rejected += 1
                        logger.debug(f"[{portal_name}] Hard rejected: {evaluation.rejection_reason}")
                        continue

                    total_matched += 1

                    if evaluation.should_apply:
                        all_evaluated_offers.append((offer, evaluation))
                    else:
                        logger.debug(f"[{portal_name}] Below threshold: {evaluation.match_score}%")

            # Persist matched offers to database
            for offer, evaluation in all_evaluated_offers:
                record, was_recorded = repo.record_submission(
                    offer=offer,
                    evaluation=evaluation,
                    cooldown_days=filter_config.matching.reapply_cooldown_days,
                )

                if was_recorded:
                    if record.times_applied == 1:
                        new_applications += 1
                    else:
                        reapplications += 1
                else:
                    skipped_cooldown += 1

            # Sync to Obsidian if requested
            obsidian_synced = False
            obsidian_created = 0
            obsidian_updated = 0

            if sync_obsidian and vault:
                logger.info("Syncing applications to Obsidian vault...")
                # Get all applications from DB for full sync
                all_apps = repo.find_all(limit=1000)
                created, updated = vault.sync_applications(all_apps, vault_path)
                obsidian_synced = True
                obsidian_created = created
                obsidian_updated = updated
                logger.info(f"Obsidian sync complete: {created} created, {updated} updated")

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Build result
            result = ScanPortalsResult(
                total_scanned=total_scanned,
                total_matched=total_matched,
                new_applications=new_applications,
                reapplications=reapplications,
                skipped_cooldown=skipped_cooldown,
                hard_rejected=hard_rejected,
                offers_by_portal=offers_by_portal,
                errors_by_portal=errors_by_portal,
                obsidian_synced=obsidian_synced,
                obsidian_created=obsidian_created,
                obsidian_updated=obsidian_updated,
                execution_time_ms=execution_time_ms,
            )

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
            # Parse status if provided
            app_status = None
            if status:
                try:
                    app_status = ApplicationStatus(status)
                except ValueError:
                    return json.dumps({
                        "success": False,
                        "error": f"Invalid status: '{status}'. Valid: {[s.value for s in ApplicationStatus]}"
                    })

            # Fetch applications with basic filters (repo may not support min_match/keyword yet)
            applications = repo.find_all(
                status=app_status,
                limit=limit + offset + 50,  # Fetch extra for pagination and filtering
            )

            # Apply min_match and keyword filters in Python if needed
            if min_match is not None:
                applications = [app for app in applications if app.match_score >= min_match]

            if keyword is not None:
                kw_lower = keyword.lower()
                applications = [
                    app for app in applications
                    if (kw_lower in app.title.lower()
                        or kw_lower in app.company.lower()
                        or kw_lower in app.description.lower()
                        or any(kw_lower in kw.keyword.lower() for kw in app.keywords))
                ]

            # Apply pagination
            total_count = len(applications)
            paginated = applications[offset:offset + limit]

            # Convert to serializable format
            apps_data = []
            for app in paginated:
                # Get first submission URL for reference
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

            result = GetApplicationsResult(
                applications=paginated,
                total_count=total_count,
                limit=limit,
                offset=offset,
            )

            return json.dumps({
                "success": True,
                "result": {
                    "applications": apps_data,
                    "total_count": result.total_count,
                    "limit": result.limit,
                    "offset": result.offset,
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
    vault_path: str = "vault",
    full_rebuild: bool = False,
) -> str:
    """
    Synchronize or rebuild Obsidian vault from SQLite database.

    This is a COMMAND (mutation) - it creates/updates files in the vault.

    Args:
        vault_path: Path to Obsidian vault
        full_rebuild: If true, delete existing notes and rebuild completely

    Returns:
        JSON string with sync results
    """
    try:
        repo = _get_repository()
        vault = _get_vault_adapter(vault_path)

        try:
            # Get all applications from database
            all_apps = repo.find_all(limit=5000)
            logger.info(f"Syncing {len(all_apps)} applications to Obsidian vault at {vault_path}")

            if full_rebuild:
                logger.info("Full rebuild requested - deleting existing application notes")
                created, updated = vault.rebuild_vault(all_apps, vault_path)
            else:
                created, updated = vault.sync_applications(all_apps, vault_path)

            # Also ensure hub files are created/updated
            hub_count = vault.create_hubs(all_apps, vault_path)

            result = SyncVaultResult(
                created=created,
                updated=updated,
                total_applications=len(all_apps),
                vault_path=vault_path,
            )

            return json.dumps({
                "success": True,
                "result": {
                    "created": result.created,
                    "updated": result.updated,
                    "total_applications": result.total_applications,
                    "vault_path": result.vault_path,
                    "hub_files": hub_count,
                    "full_rebuild": full_rebuild,
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
    # Run the server over stdio
    mcp.run()


if __name__ == "__main__":
    main()