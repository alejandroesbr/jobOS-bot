from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName

BASE_DOMAIN = "https://www.elempleo.com"


class ElempleoScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.ELEMPLEO

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            f"{BASE_DOMAIN}/co/ofertas-empleo/desarrollador/remoto",
            f"{BASE_DOMAIN}/co/ofertas-empleo/desarrollador/barranquilla",
            f"{BASE_DOMAIN}/co/ofertas-empleo/ingeniero-de-sistemas/remoto",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator(".result-item, .job-item, div.info-offer").all()

        for card_el in locators:
            title_el = card_el.locator("a.js-job-link, h2.text-ellipsis a, h2 a").first
            company_el = card_el.locator(".info-company, .company-name, span.info-company-name").first
            location_el = card_el.locator(".info-city, .info-country, span.info-location").first
            link_el = card_el.locator("a.js-job-link, a").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Empresa Confidencial"
            location = location_el.inner_text().strip() if location_el.count() else "Colombia"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            full_url = urljoin(BASE_DOMAIN, raw_url).split("?")[0]
            external_id = card_el.get_attribute("data-id") or full_url.rstrip("/").split("/")[-1]

            cards.append(
                RawJobCard(
                    portal=self.portal,
                    title=title,
                    company=company,
                    location=location,
                    url=full_url,
                    external_id=external_id,
                )
            )

        return cards

    def extract_description(self, page: Page, url: str) -> str:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        desc_el = page.locator(".job-description, .description-offer, div.description").first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
