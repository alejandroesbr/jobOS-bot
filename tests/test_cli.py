import json
from pathlib import Path

from click.testing import CliRunner
import pytest

from cli import cli
from src.adapters.db.repository import ApplicationRepository
from src.domain.models import (
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)


@pytest.fixture
def populated_db_path(tmp_path: Path) -> str:
    db_file = tmp_path / "test_jobs.db"
    repo = ApplicationRepository(str(db_file))

    offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Desarrollador React Junior",
        company="TechCorp Latam",
        location="Barranquilla",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/dev-1",
        description="React, Node.js y PostgreSQL.",
    )
    evaluation = MatchEvaluation(
        dedup_key="techcorp latam::desarrollador react junior",
        canonical_url=offer.url,
        match_score=85,
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


def test_cli_stats_command(populated_db_path: str) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["stats", "--db-path", populated_db_path])

    assert result.exit_code == 0
    assert "jobOS-bot — Estadísticas y Radar de Mercado" in result.output
    assert "Enviado" in result.output
    assert "React" in result.output


def test_cli_export_json_command(populated_db_path: str, tmp_path: Path) -> None:
    runner = CliRunner()
    out_file = tmp_path / "exported.json"
    result = runner.invoke(
        cli,
        ["export", "--format", "json", "--output", str(out_file), "--db-path", populated_db_path],
    )

    assert result.exit_code == 0
    assert out_file.is_file()

    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(content) == 1
    assert content[0]["title"] == "Desarrollador React Junior"
    assert content[0]["company"] == "TechCorp Latam"
    assert content[0]["times_applied"] == 1


def test_cli_export_csv_command(populated_db_path: str, tmp_path: Path) -> None:
    runner = CliRunner()
    out_file = tmp_path / "exported.csv"
    result = runner.invoke(
        cli,
        ["export", "--format", "csv", "--output", str(out_file), "--db-path", populated_db_path],
    )

    assert result.exit_code == 0
    assert out_file.is_file()

    content = out_file.read_text(encoding="utf-8")
    assert "Desarrollador React Junior" in content
    assert "TechCorp Latam" in content


def test_cli_scan_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--portal" in result.output
    assert "--limit" in result.output
    assert "--headless" in result.output
