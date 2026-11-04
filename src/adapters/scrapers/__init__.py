"""Scrapers package - Portal scraping adapters."""
from src.adapters.scrapers.orchestrator import (
    MultiWorkerScraperOrchestrator,
    PortalScanResult,
    WorkerResult,
    WorkerConfig,
    DEFAULT_PORTAL_REGISTRY,
)
from src.adapters.scrapers.base import BasePortalScraper, PortalScrapeError, RawJobCard, detect_modality
from src.adapters.scrapers.linkedin import LinkedInScraper
from src.adapters.scrapers.getonbrd import GetOnBrdScraper
from src.adapters.scrapers.computrabajo import ComputrabajoScraper
from src.adapters.scrapers.elempleo import ElempleoScraper
from src.adapters.scrapers.glassdoor import GlassdoorScraper
from src.adapters.scrapers.indeed import IndeedScraper
from src.adapters.scrapers.browser import create_browser_session, human_delay, smooth_scroll

__all__ = [
    # Orchestrators
    "MultiWorkerScraperOrchestrator",
    "PortalScanResult",
    "WorkerResult",
    "WorkerConfig",
    "DEFAULT_PORTAL_REGISTRY",
    # Base
    "BasePortalScraper",
    "PortalScrapeError",
    "RawJobCard",
    "detect_modality",
    # Scrapers
    "LinkedInScraper",
    "GetOnBrdScraper",
    "ComputrabajoScraper",
    "ElempleoScraper",
    "GlassdoorScraper",
    "IndeedScraper",
    # Browser
    "create_browser_session",
    "human_delay",
    "smooth_scroll",
]