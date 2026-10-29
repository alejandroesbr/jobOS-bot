from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from typing import Type

from playwright.sync_api import BrowserContext, Page

from src.adapters.scrapers.base import BasePortalScraper, PortalScrapeError
from src.adapters.scrapers.browser import create_browser_session
from src.adapters.scrapers.computrabajo import ComputrabajoScraper
from src.adapters.scrapers.elempleo import ElempleoScraper
from src.adapters.scrapers.getonbrd import GetOnBrdScraper
from src.adapters.scrapers.glassdoor import GlassdoorScraper
from src.adapters.scrapers.indeed import IndeedScraper
from src.adapters.scrapers.linkedin import LinkedInScraper
from src.config_loader import FilterConfig
from src.domain.models import JobOffer, PortalName

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
    portal: PortalName
    offers: tuple[JobOffer, ...] = ()
    error_message: str | None = None


class ScraperOrchestrator:
    def __init__(
        self,
        registry: dict[PortalName, Type[BasePortalScraper]] | None = None,
    ) -> None:
        self.registry = registry if registry is not None else dict(DEFAULT_PORTAL_REGISTRY)

    def run_scan(
        self,
        portals: list[PortalName],
        config: FilterConfig,
        headless: bool = True,
        limit_per_portal: int = 15,
        on_offer_callback: Callable[[JobOffer], None] | None = None,
    ) -> dict[PortalName, PortalScanResult]:
        results: dict[PortalName, PortalScanResult] = {}

        with create_browser_session(headless=headless) as context:
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
