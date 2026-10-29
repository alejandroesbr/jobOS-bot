import re
from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName

BASE_DOMAIN = "https://co.indeed.com"


class IndeedScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.INDEED

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            f"{BASE_DOMAIN}/jobs?q=desarrollador&l=Remoto",
            f"{BASE_DOMAIN}/jobs?q=junior+developer&l=Colombia",
            f"{BASE_DOMAIN}/jobs?q=react+node&l=Colombia",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator(".job_seen_beacon, div.cardOutline, div[data-jk]").all()

        for card_el in locators:
            title_el = card_el.locator("h2.jobTitle span, h2.jobTitle a, a[data-jk]").first
            company_el = card_el.locator("[data-testid='company-name'], .companyName, span.css-63koeb").first
            location_el = card_el.locator("[data-testid='text-location'], .companyLocation").first
            link_el = card_el.locator("h2.jobTitle a, a[data-jk], a").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Empresa Confidencial"
            location = location_el.inner_text().strip() if location_el.count() else "Colombia (Remoto)"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            full_url = urljoin(BASE_DOMAIN, raw_url)
            clean_url = full_url.split("&")[0] if "&" in full_url else full_url

            jk_match = re.search(r"jk=([a-zA-Z0-9]+)", full_url)
            external_id = jk_match.group(1) if jk_match else card_el.get_attribute("data-jk")

            cards.append(
                RawJobCard(
                    portal=self.portal,
                    title=title,
                    company=company,
                    location=location,
                    url=clean_url,
                    external_id=external_id,
                )
            )

        return cards

    def extract_description(self, page: Page, url: str) -> str:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        desc_el = page.locator("#jobDescriptionText, div.jobsearch-jobDescriptionText").first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
