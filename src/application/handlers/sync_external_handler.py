"""Sync External Handler - Executes external sync command (Notion, etc.).

This module contains the SyncExternalHandler which executes the
SyncExternalCommand by synchronizing with external systems (currently Notion)
in the CQS architecture.

The handler delegates the actual API communication and data mapping to the
ExternalSyncPort implementation, which handles:
- Pushing new/updated applications to Notion
- Pulling status changes from Notion
- Generating interview prep documents
- Detecting stalled follow-ups
- Bootstrapping from Notion (importing new applications)
"""
import time
from src.application.commands import SyncExternalCommand, SyncExternalResult
from src.domain.models import ApplicationRecord
from src.ports.external_sync_port import ExternalSyncPort


class SyncExternalHandler:
    """Handles SyncExternalCommand by syncing with external systems (Notion).

    This handler executes external synchronization operations by delegating
    to the ExternalSyncPort implementation. It provides a thin CQS command
    layer over the port's sync functionality.

    The handler:
    1. Receives SyncExternalCommand with applications and config
    2. Calls external_sync.sync_applications() with the provided data
    3. Measures execution time
    4. Returns SyncExternalResult with detailed sync statistics

    Attributes:
        _external_sync: ExternalSyncPort implementation for external API operations

    Example:
        >>> handler = SyncExternalHandler(external_sync=notion_adapter)
        >>> apps = repo.find_all(limit=1000)
        >>> config = load_filter_config()
        >>> command = SyncExternalCommand(
        ...     applications=apps,
        ...     config=config,
        ...     target="notion"
        ... )
        >>> result = handler.handle(command)
        >>> print(f"Pushed: {result.pushed_new}, Pulled: {result.pulled_statuses}")
    """

    def __init__(self, external_sync: ExternalSyncPort) -> None:
        """Initialize the handler with external sync dependency.

        Args:
            external_sync: ExternalSyncPort implementation for external API operations

        Example:
            >>> handler = SyncExternalHandler(NotionSyncAdapter(token="...", db_id="..."))
        """
        self._external_sync = external_sync

    def handle(self, command: SyncExternalCommand) -> SyncExternalResult:
        """Execute the sync external command.

        Performs the external synchronization workflow:
        1. Delegate to external_sync.sync_applications() with command data
        2. Measure execution time
        3. Return SyncExternalResult with all sync statistics

        Args:
            command: SyncExternalCommand with applications, config, and target

        Returns:
            SyncExternalResult containing:
                - pushed_new: New applications pushed to external system
                - updated_existing: Existing applications updated in external system
                - pulled_statuses: Status changes pulled from external system
                - interview_preps_triggered: Interview prep documents generated
                - stalled_followups: Applications flagged for follow-up
                - bootstrapped_from_external: Applications imported from external system
                - execution_time_ms: Total execution time in milliseconds

        Example:
            >>> command = SyncExternalCommand(
            ...     applications=apps,
            ...     config=config,
            ...     target="notion"
            ... )
            >>> result = handler.handle(command)
            >>> print(f"Sync completed in {result.execution_time_ms}ms")
            >>> print(f"New: {result.pushed_new}, Updated: {result.updated_existing}")
        """
        start_time = time.perf_counter()

        # Delegate to external sync adapter
        result = self._external_sync.sync_applications(
            applications=command.applications,
            config=command.config,
        )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return SyncExternalResult(
            pushed_new=result.pushed_new,
            updated_existing=result.updated_existing,
            pulled_statuses=result.pulled_statuses,
            interview_preps_triggered=result.interview_preps_triggered,
            stalled_followups=result.stalled_followups,
            bootstrapped_from_external=result.bootstrapped_from_external,
            execution_time_ms=execution_time_ms,
        )