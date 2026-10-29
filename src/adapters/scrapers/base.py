from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

from playwright.sync_api import Page

from src.adapters.scrapers.browser import human_delay, smooth_scroll
from src.config_loader import FilterConfig
from src.domain.models import JobOffer, PortalName, WorkModality
from src.domain.text_normalizer import strip_accents

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PortalScrapeError(Exception):
    def __init__(self, portal: PortalName, message: str, original_error: Exception | None = None) -> None:
        super().__init__(f"[{portal.value}] {message}")
        self.portal = portal
        self.original_error = original_error


@dataclass(frozen=True, slots=True)
class RawJobCard:
    portal: PortalName
    title: str
    company: str
    location: str
    url: str
    external_id: str | None = None
    modality: WorkModality = WorkModality.REMOTE


def detect_modality(text: str) -> WorkModality:
    cleaned = strip_accents(text).lower()
    if "remot" in cleaned or "teletrabaj" in cleaned or "home office" in cleaned or "100% remoto" in cleaned:
        return WorkModality.REMOTE
    if "hibrid" in cleaned or "hybrid" in cleaned:
        return WorkModality.HYBRID
    return WorkModality.ONSITE


class BasePortalScraper(ABC):
    @property
    @abstractmethod
    def portal(self) -> PortalName:
        ...

    @abstractmethod
    def build_search_urls(self, config: FilterConfig) -> list[str]:
        ...

    @abstractmethod
    def extract_cards(self, page: Page) -> list[RawJobCard]:
        ...

    @abstractmethod
    def extract_description(self, page: Page, url: str) -> str:
        ...

    def pre_filter_card(self, card: RawJobCard, config: FilterConfig) -> tuple[bool, str | None]:
        card_title = strip_accents(card.title).lower()
        for blacklisted in config.title_blacklist:
            blacklisted_norm = strip_accents(blacklisted).lower()
            if blacklisted_norm in card_title:
                return False, f"Title matched blacklist: '{blacklisted}'"

        card_company = strip_accents(card.company).lower()
        for blacklisted_comp in config.company_blacklist:
            comp_norm = strip_accents(blacklisted_comp).lower()
            if comp_norm in card_company:
                return False, f"Company matched blacklist: '{blacklisted_comp}'"

        return True, None

    def scan(
        self,
        page: Page,
        config: FilterConfig,
        limit: int = 15,
    ) -> list[JobOffer]:
        search_urls = self.build_search_urls(config)
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
                logger.warning(f"[{self.portal.value}] Failed loading search page {search_url}: {ex}")
                continue

            try:
                cards = self.extract_cards(page)
            except Exception as ex:
                logger.warning(f"[{self.portal.value}] Error extracting cards from {search_url}: {ex}")
                continue

            for card in cards:
                if len(collected_offers) >= limit:
                    break

                if card.url in seen_urls:
                    continue
                seen_urls.add(card.url)

                # Stage 1: Card-level pre-filtering (Early Exit / Return Early)
                allowed, reason = self.pre_filter_card(card, config)
                if not allowed:
                    logger.debug(f"[{self.portal.value}] Card pre-filtered out ({reason}): {card.title} @ {card.company}")
                    continue

                # Stage 2: Navigate to detail and extract full description
                try:
                    description = self.extract_description(page, card.url)
                    human_delay(1.0, 2.0)
                except Exception as ex:
                    logger.warning(f"[{self.portal.value}] Failed extracting detail for {card.url}: {ex}")
                    description = ""

                combined_text = f"{card.title} {card.location} {description}"
                modality = detect_modality(combined_text)

                offer = JobOffer(
                    portal=self.portal,
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
