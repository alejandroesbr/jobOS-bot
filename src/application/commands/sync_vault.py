"""Sync Vault Command - Mutation to synchronize Obsidian vault.

This module defines the Command and Result data classes for the Obsidian vault
synchronization operation in the CQS architecture.

The SyncVaultCommand triggers a vault sync (incremental or full rebuild),
while SyncVaultResult captures the outcome statistics.
"""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationRecord


@dataclass(frozen=True, slots=True)
class SyncVaultCommand:
    """Command to rebuild/sync Obsidian vault from database.

    Immutable command object for triggering vault synchronization.

    Attributes:
        applications: List of application records to synchronize
        vault_path: Path to Obsidian vault root directory (default: "vault")
        full_rebuild: If True, completely rebuild vault from scratch.
            If False, perform incremental sync (default: False)

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> # Incremental sync (default)
        >>> command = SyncVaultCommand(applications=apps, vault_path="~/vaults/job-search")
        >>>
        >>> # Full rebuild
        >>> command = SyncVaultCommand(
        ...     applications=apps,
        ...     vault_path="~/vaults/job-search",
        ...     full_rebuild=True
        ... )
    """
    applications: list[ApplicationRecord]
    vault_path: str = "vault"
    full_rebuild: bool = False


@dataclass(frozen=True, slots=True)
class SyncVaultResult:
    """Result of sync vault command.

    Immutable result object containing vault synchronization statistics.

    Attributes:
        created: Number of new application notes created
        updated: Number of existing application notes updated
        hubs_updated: Number of hub files created/updated
        execution_time_ms: Total command execution time in milliseconds

    Example:
        >>> result = SyncVaultResult(
        ...     created=15,
        ...     updated=8,
        ...     hubs_updated=42,
        ...     execution_time_ms=12340
        ... )
    """
    created: int
    updated: int
    hubs_updated: int = 0
    execution_time_ms: int = 0
    total_applications: int = 0
    vault_path: str = "vault"