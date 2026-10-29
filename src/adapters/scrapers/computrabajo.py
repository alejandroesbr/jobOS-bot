from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName

BASE_DOMAIN = "https://co.computrabajo.com"


class ComputrabajoScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.COMPUTRABAJO

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            f"{BASE_DOMAIN}/trabajo-de-desarrollador-en-barranquilla",
            f"{BASE_DOMAIN}/trabajo-de-desarrollador-remoto",
            f"{BASE_DOMAIN}/trabajo-de-programador-en-barranquilla",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator("article.box_offer, article[data-id]").all()

        for card_el in locators:
            title_el = card_el.locator("h2 a.js-o-link, h1.fs24 a, h2 a").first
            company_el = card_el.locator("p.fs16 a, p.fs16, .dIB").first
            location_el = card_el.locator("p.fs16 span, span.item-location").first
            link_el = card_el.locator("a.js-o-link, a").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Empresa Confidencial"
            location = location_el.inner_text().strip() if location_el.count() else "Colombia"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            full_url = urljoin(BASE_DOMAIN, raw_url).split("?")[0]
            external_id = card_el.get_attribute("data-id")

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
        desc_el = page.locator("div.box_detail, div.box_border .fs16, [data-section='description']").first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
