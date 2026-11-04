"""Scan Portals Command - Mutation to scan portals and persist results.

This module defines the Command and Result data classes for the portal scanning
operation in the CQS (Command Query Separation) architecture.

The ScanPortalsCommand encapsulates all parameters needed to execute a multi-portal
scan, while ScanPortalsResult captures the detailed outcome including statistics
for monitoring and debugging.
"""
from dataclasses import dataclass
from typing import Optional

from src.config_loader import FilterConfig
from src.domain.models import PortalName


@dataclass(frozen=True, slots=True)
class ScanPortalsCommand:
    """Command to scan job portals and record matching offers.

    Immutable command object containing all parameters for a portal scan operation.
    This is the input to the ScanPortalsHandler which orchestrates the complete
    scan-match-persist-sync workflow.

    Attributes:
        portals: List of portals to scan (e.g., [PortalName.LINKEDIN, PortalName.GETONBRD])
        limit_per_portal: Maximum offers to collect per portal (default: 15)
        headless: Run browsers in headless mode (default: True)
        max_workers: Maximum concurrent workers for MultiWorkerScraperOrchestrator (default: 4)
        sync_obsidian: Whether to sync results to Obsidian vault after scan (default: True)
        vault_path: Path to Obsidian vault for sync (default: "vault")
        config: Optional FilterConfig override. If None, loads from config/filters.yaml

    Example:
        >>> command = ScanPortalsCommand(
        ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
        ...     limit_per_portal=20,
        ...     headless=True,
        ...     max_workers=3,
        ...     sync_obsidian=True,
        ...     vault_path="~/vaults/job-search"
        ... )
    """
    portals: list[PortalName]
    limit_per_portal: int = 15
    headless: bool = True
    max_workers: int = 4
    sync_obsidian: bool = True
    vault_path: str = "vault"
    config: Optional[FilterConfig] = None


@dataclass(frozen=True, slots=True)
class ScanPortalsResult:
    """Result of scan portals command.

    Immutable result object containing comprehensive statistics from a scan operation.
    Used for CLI output, logging, and monitoring.

    Attributes:
        total_scanned: Total job offers found across all portals (before filtering)
        total_matched: Total offers that passed matching criteria (should_apply=True)
        new_applications: Number of first-time applications recorded
        reapplications: Number of re-applications to previously seen offers
        skipped_cooldown: Number of offers skipped due to re-application cooldown
        hard_rejected: Number of offers rejected by hard filters (seniority, etc.)
        offers_by_portal: Dict mapping portal name to offer count found
        errors_by_portal: Dict mapping portal name to error message (if any)
        obsidian_synced: Whether Obsidian sync was performed
        obsidian_created: Number of new application notes created in vault
        obsidian_updated: Number of existing application notes updated in vault
        execution_time_ms: Total command execution time in milliseconds

    Example:
        >>> result = ScanPortalsResult(
        ...     total_scanned=45,
        ...     total_matched=12,
        ...     new_applications=8,
        ...     reapplications=3,
        ...     skipped_cooldown=1,
        ...     hard_rejected=33,
        ...     offers_by_portal={"LinkedIn": 25, "GetOnBrd": 20},
        ...     errors_by_portal={},
        ...     obsidian_synced=True,
        ...     obsidian_created=8,
        ...     obsidian_updated=3,
        ...     execution_time_ms=125430
        ... )
    """
    total_scanned: int
    total_matched: int
    new_applications: int
    reapplications: int
    skipped_cooldown: int
    hard_rejected: int
    offers_by_portal: dict[str, int]
    errors_by_portal: dict[str, str]
    obsidian_synced: bool
    obsidian_created: int
    obsidian_updated: int
    execution_time_ms: int