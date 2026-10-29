from pathlib import Path
from unittest.mock import patch

import pytest

from src.adapters.db.repository import ApplicationRepository
from src.adapters.mcp.server import (
    get_market_stack_radar,
    get_pipeline_overview,
    prepare_job_application_kit,
    search_applications,
    sync_pipeline_with_notion,
)
from src.domain.models import (
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    db_file = tmp_path / "mcp_test.db"
    repo = ApplicationRepository(str(db_file))

    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="React & Node Developer",
        company="InnoTech",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/inno-1",
        description="React, Node.js y PostgreSQL.",
    )
    evaluation = MatchEvaluation(
        dedup_key="innotech::react & node developer",
        canonical_url=offer.url,
        match_score=90,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Node.js", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repo.record_submission(offer, evaluation)
    repo.close()
    return str(db_file)


def test_mcp_get_pipeline_overview(db_path: str) -> None:
    with patch("src.adapters.mcp.server._get_repository", side_effect=lambda: ApplicationRepository(db_path)):
        result = get_pipeline_overview()

    assert "Resumen del Pipeline de Postulaciones" in result
    assert "Total Vacantes Maestras" in result
    assert "Enviado" in result


def test_mcp_search_applications(db_path: str) -> None:
    with patch("src.adapters.mcp.server._get_repository", side_effect=lambda: ApplicationRepository(db_path)):
        result_found = search_applications(query="React")
        result_empty = search_applications(query="NonExistentCompany")

    assert "Vacantes Encontradas" in result_found
    assert "InnoTech" in result_found
    assert "No se encontraron vacantes" in result_empty


def test_mcp_get_market_stack_radar(db_path: str) -> None:
    with patch("src.adapters.mcp.server._get_repository", side_effect=lambda: ApplicationRepository(db_path)):
        result = get_market_stack_radar()

    assert "Radar de Tecnologías del Mercado" in result
    assert "React" in result
    assert "Node.js" in result


def test_mcp_prepare_job_application_kit(db_path: str) -> None:
    with patch("src.adapters.mcp.server._get_repository", side_effect=lambda: ApplicationRepository(db_path)):
        result = prepare_job_application_kit(application_id=1)

    assert "Kit de Postulación" in result
    assert "InnoTech" in result
    assert "CV Tailor" in result


def test_mcp_sync_pipeline_with_notion(db_path: str) -> None:
    with patch("src.adapters.mcp.server._get_repository", side_effect=lambda: ApplicationRepository(db_path)):
        result = sync_pipeline_with_notion()

    assert "Informe de Sincronización con Notion" in result
