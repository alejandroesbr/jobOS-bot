import asyncio
import inspect
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.db.repository import ApplicationRepository
from src.adapters.mcp.server import (
    query_job_applications,
    run_portal_scan_and_sync,
    sync_obsidian_vault,
)
from src.domain.models import (
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.ports.scraper_port import PortalScanResult


def _invoke_tool(func: Any, *args: Any, **kwargs: Any) -> str:
    result = func(*args, **kwargs)
    if inspect.iscoroutine(result):
        return str(asyncio.run(result))
    return str(result)


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


def test_mcp_query_job_applications(db_path: str) -> None:
    with patch(
        "src.adapters.mcp.server._get_repository",
        side_effect=lambda: ApplicationRepository(db_path),
    ):
        raw_found = _invoke_tool(query_job_applications, min_match=80, keyword="React")
        raw_empty = _invoke_tool(query_job_applications, keyword="NonExistentCompany")

    assert "InnoTech" in raw_found
    assert "React & Node Developer" in raw_found

    if raw_empty.strip().startswith("{"):
        parsed_empty = json.loads(raw_empty)
        apps = parsed_empty.get("result", parsed_empty).get("applications", [])
        assert len(apps) == 0
    else:
        assert "0" in raw_empty or "No se encontraron" in raw_empty


def test_mcp_sync_obsidian_vault(db_path: str, tmp_path: Path) -> None:
    vault_dir = tmp_path / "mcp_vault"
    with patch(
        "src.adapters.mcp.server._get_repository",
        side_effect=lambda: ApplicationRepository(db_path),
    ):
        raw_res = _invoke_tool(sync_obsidian_vault, vault_path=str(vault_dir))

    assert (vault_dir / "applications").is_dir()
    assert len(list((vault_dir / "applications").glob("*.md"))) == 1
    assert "true" in raw_res.lower() or "created" in raw_res.lower() or "sincroniz" in raw_res.lower()


def test_mcp_run_portal_scan_and_sync(db_path: str, tmp_path: Path) -> None:
    vault_dir = tmp_path / "scan_vault"
    sample_offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Junior Full Stack Developer",
        company="Togrow Agencia",
        location="Remoto, Colombia",
        modality=WorkModality.REMOTE,
        url="https://www.getonbrd.com/jobs/togrow-1",
        description="Buscamos desarrollador con React, Node.js, TypeScript, PostgreSQL y Docker.",
    )
    mock_orchestrator = MagicMock()
    scan_ret = {
        PortalName.GETONBRD: PortalScanResult(
            portal=PortalName.GETONBRD,
            offers=(sample_offer,),
            error_message=None,
        )
    }
    mock_orchestrator.run_scan.return_value = scan_ret
    mock_orchestrator.scan_all.return_value = scan_ret

    with (
        patch(
            "src.adapters.mcp.server._get_repository",
            side_effect=lambda: ApplicationRepository(db_path),
        ),
        patch(
            "src.adapters.mcp.server._get_scraper_orchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        raw_res = _invoke_tool(
            run_portal_scan_and_sync,
            portals=["getonbrd"],
            limit_per_portal=5,
            workers=2,
            sync_obsidian=True,
            vault_path=str(vault_dir),
        )

    assert "true" in raw_res.lower() or "total_scanned" in raw_res.lower()
    assert (vault_dir / "applications").is_dir()
    assert len(list((vault_dir / "applications").glob("*.md"))) >= 2
