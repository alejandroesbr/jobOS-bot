"""External Sync Port - Abstract interface for optional Notion sync.

This module defines the abstract interface (Port) for bidirectional synchronization
with external systems, currently supporting Notion as the primary external target.

The sync is optional - the application functions fully without external sync.
Notion serves as a visual dashboard and collaboration layer on top of the local
SQLite database (the single source of truth).

Sync operations are idempotent and can be run multiple times safely.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.domain.models import ApplicationRecord
from src.config_loader import FilterConfig


@dataclass(frozen=True, slots=True)
class SyncReport:
    """Report of external synchronization results.

    Immutable data class summarizing the outcome of a bidirectional sync operation
    with an external system (e.g., Notion). All counts are non-negative integers.

    Attributes:
        pushed_new: Number of new applications pushed to external system
        updated_existing: Number of existing applications updated in external system
        pulled_statuses: Number of status changes pulled from external system
        interview_preps_triggered: Number of interview prep documents generated
        bootstrapped_from_notion: Number of applications imported from external system
        stalled_followups: Number of applications flagged for follow-up (>7 days stale)

    Example:
        >>> report = SyncReport(pushed_new=5, updated_existing=2, pulled_statuses=3,
        ...                     interview_preps_triggered=1, bootstrapped_from_notion=0,
        ...                     stalled_followups=2)
        >>> print(f"Synced {report.pushed_new} new, {report.updated_existing} updated")
    """
    pushed_new: int = 0
    updated_existing: int = 0
    pulled_statuses: int = 0
    interview_preps_triggered: int = 0
    bootstrapped_from_notion: int = 0
    stalled_followups: int = 0

    @property
    def bootstrapped_from_external(self) -> int:
        return self.bootstrapped_from_notion


class ExternalSyncPort(ABC):
    """Abstract interface for optional external synchronization (e.g., Notion).

    This port defines the contract for synchronizing application data with an
    external system. The implementation handles API communication, data mapping,
    and conflict resolution.

    Key principles:
    - SQLite is the single source of truth
    - External sync is best-effort and non-blocking
    - Sync is bidirectional: push local changes, pull remote status updates
    - Idempotent operations safe to retry

    Example:
        >>> sync = NotionSyncAdapter(notion_token="secret_...", database_id="...")
        >>> if sync.is_configured:
        ...     report = sync.sync()
        ...     print(f"Pushed {report.pushed_new}, Pulled {report.pulled_statuses}")
    """

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if external sync is configured and ready.

        Verifies that all required credentials and configuration are present
        and valid (e.g., Notion API token, database ID, network connectivity).

        Returns:
            True if sync can proceed, False if configuration is missing/invalid

        Example:
            >>> if notion_sync.is_configured:
            ...     report = notion_sync.sync()
            ... else:
            ...     print("Notion sync not configured - skipping")
        """
        ...

    @abstractmethod
    def sync(self) -> SyncReport:
        """Perform full bidirectional sync with external system.

        Executes the complete synchronization cycle:
        1. Push new/updated local applications to external system
        2. Pull status changes from external system to local database
        3. Generate interview prep documents for scheduled interviews
        4. Detect stalled applications needing follow-up
        5. Bootstrap any new applications from external system

        Returns:
            SyncReport with detailed counts of all sync operations performed

        Raises:
            SyncError: If API communication fails critically
            ConfigurationError: If sync is not properly configured
            RateLimitError: If external API rate limits are exceeded

        Example:
            >>> report = notion_sync.sync()
            >>> print(f"Sync completed:")
            >>> print(f"  New: {report.pushed_new}")
            >>> print(f"  Updated: {report.updated_existing}")
            >>> print(f"  Status pulls: {report.pulled_statuses}")
            >>> print(f"  Interview preps: {report.interview_preps_triggered}")
            >>> print(f"  Bootstrapped: {report.bootstrapped_from_notion}")
            >>> print(f"  Stalled follow-ups: {report.stalled_followups}")
        """
        ...

    @abstractmethod
    def sync_applications(
        self,
        applications: list[ApplicationRecord],
        config: Optional[FilterConfig] = None,
    ) -> SyncReport:
        """Sync a specific list of applications with external system.

        Allows targeted sync of a subset of applications with custom filter config.
        Useful for CQS command handler integration.

        Args:
            applications: List of ApplicationRecord objects to sync
            config: FilterConfig for matching and sync criteria

        Returns:
            SyncReport with detailed counts

        Raises:
            SyncError: If API communication fails
            ConfigurationError: If sync is not properly configured
        """
        ...


# Alias for backward compatibility
NotionSyncPort = ExternalSyncPort