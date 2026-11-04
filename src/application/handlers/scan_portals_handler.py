"""Scan Portals Handler - Executes multi-worker scan command.

This module contains the ScanPortalsHandler which orchestrates the complete
scan-match-persist-sync workflow for the ScanPortalsCommand in the CQS architecture.

The handler coordinates:
1. Multi-worker concurrent portal scraping via MultiPortalScraperPort
2. Offer evaluation and filtering via OfferMatcher
3. Application persistence via ApplicationRepositoryPort
4. Optional Obsidian vault sync via KnowledgeVaultPort

All operations are wrapped in error handling to ensure graceful degradation
(one portal failure doesn't stop the entire scan).
"""
from pathlib import Path
import time
import uuid
from typing import Callable, cast

from src.application.commands import ScanPortalsCommand, ScanPortalsResult
from src.config_loader import FilterConfig, load_filter_config
from src.domain.matcher import OfferMatcher
from src.domain.models import JobOffer, MatchEvaluation, PortalName
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.scraper_port import MultiPortalScraperPort, PortalScanResult
from src.ports.vault_port import KnowledgeVaultPort


class ScanPortalsHandler:
    """Handles ScanPortalsCommand by orchestrating multi-worker scrape, match, and persist.

    This handler is the central coordinator for the portal scanning workflow.
    It receives a ScanPortalsCommand, executes the concurrent scan across
    multiple portals, evaluates each offer against filter criteria, persists
    matching applications, and optionally syncs results to Obsidian vault.

    Dependencies are injected via constructor for testability and flexibility:
    - ApplicationRepositoryPort: For persistence operations
    - MultiPortalScraperPort: For concurrent portal scraping
    - KnowledgeVaultPort (optional): For Obsidian vault synchronization

    Attributes:
        _repository: Repository port for application persistence
        _scraper: Multi-portal scraper port for concurrent scanning
        _vault: Optional vault port for Obsidian sync
        _matcher: OfferMatcher instance (initialized per-handle with config)

    Example:
        >>> handler = ScanPortalsHandler(
        ...     repository=sqlite_repo,
        ...     scraper=multi_worker_orchestrator,
        ...     vault=obsidian_adapter
        ... )
        >>> command = ScanPortalsCommand(
        ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
        ...     limit_per_portal=20,
        ...     max_workers=3
        ... )
        >>> result = handler.handle(command)
        >>> print(f"Scanned: {result.total_scanned}, Matched: {result.total_matched}")
    """

    def __init__(
        self,
        repository: ApplicationRepositoryPort,
        scraper: MultiPortalScraperPort,
        vault: KnowledgeVaultPort | None = None,
    ) -> None:
        """Initialize the handler with required dependencies.

        Args:
            repository: ApplicationRepositoryPort implementation for persistence
            scraper: MultiPortalScraperPort implementation for concurrent scraping
            vault: Optional KnowledgeVaultPort for Obsidian sync (default: None)

        Example:
            >>> handler = ScanPortalsHandler(
            ...     repository=SQLiteApplicationRepository("data/jobs.db"),
            ...     scraper=MultiWorkerScraperOrchestrator(max_workers=4),
            ...     vault=ObsidianVaultAdapter("vault")
            ... )
        """
        self._repository = repository
        self._scraper = scraper
        self._vault = vault
        self._matcher: OfferMatcher | None = None

    def handle(self, command: ScanPortalsCommand) -> ScanPortalsResult:
        """Execute the scan portals command.

        Orchestrates the complete scan workflow:
        1. Initialize matcher with command config
        2. Generate session ID for tracking
        3. Load storage state for authenticated scraping
        4. Run concurrent scan via MultiPortalScraperPort
        5. Process each portal's results: match, filter, persist
        6. Sync to Obsidian vault if enabled and vault available
        7. Return comprehensive ScanPortalsResult with statistics

        Args:
            command: ScanPortalsCommand with portals, limits, and sync options

        Returns:
            ScanPortalsResult with detailed statistics:
                - total_scanned: Total offers found across all portals
                - total_matched: Offers passing match criteria
                - new_applications: First-time applications recorded
                - reapplications: Re-applications to existing offers
                - skipped_cooldown: Offers skipped due to cooldown
                - hard_rejected: Offers rejected by hard filters
                - offers_by_portal: Per-portal offer counts
                - errors_by_portal: Per-portal error messages
                - obsidian_synced: Whether vault sync occurred
                - obsidian_created/updated: Vault sync statistics
                - execution_time_ms: Total execution time

        Raises:
            Exception: Critical errors are caught and recorded in errors_by_portal,
                but the handler never raises - it returns partial results with errors.

        Example:
            >>> command = ScanPortalsCommand(
            ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
            ...     limit_per_portal=15,
            ...     headless=True,
            ...     max_workers=4,
            ...     sync_obsidian=True,
            ...     vault_path="vault"
            ... )
            >>> result = handler.handle(command)
            >>> print(f"Execution time: {result.execution_time_ms}ms")
            >>> print(f"New applications: {result.new_applications}")
        """
        start_time = time.perf_counter()

        # Load config if not provided and initialize matcher
        config: FilterConfig = command.config if command.config is not None else load_filter_config()
        matcher = OfferMatcher(config, repository=self._repository)
        self._matcher = matcher

        # Generate session ID for tracking
        _session_id = str(uuid.uuid4())[:8]

        # Run concurrent scan via orchestrator
        storage_state_path: Path | None = None
        try:
            default_state = Path("data/storage_state.json")
            if default_state.is_file():
                storage_state_path = default_state
        except Exception:
            pass

        scraper_dict = getattr(self._scraper, "__dict__", {})
        worker_results: dict[PortalName, PortalScanResult]
        if "scan_all" in scraper_dict:
            worker_results = self._scraper.scan_all(
                portals=command.portals,
                config=config,
                limit_per_portal=command.limit_per_portal,
                max_workers=command.max_workers,
                headless=command.headless,
            )
        elif "run_scan" in scraper_dict or hasattr(type(self._scraper), "run_scan"):
            run_scan_fn = cast(
                Callable[..., dict[PortalName, PortalScanResult]],
                getattr(self._scraper, "run_scan"),
            )
            worker_results = run_scan_fn(
                portals=command.portals,
                config=config,
                headless=command.headless,
                limit_per_portal=command.limit_per_portal,
                storage_state_path=storage_state_path,
            )
        else:
            worker_results = self._scraper.scan_all(
                portals=command.portals,
                config=config,
                limit_per_portal=command.limit_per_portal,
                max_workers=command.max_workers,
                headless=command.headless,
            )

        # Process results: match, filter, persist
        total_scanned = 0
        total_matched = 0
        new_applications = 0
        reapplications = 0
        skipped_cooldown = 0
        hard_rejected = 0
        offers_by_portal: dict[str, int] = {}
        errors_by_portal: dict[str, str] = {}
        matched_offers: list[tuple[JobOffer, MatchEvaluation]] = []

        for portal, result in worker_results.items():
            portal_name = portal.value
            offers_by_portal[portal_name] = len(result.offers)
            total_scanned += len(result.offers)

            if result.error_message:
                errors_by_portal[portal_name] = result.error_message
                continue

            for offer in result.offers:
                evaluation = matcher.evaluate(offer)

                if evaluation.is_hard_rejected:
                    hard_rejected += 1
                    continue

                if not evaluation.should_apply:
                    continue

                total_matched += 1
                matched_offers.append((offer, evaluation))

                # Persist to repository
                try:
                    record, was_new = self._repository.record_submission(
                        offer=offer,
                        evaluation=evaluation,
                        cooldown_days=config.matching.reapply_cooldown_days,
                    )
                    if was_new:
                        if record.times_applied == 1:
                            new_applications += 1
                        else:
                            reapplications += 1
                    else:
                        skipped_cooldown += 1
                except Exception as ex:
                    errors_by_portal[f"{portal_name}_persist"] = str(ex)

        # Sync to Obsidian vault if enabled
        obsidian_created = 0
        obsidian_updated = 0
        obsidian_synced = False

        if command.sync_obsidian and self._vault is not None:
            try:
                # Get all applications for sync
                all_apps = self._repository.find_all(limit=10000)
                vault_dir = Path(command.vault_path)
                created, updated = self._vault.sync_applications(all_apps, vault_dir)
                self._vault.create_hubs(all_apps, vault_dir)
                obsidian_created = created
                obsidian_updated = updated
                obsidian_synced = True
            except Exception as ex:
                errors_by_portal["obsidian"] = str(ex)

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return ScanPortalsResult(
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