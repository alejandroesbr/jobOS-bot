from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName

BASE_DOMAIN = "https://www.getonbrd.com"


class GetOnBrdScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.GETONBRD

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            f"{BASE_DOMAIN}/jobs-programming?remote=true",
            f"{BASE_DOMAIN}/jobs/programming?web=true",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator("[data-job-id], .gb-results-list > div").all()

        for card_el in locators:
            title_el = card_el.locator("h4, .color-hierarchy, .color-hierarchy-title").first
            company_el = card_el.locator(".color-hierarchy-sub, .size0 strong").first
            link_el = card_el.locator("a[href*='/jobs/']").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Startup Tech"
            location = "Remoto Latam"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            full_url = urljoin(BASE_DOMAIN, raw_url).split("?")[0]
            external_id = card_el.get_attribute("data-job-id")

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
        desc_el = page.locator("#job-body, .job-description, [data-section='body']").first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
