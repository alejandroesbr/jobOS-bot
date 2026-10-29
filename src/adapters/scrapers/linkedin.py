import re
from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName


class LinkedInScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.LINKEDIN

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            "https://www.linkedin.com/jobs/search?keywords=desarrollador+full+stack&location=Colombia&f_TPR=r86400&position=1&pageNum=0",
            "https://www.linkedin.com/jobs/search?keywords=react+node&location=Colombia&f_TPR=r86400&position=1&pageNum=0",
            "https://www.linkedin.com/jobs/search?keywords=junior+software+engineer&location=Colombia&f_TPR=r86400&position=1&pageNum=0",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator("ul.jobs-search__results-list > li, div.job-search-card, .base-card").all()

        for card_el in locators:
            title_el = card_el.locator("h3.base-search-card__title, .base-search-card__title").first
            company_el = card_el.locator("h4.base-search-card__subtitle, .base-search-card__subtitle").first
            location_el = card_el.locator(".job-search-card__location, span.job-search-card__location").first
            link_el = card_el.locator("a.base-card__full-link, a").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Empresa Confidencial"
            location = location_el.inner_text().strip() if location_el.count() else "Colombia (Remoto)"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            canonical_url = raw_url.split("?")[0]
            ext_id_match = re.search(r"/view/(\d+)", canonical_url)
            external_id = ext_id_match.group(1) if ext_id_match else None

            cards.append(
                RawJobCard(
                    portal=self.portal,
                    title=title,
                    company=company,
                    location=location,
                    url=canonical_url,
                    external_id=external_id,
                )
            )

        return cards

    def extract_description(self, page: Page, url: str) -> str:
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        desc_el = page.locator(
            ".show-more-less-html__markup, .description__text, div.decorated-job-posting__details"
        ).first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
