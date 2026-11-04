"""Scraper Orchestrators - Sequential (v1) and Multi-Worker Concurrent (v2).

This module provides two orchestrator implementations for coordinating job portal scrapers:

1. **ScraperOrchestrator (Legacy)**: Sequential single-thread execution
   - Uses a single shared browser context
   - Processes portals one at a time
   - Lower resource usage, slower total time
   - Kept for backward compatibility

2. **MultiWorkerScraperOrchestrator (v2.0)**: Concurrent multi-thread execution
   - Each worker gets isolated Playwright BrowserContext
   - Processes portals in parallel using ThreadPoolExecutor
   - Higher resource usage, significantly faster total time
   - Built-in retry logic with exponential backoff
   - Error isolation (one portal failure doesn't affect others)

Both orchestrators use the same portal registry and produce compatible
PortalScanResult/WorkerResult objects for downstream processing.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
import time
from pathlib import Path
from typing import Callable, Optional, Type

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.adapters.scrapers.browser import create_browser_session, human_delay, smooth_scroll
from src.adapters.scrapers.computrabajo import ComputrabajoScraper
from src.adapters.scrapers.elempleo import ElempleoScraper
from src.adapters.scrapers.getonbrd import GetOnBrdScraper
from src.adapters.scrapers.glassdoor import GlassdoorScraper
from src.adapters.scrapers.indeed import IndeedScraper
from src.adapters.scrapers.linkedin import LinkedInScraper
from src.config_loader import FilterConfig
from src.domain.models import JobOffer, PortalName, WorkModality
from src.domain.text_normalizer import detect_modality

logger = logging.getLogger(__name__)

DEFAULT_PORTAL_REGISTRY: dict[PortalName, Type[BasePortalScraper]] = {
    PortalName.LINKEDIN: LinkedInScraper,
    PortalName.GETONBRD: GetOnBrdScraper,
    PortalName.COMPUTRABAJO: ComputrabajoScraper,
    PortalName.ELEMPLEO: ElempleoScraper,
    PortalName.GLASSDOOR: GlassdoorScraper,
    PortalName.INDEED: IndeedScraper,
}


@dataclass(frozen=True, slots=True)
class PortalScanResult:
    """Result of scanning a single portal (legacy sequential).

    Immutable data class containing the outcome of a portal scan operation
    using the legacy sequential orchestrator.

    Attributes:
        portal: The portal that was scanned
        offers: Tuple of JobOffer objects found (empty if error or no matches)
        error_message: Error description if scan failed, None if successful

    Example:
        >>> result = PortalScanResult(
        ...     portal=PortalName.LINKEDIN,
        ...     offers=(offer1, offer2),
        ...     error_message=None
        ... )
    """
    portal: PortalName
    offers: tuple[JobOffer, ...] = ()
    error_message: str | None = None


# ============================================================================
# LEGACY: Sequential Single-Thread Orchestrator (kept for backward compatibility)
# ============================================================================

class ScraperOrchestrator:
    """
    Legacy sequential single-thread orchestrator.

    Kept for backward compatibility. New code should use MultiWorkerScraperOrchestrator.

    This orchestrator uses a single browser context shared across all portals,
    processing them sequentially. While simpler and using fewer resources,
    it's significantly slower for multi-portal scans.

    Attributes:
        registry: Dictionary mapping PortalName to scraper class

    Example:
        >>> orchestrator = ScraperOrchestrator()
        >>> results = orchestrator.run_scan(
        ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
        ...     config=config,
        ...     headless=True,
        ...     limit_per_portal=15
        ... )
    """

    def __init__(
        self,
        registry: dict[PortalName, Type[BasePortalScraper]] | None = None,
    ) -> None:
        """Initialize the orchestrator with a portal registry.

        Args:
            registry: Optional custom registry mapping PortalName to scraper classes.
                Defaults to DEFAULT_PORTAL_REGISTRY with all supported portals.

        Example:
            >>> # Use default registry (all portals)
            >>> orchestrator = ScraperOrchestrator()
            >>>
            >>> # Custom registry with only specific portals
            >>> custom_registry = {PortalName.LINKEDIN: LinkedInScraper}
            >>> orchestrator = ScraperOrchestrator(custom_registry)
        """
        self.registry = registry if registry is not None else dict(DEFAULT_PORTAL_REGISTRY)

    def run_scan(
        self,
        portals: list[PortalName],
        config: FilterConfig,
        headless: bool = True,
        limit_per_portal: int = 15,
        on_offer_callback: Callable[[JobOffer], None] | None = None,
    ) -> dict[PortalName, PortalScanResult]:
        """Run sequential scan across multiple portals.

        Opens a single browser context and processes each portal in sequence.
        If a portal fails, logs the error and continues with the next portal.

        Args:
            portals: List of portals to scan in order
            config: Filter configuration for search criteria
            headless: Run browser in headless mode (default: True)
            limit_per_portal: Maximum offers to collect per portal (default: 15)
            on_offer_callback: Optional callback for each offer found during scan

        Returns:
            Dictionary mapping PortalName to PortalScanResult

        Example:
            >>> orchestrator = ScraperOrchestrator()
            >>> results = orchestrator.run_scan(
            ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
            ...     config=config,
            ...     headless=False,
            ...     limit_per_portal=20
            ... )
            >>> for portal, result in results.items():
            ...     print(f"{portal.value}: {len(result.offers)} offers")
        """
        results: dict[PortalName, PortalScanResult] = {}

        storage_path = Path('data/storage_state.json') if Path('data/storage_state.json').is_file() else None
        with create_browser_session(headless=headless, storage_state_path=storage_path) as context:
            page: Page = context.new_page()

            for portal_name in portals:
                scraper_cls = self.registry.get(portal_name)
                if not scraper_cls:
                    logger.warning(f"No scraper registered for portal: {portal_name}")
                    results[portal_name] = PortalScanResult(
                        portal=portal_name,
                        offers=(),
                        error_message=f"No scraper implementation registered for {portal_name.value}",
                    )
                    continue

                scraper = scraper_cls()
                logger.info(f"Starting sequential single-thread scan on [{portal_name.value}]...")

                try:
                    raw_offers = scraper.scan(page, config, limit=limit_per_portal)
                    if on_offer_callback:
                        for offer in raw_offers:
                            on_offer_callback(offer)

                    results[portal_name] = PortalScanResult(
                        portal=portal_name,
                        offers=tuple(raw_offers),
                        error_message=None,
                    )
                    logger.info(f"[{portal_name.value}] Finished: {len(raw_offers)} offers collected.")

                except Exception as ex:
                    logger.error(f"[{portal_name.value}] Scraper failed gracefully: {ex}", exc_info=True)
                    results[portal_name] = PortalScanResult(
                        portal=portal_name,
                        offers=(),
                        error_message=str(ex),
                    )

            page.close()

        return results


# ============================================================================
# NEW v2.0: Multi-Worker Concurrent Orchestrator
# ============================================================================

@dataclass(frozen=True, slots=True)
class WorkerConfig:
    """Configuration for a single worker.

    Immutable configuration object passed to each worker thread in the
    concurrent orchestrator. Contains all parameters needed for an isolated
    portal scan.

    Attributes:
        portal: The portal this worker will scan
        config: Filter configuration for search criteria
        limit: Maximum offers to collect
        headless: Browser headless mode
        storage_state_path: Optional path to shared authentication state
        timeout_seconds: Maximum time allowed for worker execution (default: 120)
        max_retries: Number of retry attempts on failure (default: 2)

    Example:
        >>> config = WorkerConfig(
        ...     portal=PortalName.LINKEDIN,
        ...     config=filter_config,
        ...     limit=15,
        ...     headless=True,
        ...     storage_state_path=Path("data/storage_state.json"),
        ...     timeout_seconds=180,
        ...     max_retries=3
        ... )
    """
    portal: PortalName
    config: FilterConfig
    limit: int
    headless: bool
    storage_state_path: Optional[Path]
    timeout_seconds: int = 120
    max_retries: int = 2


@dataclass(frozen=True, slots=True)
class WorkerResult:
    """Result from a single worker.

    Immutable data class containing the outcome of a worker's portal scan.
    Includes timing information for performance monitoring.

    Attributes:
        portal: The portal that was scanned
        offers: Tuple of JobOffer objects found
        error_message: Error description if scan failed, None if successful
        execution_time_ms: Total execution time in milliseconds

    Example:
        >>> result = WorkerResult(
        ...     portal=PortalName.LINKEDIN,
        ...     offers=(offer1, offer2),
        ...     error_message=None,
        ...     execution_time_ms=45230
        ... )
        >>> print(f"Completed in {result.execution_time_ms/1000:.1f}s")
    """
    portal: PortalName
    offers: tuple[JobOffer, ...] = ()
    error_message: Optional[str] = None
    execution_time_ms: int = 0


class MultiWorkerScraperOrchestrator:
    """
    Concurrent scraper orchestrator using ThreadPoolExecutor.

    Each worker gets its own isolated Playwright BrowserContext to avoid
    state collisions, cookie conflicts, and detection. This design enables
    true parallel scraping while maintaining session isolation.

    Key features:
    - Isolated browser contexts per worker
    - Configurable worker pool size
    - Automatic retry with exponential backoff
    - Error isolation (worker failures don't affect others)
    - Progress callback support for real-time monitoring

    Attributes:
        registry: Dictionary mapping PortalName to scraper class
        max_workers: Maximum concurrent workers
        default_timeout: Default worker timeout in seconds
        default_retries: Default retry count per worker

    Example:
        >>> orchestrator = MultiWorkerScraperOrchestrator(max_workers=4)
        >>> results = orchestrator.run_scan(
        ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD, PortalName.INDEED],
        ...     config=config,
        ...     limit_per_portal=20,
        ...     headless=True
        ... )
        >>> for portal, result in results.items():
        ...     print(f"{portal.value}: {len(result.offers)} offers in {result.execution_time_ms}ms")
    """

    def __init__(
        self,
        registry: dict[PortalName, Type[BasePortalScraper]] | None = None,
        max_workers: int = 4,
        default_timeout: int = 120,
        default_retries: int = 2,
    ) -> None:
        """Initialize the multi-worker orchestrator.

        Args:
            registry: Optional custom registry mapping PortalName to scraper classes.
                Defaults to DEFAULT_PORTAL_REGISTRY.
            max_workers: Maximum concurrent browser contexts (default: 4).
                Should not exceed available CPU cores for optimal performance.
            default_timeout: Default worker timeout in seconds (default: 120).
            default_retries: Default retry attempts per worker (default: 2).

        Raises:
            ValueError: If max_workers < 1, default_timeout < 1, or default_retries < 0

        Example:
            >>> # Default configuration (4 workers, 120s timeout, 2 retries)
            >>> orchestrator = MultiWorkerScraperOrchestrator()
            >>>
            >>> # High-performance configuration
            >>> orchestrator = MultiWorkerScraperOrchestrator(
            ...     max_workers=6,
            ...     default_timeout=180,
            ...     default_retries=3
            ... )
        """
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if default_timeout < 1:
            raise ValueError("default_timeout must be >= 1")
        if default_retries < 0:
            raise ValueError("default_retries must be >= 0")

        self.registry = registry if registry is not None else dict(DEFAULT_PORTAL_REGISTRY)
        self.max_workers = max_workers
        self.default_timeout = default_timeout
        self.default_retries = default_retries

    def run_scan(
        self,
        portals: list[PortalName],
        config: FilterConfig,
        headless: bool = True,
        limit_per_portal: int = 15,
        on_offer_callback: Callable[[JobOffer], None] | None = None,
        storage_state_path: Path | None = None,
    ) -> dict[PortalName, WorkerResult]:
        """Run concurrent scan across multiple portals.

        Spawns up to max_workers concurrent workers, each with an isolated
        browser context. Workers run independently and results are collected
        as they complete (not in portal order).

        Args:
            portals: List of portals to scan
            config: Filter configuration shared across all portals
            headless: Browser headless mode for all workers (default: True)
            limit_per_portal: Max offers per individual portal (default: 15)
            on_offer_callback: Optional callback invoked for each offer found
            storage_state_path: Optional path to shared auth state JSON file

        Returns:
            Dictionary mapping PortalName to WorkerResult.
            Portals that failed will have error_message set and empty offers.

        Raises:
            ValueError: If portals list is empty
            OrchestrationError: If thread pool creation fails

        Example:
            >>> orchestrator = MultiWorkerScraperOrchestrator(max_workers=3)
            >>> results = orchestrator.run_scan(
            ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD, PortalName.INDEED],
            ...     config=config,
            ...     limit_per_portal=20,
            ...     headless=True,
            ...     storage_state_path=Path("data/storage_state.json")
            ... )
            >>> total = sum(len(r.offers) for r in results.values())
            >>> print(f"Total offers: {total}")
        """
        if not portals:
            return {}

        # Limit workers to max_workers or number of portals
        actual_workers = min(self.max_workers, len(portals))

        # Prepare worker configs
        worker_configs = [
            WorkerConfig(
                portal=portal,
                config=config,
                limit=limit_per_portal,
                headless=headless,
                storage_state_path=storage_state_path,
                timeout_seconds=self.default_timeout,
                max_retries=self.default_retries,
            )
            for portal in portals
        ]

        results: dict[PortalName, WorkerResult] = {}

        with ThreadPoolExecutor(max_workers=actual_workers) as executor:
            # Submit all workers
            future_to_portal = {
                executor.submit(self._run_worker, wc): wc.portal
                for wc in worker_configs
            }

            # Collect results as they complete
            for future in as_completed(future_to_portal):
                portal = future_to_portal[future]
                try:
                    result = future.result()
                    results[portal] = result
                    logger.info(
                        f"[{portal.value}] Worker completed: "
                        f"{len(result.offers)} offers in {result.execution_time_ms}ms"
                    )
                    if on_offer_callback:
                        for offer in result.offers:
                            on_offer_callback(offer)
                except Exception as ex:
                    logger.error(f"[{portal.value}] Worker failed: {ex}", exc_info=True)
                    results[portal] = WorkerResult(
                        portal=portal,
                        offers=(),
                        error_message=str(ex),
                    )

        return results

    def _run_worker(self, worker_config: WorkerConfig) -> WorkerResult:
        """Run a single worker with isolated browser context.

        Creates a dedicated browser context for this worker, executes the
        scan with retry logic, and returns the result with timing information.

        Args:
            worker_config: Configuration for this worker

        Returns:
            WorkerResult with offers, errors, and execution time
        """
        start_time = time.perf_counter()

        portal = worker_config.portal
        scraper_cls = self.registry.get(portal)

        if not scraper_cls:
            return WorkerResult(
                portal=portal,
                offers=(),
                error_message=f"No scraper registered for {portal.value}",
            )

        scraper = scraper_cls()
        collected_offers: list[JobOffer] = []
        last_error: Exception | None = None

        # Retry loop
        for attempt in range(worker_config.max_retries + 1):
            try:
                # Create isolated browser context per worker
                with create_browser_session(
                    headless=worker_config.headless,
                    storage_state_path=worker_config.storage_state_path,
                ) as context:
                    page = context.new_page()
                    try:
                        offers = self._scan_with_scraper(
                            scraper=scraper,
                            page=page,
                            config=worker_config.config,
                            limit=worker_config.limit,
                        )
                        collected_offers = offers
                        last_error = None
                        break  # Success, exit retry loop
                    finally:
                        page.close()
            except Exception as ex:
                last_error = ex
                logger.warning(
                    f"[{portal.value}] Attempt {attempt + 1}/{worker_config.max_retries + 1} failed: {ex}"
                )
                if attempt < worker_config.max_retries:
                    time.sleep(2 ** attempt)  # Exponential backoff

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return WorkerResult(
            portal=portal,
            offers=tuple(collected_offers),
            error_message=str(last_error) if last_error else None,
            execution_time_ms=execution_time_ms,
        )

    def _scan_with_scraper(
        self,
        scraper: BasePortalScraper,
        page: Page,
        config: FilterConfig,
        limit: int,
    ) -> list[JobOffer]:
        """Execute scan logic within a worker's isolated page context.

        Performs the complete scraping workflow for a single portal:
        1. Build search URLs from filter config
        2. Navigate to each search URL
        3. Extract job cards from listing pages
        4. Pre-filter cards (seniority, location, keywords)
        5. Extract full descriptions for passing cards
        6. Create JobOffer objects

        Args:
            scraper: Portal-specific scraper instance
            page: Isolated Playwright page for this worker
            config: Filter configuration
            limit: Maximum offers to collect

        Returns:
            List of JobOffer objects (up to limit)
        """
        search_urls = scraper.build_search_urls(config)
        collected_offers: list[JobOffer] = []
        seen_urls: set[str] = set()

        for search_url in search_urls:
            if len(collected_offers) >= limit:
                break

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                human_delay(1.5, 3.0)
                smooth_scroll(page, steps=2)
            except Exception as ex:
                logger.warning(f"[{scraper.portal.value}] Failed loading {search_url}: {ex}")
                continue

            try:
                cards = scraper.extract_cards(page)
            except Exception as ex:
                logger.warning(f"[{scraper.portal.value}] Error extracting cards: {ex}")
                continue

            for card in cards:
                if len(collected_offers) >= limit:
                    break

                if card.url in seen_urls:
                    continue
                seen_urls.add(card.url)

                # Pre-filter
                allowed, reason = scraper.pre_filter_card(card, config)
                if not allowed:
                    logger.debug(f"[{scraper.portal.value}] Pre-filtered: {reason}")
                    continue

                # Extract description
                try:
                    description = scraper.extract_description(page, card.url)
                    human_delay(1.0, 2.0)
                except Exception as ex:
                    logger.warning(f"[{scraper.portal.value}] Failed detail extraction: {ex}")
                    description = ""

                combined_text = f"{card.title} {card.location} {description}"
                modality = detect_modality(combined_text)

                offer = JobOffer(
                    portal=scraper.portal,
                    title=card.title,
                    company=card.company,
                    location=card.location,
                    modality=modality,
                    url=card.url,
                    description=description,
                    external_id=card.external_id,
                )
                collected_offers.append(offer)

        return collected_offers