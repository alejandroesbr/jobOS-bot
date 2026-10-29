from unittest.mock import MagicMock, patch

import pytest

from src.adapters.db.repository import ApplicationRepository
from src.adapters.notion.notion_client import NotionClient
from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    SubmissionAttempt,
    WorkModality,
)


@pytest.fixture
def sample_record() -> ApplicationRecord:
    return ApplicationRecord(
        id=1,
        dedup_key="techcorp::junior full stack",
        title="Junior Full Stack",
        company="TechCorp",
        location="Barranquilla",
        modality=WorkModality.REMOTE,
        description="React y Node",
        match_score=85,
        times_applied=1,
        status=ApplicationStatus.APPLIED,
        first_applied_at="2026-10-28T10:00:00Z",
        last_applied_at="2026-10-28T10:00:00Z",
        submissions=(
            SubmissionAttempt(
                attempt_number=1,
                portal=PortalName.LINKEDIN,
                canonical_url="https://linkedin.com/jobs/view/100",
                applied_at="2026-10-28T10:00:00Z",
            ),
        ),
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )


def test_notion_client_unconfigured() -> None:
    client = NotionClient(api_token="", database_id="")
    assert client.is_configured is False
    assert client.push_application(MagicMock()) is None
    assert client.update_application("page-123", MagicMock()) is False
    assert client.pull_status_updates() == []


def test_notion_client_push_success(sample_record: ApplicationRecord) -> None:
    client = NotionClient(api_token="mock-token", database_id="mock-db")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "page-notion-456"}

    with patch("httpx.Client.post", return_value=mock_response):
        page_id = client.push_application(sample_record)

    assert page_id == "page-notion-456"


def test_notion_client_pull_status_updates() -> None:
    client = NotionClient(api_token="mock-token", database_id="mock-db")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "page-1",
                "properties": {
                    "Estado": {"select": {"name": "Entrevista Programada"}}
                },
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response):
        updates = client.pull_status_updates()

    assert len(updates) == 1
    assert updates[0] == ("page-1", "Entrevista Programada")


def test_notion_client_bootstrap_to_repository() -> None:
    client = NotionClient(api_token="mock-token", database_id="mock-db")
    repo = ApplicationRepository(":memory:")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "page-remote-1",
                "properties": {
                    "Cargo": {"title": [{"text": {"content": "Frontend Developer"}}]},
                    "Empresa": {"rich_text": [{"text": {"content": "Acme Startup"}}]},
                    "Portal": {"select": {"name": "getonbrd"}},
                    "Estado": {"select": {"name": "Enviado"}},
                    "Modalidad": {"select": {"name": "remote"}},
                    "Match (%)": {"number": 80},
                    "Veces Postulado": {"number": 1},
                    "Link Oferta": {"url": "https://getonbrd.com/jobs/acme-1"},
                    "Último Envío": {"date": {"start": "2026-10-25"}},
                },
            }
        ]
    }

    with patch("httpx.Client.post", return_value=mock_response):
        restored = client.bootstrap_to_repository(repo)

    assert restored == 1
    all_apps = repo.find_all()
    assert len(all_apps) == 1
    assert all_apps[0].title == "Frontend Developer"
    assert all_apps[0].company == "Acme Startup"
    assert all_apps[0].notion_page_id == "page-remote-1"
