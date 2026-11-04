"""Sync Vault Handler - Executes Obsidian vault sync command.

This module contains the SyncVaultHandler which executes the
SyncVaultCommand by synchronizing applications to the Obsidian vault
in the CQS architecture.

The handler supports two modes:
1. Incremental sync (default): Creates/updates application notes and hub indexes
2. Full rebuild: Completely rebuilds vault from scratch

Both modes also create/update hub files for companies, skills, portals, and statuses.
"""
from pathlib import Path
import time
from src.application.commands import SyncVaultCommand, SyncVaultResult
from src.domain.models import ApplicationRecord
from src.ports.vault_port import KnowledgeVaultPort


class SyncVaultHandler:
    """Handles SyncVaultCommand by syncing applications to Obsidian vault.

    This handler executes vault synchronization operations, supporting both
    incremental sync and full rebuild modes. It delegates the actual file
    system operations to the KnowledgeVaultPort implementation.

    The handler:
    1. Receives SyncVaultCommand with applications list and mode
    2. Calls appropriate vault port method (sync_applications or rebuild_vault)
    3. Creates/updates hub files for navigation
    4. Returns SyncVaultResult with statistics

    Attributes:
        _vault: KnowledgeVaultPort implementation for vault operations

    Example:
        >>> handler = SyncVaultHandler(vault=obsidian_adapter)
        >>> apps = repo.find_all(limit=1000)
        >>> command = SyncVaultCommand(
        ...     applications=apps,
        ...     vault_path="~/vaults/job-search",
        ...     full_rebuild=False
        ... )
        >>> result = handler.handle(command)
        >>> print(f"Created: {result.created}, Updated: {result.updated}")
    """

    def __init__(self, vault: KnowledgeVaultPort) -> None:
        """Initialize the handler with vault dependency.

        Args:
            vault: KnowledgeVaultPort implementation for vault operations

        Example:
            >>> handler = SyncVaultHandler(ObsidianVaultAdapter("vault"))
        """
        self._vault = vault

    def handle(self, command: SyncVaultCommand) -> SyncVaultResult:
        """Execute the sync vault command.

        Performs the vault synchronization workflow:
        1. Choose sync mode based on command.full_rebuild
        2. Execute sync_applications (incremental) or rebuild_vault (full)
        3. Create/update hub files for companies, skills, portals, statuses
        4. Return result with creation/update counts and execution time

        Args:
            command: SyncVaultCommand with applications, vault_path, and full_rebuild flag

        Returns:
            SyncVaultResult containing:
                - created: Number of new application notes created
                - updated: Number of existing application notes updated
                - hubs_updated: Number of hub files created/updated
                - execution_time_ms: Total execution time in milliseconds

        Example:
            >>> apps = repo.find_all(limit=2000)
            >>> command = SyncVaultCommand(
            ...     applications=apps,
            ...     vault_path="vault",
            ...     full_rebuild=True
            ... )
            >>> result = handler.handle(command)
            >>> print(f"Full rebuild: {result.created} notes, {result.hubs_updated} hubs")
        """
        start_time = time.perf_counter()
        vault_dir = Path(command.vault_path)

        if command.full_rebuild:
            created, updated = self._vault.rebuild_vault(
                applications=command.applications,
                vault_path=vault_dir,
            )
        else:
            created, updated = self._vault.sync_applications(
                applications=command.applications,
                vault_path=vault_dir,
            )

        # Create/update hubs
        hubs_updated = self._vault.create_hubs(
            applications=command.applications,
            vault_path=vault_dir,
        )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return SyncVaultResult(
            created=created,
            updated=updated,
            hubs_updated=hubs_updated,
            execution_time_ms=execution_time_ms,
            total_applications=len(command.applications),
            vault_path=command.vault_path,
        )