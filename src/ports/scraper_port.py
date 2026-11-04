"""Portal Scraper Port - Abstract interfaces for job portal scraping.

This module defines the abstract interfaces (Ports) for scraping job portals,
following the Clean Architecture pattern. Concrete implementations (Adapters)
handle portal-specific scraping logic using Playwright.

Two interfaces are provided:
- PortalScraperPort: For scraping a single portal
- MultiPortalScraperPort: For orchestrating concurrent multi-portal scans

The ports isolate the application layer from scraping implementation details,
enabling:
- Easy testing with mock scrapers
- Adding new portals without changing orchestration logic
- Swapping scraping strategies (sequential vs concurrent)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from playwright.sync_api import Page

from src.config_loader import FilterConfig
from src.domain.models import JobOffer, PortalName


@dataclass(frozen=True, slots=True)
class PortalScanResult:
    """Result of scanning a single portal.

    Immutable data class containing the outcome of a portal scan operation.
    Includes either collected job offers or an error message if the scan failed.

    Attributes:
        portal: The portal that was scanned
        offers: Tuple of JobOffer objects found (empty if error or no matches)
        error_message: Error description if scan failed, None if successful
        execution_time_ms: Total execution time in milliseconds

    Example:
        >>> result = PortalScanResult(
        ...     portal=PortalName.LINKEDIN,
        ...     offers=(offer1, offer2),
        ...     error_message=None
        ... )
        >>> print(f"Found {len(result.offers)} offers on {result.portal.value}")
    """
    portal: PortalName
    offers: tuple[JobOffer, ...] = ()
    error_message: Optional[str] = None
    execution_time_ms: int = 0


class PortalScraperPort(ABC):
    """Abstract interface for scraping a single job portal.

    Each portal (LinkedIn, GetOnBrd, Computrabajo, etc.) implements this interface
    with portal-specific logic for:
    - Building search URLs from filter configuration
    - Navigating and extracting job cards from listing pages
    - Extracting detailed job descriptions from detail pages
    - Pre-filtering cards before expensive detail extraction

    Implementations must be stateless and thread-safe (no shared browser state).
    The orchestrator provides an isolated browser context per scan.

    Attributes:
        portal_name: The PortalName enum value this scraper handles
    """

    @property
    @abstractmethod
    def portal(self) -> PortalName:
        """Return the portal this scraper handles."""
        ...

    @property
    def portal_name(self) -> PortalName:
        """Return the portal this scraper handles."""
        return self.portal

    @abstractmethod
    def scan(
        self,
        page: Page,
        config: FilterConfig,
        limit: int = 15,
    ) -> list[JobOffer]:
        """Scan the portal for job offers matching the filter configuration.

        This is the main entry point for scraping a portal. The implementation
        should:
        1. Build search URLs from the filter config
        2. Navigate to each search URL
        3. Extract job cards from listing pages
        4. Pre-filter cards (seniority, location, keywords)
        5. Extract full descriptions for passing cards
        6. Create JobOffer objects and return them

        Args:
            config: FilterConfig containing keywords, locations, modalities,
                seniority filters, and other search criteria
            limit_per_portal: Maximum number of offers to collect (default: 15)
            headless: Whether to run browser in headless mode (default: True)
            on_offer_callback: Optional callback invoked for each offer found.
                Useful for real-time processing or progress reporting.

        Returns:
            PortalScanResult containing:
                - portal: The portal scanned
                - offers: Tuple of JobOffer objects (max limit_per_portal)
                - error_message: None if successful, error string if failed

        Raises:
            ScraperError: If browser automation fails critically
            ConfigurationError: If config is invalid for this portal
            TimeoutError: If page load or element wait times out

        Example:
            >>> from src.config_loader import FilterConfig, load_filter_config
            >>> config = load_filter_config()
            >>> scraper = LinkedInScraper()
            >>> result = scraper.scan(config, limit_per_portal=10, headless=False)
            >>> if result.error_message:
            ...     print(f"Scan failed: {result.error_message}")
            ... else:
            ...     print(f"Found {len(result.offers)} offers")
        """
        ...


class MultiPortalScraperPort(ABC):
    """Abstract interface for orchestrating multiple portal scrapers concurrently.

    This port defines the contract for a multi-portal orchestrator that can
    scan multiple portals in parallel using a thread pool. Implementations
    handle worker lifecycle, error isolation, and result aggregation.

    The concurrent approach significantly reduces total scan time compared to
    sequential scanning, at the cost of higher resource usage (multiple browser
    contexts).

    Example:
        >>> orchestrator = MultiWorkerScraperOrchestrator(max_workers=4)
        >>> results = orchestrator.scan_all(
        ...     portals=[PortalName.LINKEDIN, PortalName.GETONBRD],
        ...     config=config,
        ...     limit_per_portal=15,
        ...     headless=True
        ... )
        >>> for portal, result in results.items():
        ...     print(f"{portal.value}: {len(result.offers)} offers")
    """

    @abstractmethod
    def scan_all(
        self,
        portals: list[PortalName],
        config: FilterConfig,
        limit_per_portal: int = 15,
        max_workers: int = 4,
        headless: bool = True,
    ) -> dict[PortalName, PortalScanResult]:
        """Scan multiple portals concurrently."""
        ...

    @abstractmethod
    def run_scan(
        self,
        portals: list[PortalName],
        config: FilterConfig,
        headless: bool = True,
        limit_per_portal: int = 15,
        on_offer_callback: Optional[Callable[[JobOffer], None]] = None,
        storage_state_path: Optional[Path] = None,
    ) -> dict[PortalName, PortalScanResult]:
        """Run concurrent scan across multiple portals."""
        ...