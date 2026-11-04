"""Sync External Command - Mutation to sync with external systems (Notion).

This module defines the Command and Result data classes for the external
synchronization operation in the CQS architecture.

The SyncExternalCommand triggers a bidirectional sync with an external system
(currently Notion), while SyncExternalResult captures the detailed sync report.
"""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationRecord
from src.config_loader import FilterConfig


@dataclass(frozen=True, slots=True)
class SyncExternalCommand:
    """Command to sync with external system (Notion).

    Immutable command object for triggering external synchronization.
    Currently supports Notion as the only target, but designed for extensibility.

    Attributes:
        applications: List of application records to synchronize
        config: Filter configuration for sync criteria
        target: External system to sync with. Currently only "notion" is supported.
            Future targets could include "airtable", "google_sheets", etc.

    Example:
        >>> apps = repo.find_all(limit=1000)
        >>> config = load_filter_config()
        >>> command = SyncExternalCommand(
        ...     applications=apps,
        ...     config=config,
        ...     target="notion"
        ... )
    """
    applications: Optional[list[ApplicationRecord]] = None
    config: Optional[FilterConfig] = None
    target: str = "notion"  # "notion" or other future targets


@dataclass(frozen=True, slots=True)
class SyncExternalResult:
    """Result of external sync command.

    Immutable result object containing the sync report from the external system.
    All counts are non-negative integers.

    Attributes:
        pushed_new: Number of new applications pushed to external system
        updated_existing: Number of existing applications updated in external system
        pulled_statuses: Number of status changes pulled from external system
        interview_preps_triggered: Number of interview prep documents generated
        stalled_followups: Number of applications flagged for follow-up (>7 days stale)
        bootstrapped_from_external: Number of applications imported from external system
        execution_time_ms: Total command execution time in milliseconds

    Example:
        >>> result = SyncExternalResult(
        ...     pushed_new=5,
        ...     updated_existing=2,
        ...     pulled_statuses=3,
        ...     interview_preps_triggered=1,
        ...     stalled_followups=2,
        ...     bootstrapped_from_external=0,
        ...     execution_time_ms=45230
        ... )
    """
    pushed_new: int
    updated_existing: int
    pulled_statuses: int
    interview_preps_triggered: int
    stalled_followups: int
    bootstrapped_from_external: int
    execution_time_ms: int