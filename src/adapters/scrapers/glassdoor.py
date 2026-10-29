from urllib.parse import urljoin

from playwright.sync_api import Page

from src.adapters.scrapers.base import BasePortalScraper, RawJobCard
from src.config_loader import FilterConfig
from src.domain.models import PortalName

BASE_DOMAIN = "https://www.glassdoor.com"


class GlassdoorScraper(BasePortalScraper):
    @property
    def portal(self) -> PortalName:
        return PortalName.GLASSDOOR

    def build_search_urls(self, config: FilterConfig) -> list[str]:
        return [
            f"{BASE_DOMAIN}/Job/colombia-developer-jobs-SRCH_IL.0,8_IN55_KO9,18.htm",
            f"{BASE_DOMAIN}/Job/colombia-junior-developer-jobs-SRCH_IL.0,8_IN55_KO9,25.htm",
        ]

    def extract_cards(self, page: Page) -> list[RawJobCard]:
        cards: list[RawJobCard] = []
        locators = page.locator("li[data-test='jobListing'], .JobCard_jobCardContainer___prPt, article").all()

        for card_el in locators:
            title_el = card_el.locator("a.JobCard_jobTitle___5kW8, [data-test='job-title']").first
            company_el = card_el.locator(".EmployerProfile_compactEmployerName__LE242, [data-test='employer-name']").first
            location_el = card_el.locator("[data-test='emp-location'], .JobCard_location__rCzMG").first
            link_el = card_el.locator("a.JobCard_jobTitle___5kW8, a[data-test='job-link'], a").first

            if not title_el.count() or not link_el.count():
                continue

            title = title_el.inner_text().strip()
            company = company_el.inner_text().strip() if company_el.count() else "Empresa Confidencial"
            location = location_el.inner_text().strip() if location_el.count() else "Colombia (Remoto)"
            raw_url = link_el.get_attribute("href") or ""
            if not raw_url:
                continue

            full_url = urljoin(BASE_DOMAIN, raw_url).split("?")[0]
            external_id = card_el.get_attribute("data-jobid") or card_el.get_attribute("data-id")

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
        desc_el = page.locator(
            ".JobDetails_jobDescription__uW_fK, [data-test='jobDescription'], div.jobDescriptionContent"
        ).first
        if desc_el.count():
            return desc_el.inner_text().strip()
        body_el = page.locator("main, body").first
        return body_el.inner_text().strip() if body_el.count() else ""
