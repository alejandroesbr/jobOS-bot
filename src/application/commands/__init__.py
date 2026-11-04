"""CQS Commands - Write operations (Mutations) for the application layer.

This package contains all command classes for the Command Query Separation (CQS)
architecture. Commands represent intent to change system state and are handled
by corresponding Command Handlers.

Commands:
- ScanPortalsCommand / ScanPortalsResult: Scan job portals, match offers, persist applications
- SyncExternalCommand / SyncExternalResult: Synchronize with external systems (Notion)
- SyncVaultCommand / SyncVaultResult: Synchronize Obsidian vault from database

Each command is an immutable dataclass (frozen=True, slots=True) containing
all parameters needed for the operation. Results are also immutable dataclasses
capturing the outcome with detailed statistics.

Example usage:
    >>> from src.application.commands import ScanPortalsCommand
    >>> from src.domain.models import PortalName
    >>>
    >>> command = ScanPortalsCommand(
    ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
    ...     limit_per_portal=20,
    ...     max_workers=4,
    ...     sync_obsidian=True
    ... )
    >>> result = handler.handle(command)
"""
from src.application.commands.scan_portals import ScanPortalsCommand, ScanPortalsResult
from src.application.commands.sync_external import SyncExternalCommand, SyncExternalResult
from src.application.commands.sync_vault import SyncVaultCommand, SyncVaultResult

__all__ = [
    "ScanPortalsCommand",
    "ScanPortalsResult",
    "SyncExternalCommand",
    "SyncExternalResult",
    "SyncVaultCommand",
    "SyncVaultResult",
]