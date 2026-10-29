from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from src.adapters.db.repository import ApplicationRepository
from src.adapters.scrapers.base import BasePortalScraper, RawJobCard, detect_modality
from src.adapters.scrapers.computrabajo import ComputrabajoScraper
from src.adapters.scrapers.elempleo import ElempleoScraper
from src.adapters.scrapers.getonbrd import GetOnBrdScraper
from src.adapters.scrapers.glassdoor import GlassdoorScraper
from src.adapters.scrapers.indeed import IndeedScraper
from src.adapters.scrapers.linkedin import LinkedInScraper
from src.adapters.scrapers.orchestrator import ScraperOrchestrator
from src.config_loader import FilterConfig, load_filter_config
from src.domain.models import JobOffer, PortalName, WorkModality
from src.services.scan_service import ScanService


@pytest.fixture
def filter_config() -> FilterConfig:
    return load_filter_config("config/filters.yaml")


@pytest.fixture
def repo() -> Iterator[ApplicationRepository]:
    repository = ApplicationRepository(":memory:")
    yield repository
    repository.close()


def test_detect_modality() -> None:
    assert detect_modality("Desarrollador Full Stack 100% Remoto") == WorkModality.REMOTE
    assert detect_modality("Software Engineer - Teletrabajo Latam") == WorkModality.REMOTE
    assert detect_modality("Ingeniero de Software Híbrido en Barranquilla") == WorkModality.HYBRID
    assert detect_modality("Desarrollador Web Presencial en Sede") == WorkModality.ONSITE


def test_scraper_card_pre_filtering_rejects_blacklist(filter_config: FilterConfig) -> None:
    scraper = GetOnBrdScraper()

    # 1. Senior title should be rejected at card stage
    card_senior = RawJobCard(
        portal=PortalName.GETONBRD,
        title="Senior React Architect",
        company="Global Tech",
        location="Remoto",
        url="https://getonbrd.com/jobs/senior-1",
    )
    allowed, reason = scraper.pre_filter_card(card_senior, filter_config)
    assert allowed is False
    assert "senior" in str(reason).lower()

    # 2. Blacklisted company should be rejected
    card_spam = RawJobCard(
        portal=PortalName.GETONBRD,
        title="Junior Developer",
        company="Spam Staffing LLC",
        location="Remoto",
        url="https://getonbrd.com/jobs/dev-1",
    )
    allowed, reason = scraper.pre_filter_card(card_spam, filter_config)
    assert allowed is False
    assert "company" in str(reason).lower()

    # 3. Valid junior card should be accepted
    card_junior = RawJobCard(
        portal=PortalName.GETONBRD,
        title="Desarrollador Full Stack Junior",
        company="Innovatech Colombia",
        location="Remoto",
        url="https://getonbrd.com/jobs/jr-1",
    )
    allowed, reason = scraper.pre_filter_card(card_junior, filter_config)
    assert allowed is True
    assert reason is None


def test_orchestrator_contains_all_six_portal_adapters() -> None:
    orchestrator = ScraperOrchestrator()
    assert len(orchestrator.registry) == 6
    assert orchestrator.registry[PortalName.LINKEDIN] is LinkedInScraper
    assert orchestrator.registry[PortalName.GETONBRD] is GetOnBrdScraper
    assert orchestrator.registry[PortalName.COMPUTRABAJO] is ComputrabajoScraper
    assert orchestrator.registry[PortalName.ELEMPLEO] is ElempleoScraper
    assert orchestrator.registry[PortalName.GLASSDOOR] is GlassdoorScraper
    assert orchestrator.registry[PortalName.INDEED] is IndeedScraper


def test_orchestrator_handles_missing_or_failing_scraper_gracefully(filter_config: FilterConfig) -> None:
    # Custom scraper that throws an exception
    failing_scraper_cls = MagicMock()
    failing_instance = failing_scraper_cls.return_value
    failing_instance.scan.side_effect = RuntimeError("Cloudflare challenge block")

    orchestrator = ScraperOrchestrator(
        registry={
            PortalName.GETONBRD: failing_scraper_cls,
        }
    )

    # Mock the browser session so we don't open a real browser
    mock_context = MagicMock()
    mock_page = MagicMock()
    mock_context.new_page.return_value = mock_page

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.adapters.scrapers.orchestrator.create_browser_session",
            MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=mock_context), __exit__=MagicMock())),
        )
        results = orchestrator.run_scan([PortalName.GETONBRD], filter_config)

    assert PortalName.GETONBRD in results
    result = results[PortalName.GETONBRD]
    assert len(result.offers) == 0
    assert "Cloudflare challenge block" in str(result.error_message)


def test_scan_service_end_to_end_flow_with_mocked_orchestrator(
    repo: ApplicationRepository,
    filter_config: FilterConfig,
) -> None:
    offer_good = JobOffer(
        portal=PortalName.GETONBRD,
        title="Desarrollador Full Stack Junior",
        company="Startup A",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/good-1",
        description="Buscamos React, Node.js y PostgreSQL.",
    )
    offer_hard_reject = JobOffer(
        portal=PortalName.GETONBRD,
        title="Senior Tech Lead .NET",
        company="Enterprise B",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/bad-1",
        description="C# y .NET",
    )

    mock_orch = MagicMock(spec=ScraperOrchestrator)
    from src.adapters.scrapers.orchestrator import PortalScanResult

    mock_orch.run_scan.return_value = {
        PortalName.GETONBRD: PortalScanResult(
            portal=PortalName.GETONBRD,
            offers=(offer_good, offer_hard_reject),
        )
    }

    service = ScanService(repository=repo, config=filter_config, orchestrator=mock_orch)
    summary = service.run_scan_pipeline(portals=[PortalName.GETONBRD])

    assert summary.total_scanned == 2
    assert summary.total_matched == 1
    assert summary.new_applications == 1
    assert summary.hard_rejected == 1

    # Verify saved in SQLite repository
    all_apps = repo.find_all()
    assert len(all_apps) == 1
    assert all_apps[0].title == "Desarrollador Full Stack Junior"
    assert all_apps[0].times_applied == 1
