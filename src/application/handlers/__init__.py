"""CQS Handlers - Command and Query handlers for the application layer.

This package contains all handler classes for the Command Query Separation (CQS)
architecture. Handlers contain the business logic for executing commands and queries
by coordinating ports (repositories, scrapers, vaults, external sync).

Handlers:
- ScanPortalsHandler: Orchestrates multi-worker portal scan, matching, persistence, and vault sync
- GetApplicationsHandler: Executes filtered, paginated application queries
- SyncVaultHandler: Synchronizes applications to Obsidian vault (incremental or full rebuild)
- SyncExternalHandler: Synchronizes with external systems (Notion)

Handlers are stateless (except for injected dependencies) and follow the pattern:
    handler = Handler(dependencies...)
    result = handler.handle(command_or_query)

Dependencies are injected via constructor for testability and loose coupling.
All handlers measure and return execution time in their results.

Note: GetApplicationByIdHandler is referenced but not yet implemented as a separate file.
      The GetApplicationsHandler can be used with limit=1 and appropriate filters.

Example usage:
    >>> from src.application.handlers import ScanPortalsHandler
    >>> from src.application.commands import ScanPortalsCommand
    >>> from src.domain.models import PortalName
    >>>
    >>> handler = ScanPortalsHandler(
    ...     repository=sqlite_repo,
    ...     scraper=multi_worker_orchestrator,
    ...     vault=obsidian_adapter
    ... )
    >>> command = ScanPortalsCommand(
    ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
    ...     limit_per_portal=20
    ... )
    >>> result = handler.handle(command)
"""
from src.application.handlers.scan_portals_handler import ScanPortalsHandler
from src.application.handlers.sync_vault_handler import SyncVaultHandler
from src.application.handlers.sync_external_handler import SyncExternalHandler
from src.application.handlers.get_applications_handler import GetApplicationsHandler
# GetApplicationByIdHandler - not yet implemented as separate file

__all__ = [
    "ScanPortalsHandler",
    "SyncVaultHandler",
    "SyncExternalHandler",
    "GetApplicationsHandler",
    # "GetApplicationByIdHandler",
]