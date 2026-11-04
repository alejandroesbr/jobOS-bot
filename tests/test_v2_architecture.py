from pathlib import Path
from unittest.mock import MagicMock

from src.adapters.db.repository import ApplicationRepository
from src.adapters.obsidian.adapter import ObsidianVaultAdapter
from src.adapters.obsidian.frontmatter import build_frontmatter, format_yaml_frontmatter
from src.application.commands import ScanPortalsCommand, SyncVaultCommand
from src.application.handlers import (
    GetApplicationByIdHandler,
    GetApplicationsHandler,
    ScanPortalsHandler,
    SyncVaultHandler,
)
from src.application.queries import GetApplicationByIdQuery, GetApplicationsQuery
from src.config_loader import load_filter_config
from src.domain.bayesian_scorer import BayesianConfig, BayesianScorer, IDFCache
from src.domain.graph_analyzer import GraphAnalyzer
from src.domain.models import (
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.domain.tech_tokenizer import TechTokenizer, TechVocabulary
from src.ports.scraper_port import PortalScanResult


# ============================================================================
# 1. TechTokenizer Tests (O(n) + punctuation + aliases + multi-word)
# ============================================================================


def test_tech_tokenizer_single_pass_aliases_and_punctuation() -> None:
    vocab = TechVocabulary(
        core=("react", "nodejs", "typescript", "javascript", "postgresql", "csharp", "cpp", "dotnet"),
        secondary=("docker", "aws", "restapi"),
        bonus=("git", "linux"),
        multi_word=("rest api", "amazon web services"),
    )
    tokenizer = TechTokenizer(vocab)

    text = (
        "Buscamos desarrollador con JS, TS, Node.js, C#, C++ y .NET. "
        "También experiencia en REST API y Amazon Web Services con Docker."
    )
    unique_techs = tokenizer.get_unique_technologies(text)

    assert "javascript" in unique_techs
    assert "typescript" in unique_techs
    assert "nodejs" in unique_techs
    assert "csharp" in unique_techs
    assert "cpp" in unique_techs
    assert "dotnet" in unique_techs
    assert "restapi" in unique_techs
    assert "aws" in unique_techs
    assert "docker" in unique_techs

    categorized = tokenizer.extract_technologies(text)
    core_norms = {m.normalized for m in categorized["core"]}
    assert "nodejs" in core_norms
    assert "csharp" in core_norms


# ============================================================================
# 2. BayesianScorer & IDFCache Tests
# ============================================================================


def test_bayesian_scorer_and_idf_cache_with_repository(tmp_path: Path) -> None:
    db_file = tmp_path / "bayesian_test.db"
    repo = ApplicationRepository(str(db_file))

    offer1 = JobOffer(
        portal=PortalName.LINKEDIN,
        title="Backend Dev 1",
        company="Company A",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://linkedin.com/jobs/1",
        description="React y PostgreSQL",
    )
    eval1 = MatchEvaluation(
        dedup_key="company a::backend dev 1",
        canonical_url=offer1.url,
        match_score=85,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="PostgreSQL", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repo.record_submission(offer1, eval1)

    offer2 = JobOffer(
        portal=PortalName.GETONBRD,
        title="Frontend Dev 2",
        company="Company B",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/2",
        description="React",
    )
    eval2 = MatchEvaluation(
        dedup_key="company b::frontend dev 2",
        canonical_url=offer2.url,
        match_score=80,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
        ),
    )
    repo.record_submission(offer2, eval2)

    idf_cache = IDFCache(repo)
    react_idf = idf_cache.get_idf("React")
    pg_idf = idf_cache.get_idf("PostgreSQL")
    unknown_idf = idf_cache.get_idf("Elixir")

    assert react_idf >= 0.0
    assert pg_idf >= react_idf
    assert unknown_idf == 1.0

    scorer = BayesianScorer(config=BayesianConfig(), idf_cache=idf_cache)
    keywords = (
        KeywordMatch(keyword="React", is_matched=True, weight=KeywordWeight.CORE),
        KeywordMatch(keyword="PostgreSQL", is_matched=True, weight=KeywordWeight.CORE),
        KeywordMatch(keyword="Docker", is_matched=False, weight=KeywordWeight.SECONDARY),
    )
    res = scorer.score_keywords(keywords, candidate_skills={"React", "PostgreSQL"})

    assert 50 <= res.score <= 100
    assert 0.0 <= res.confidence_lower <= res.posterior_mean <= res.confidence_upper <= 1.0
    assert len(res.keyword_contributions) == 3

    repo.close()


# ============================================================================
# 3. GraphAnalyzer Tests (Co-occurrence, Communities, Association Rules, Matrix)
# ============================================================================


def test_graph_analyzer_cooccurrence_communities_rules_and_matrix() -> None:
    applications_skills = [
        ["Python", "FastAPI", "PostgreSQL", "Docker"],
        ["Python", "FastAPI", "PostgreSQL", "Docker"],
        ["Python", "FastAPI", "PostgreSQL"],
        ["React", "TypeScript", "Node.js", "PostgreSQL"],
        ["React", "TypeScript", "Node.js"],
        ["React", "TypeScript", "Node.js"],
    ]

    analyzer = GraphAnalyzer()
    analyzer.build_from_applications(applications_skills)

    assert analyzer.application_count == 6
    assert analyzer.skill_count == 7

    metrics = analyzer.get_skill_metrics({"Python": 0.8, "Docker": 0.2})
    assert len(metrics) == 7
    # PostgreSQL has demand 4 and mastery 0.0 -> priority 4.0
    assert metrics[0].name == "PostgreSQL"
    assert metrics[0].priority_score == 4.0

    rules = analyzer.get_association_rules()
    assert len(rules) > 0
    assert any(
        "FastAPI" in r.antecedent and "Python" in r.consequent
        for r in rules
    )

    matrix = analyzer.get_learning_priority_matrix(top_k=5)
    assert len(matrix) == 5
    assert "skill" in matrix[0]
    assert "priority" in matrix[0]
    assert "community" in matrix[0]


# ============================================================================
# 4. ObsidianVaultAdapter Tests (YAML frontmatter quotes, hubs, slugs)
# ============================================================================


def test_obsidian_vault_adapter_frontmatter_quotes_hubs_and_slugs(tmp_path: Path) -> None:
    db_file = tmp_path / "obsidian_test.db"
    repo = ApplicationRepository(str(db_file))

    offer = JobOffer(
        portal=PortalName.LINKEDIN,
        title="Backend Developer Python",
        company="Togrow Agencia",
        location="Remoto",
        modality=WorkModality.REMOTE,
        url="https://linkedin.com/jobs/view/555",
        description="Buscamos Backend con Python, FastAPI y Docker.",
    )
    evaluation = MatchEvaluation(
        dedup_key="togrow agencia::backend developer python",
        canonical_url=offer.url,
        match_score=92,
        should_apply=True,
        is_hard_rejected=False,
        rejection_reason=None,
        keywords=(
            KeywordMatch(keyword="Python", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="FastAPI", is_matched=True, weight=KeywordWeight.CORE),
            KeywordMatch(keyword="Docker", is_matched=False, weight=KeywordWeight.SECONDARY),
        ),
    )
    record, _ = repo.record_submission(offer, evaluation)

    # Check YAML frontmatter quotes around wikilinks
    fm = build_frontmatter(record, ["Python", "FastAPI"])
    yaml_text = format_yaml_frontmatter(fm)
    assert 'company_link: "[[Togrow Agencia]]"' in yaml_text
    assert 'portal_link: "[[LinkedIn]]"' in yaml_text
    assert '"[[Python]]"' in yaml_text
    assert '"[[FastAPI]]"' in yaml_text

    # Sync to Obsidian vault
    vault_dir = tmp_path / "vault"
    adapter = ObsidianVaultAdapter(str(vault_dir))
    created, updated = adapter.sync_applications([record])

    assert created == 1
    assert updated == 0

    # Verify directories & hubs
    assert (vault_dir / "applications").is_dir()
    assert (vault_dir / "companies" / "index.md").is_file()
    assert (vault_dir / "skills" / "index.md").is_file()
    assert (vault_dir / "portals" / "index.md").is_file()
    assert (vault_dir / "status" / "index.md").is_file()

    # Check note file and slug consistency with company hub
    app_notes = list((vault_dir / "applications").glob("*.md"))
    assert len(app_notes) == 1
    note_stem = app_notes[0].stem

    company_hub = vault_dir / "companies" / "Togrow Agencia.md"
    assert company_hub.is_file()
    company_hub_content = company_hub.read_text(encoding="utf-8")
    assert f"[[{note_stem}]]" in company_hub_content

    repo.close()


# ============================================================================
# 5. CQS Handlers Tests (ScanPortals, SyncVault, GetApplications, GetApplicationById)
# ============================================================================


def test_cqs_handlers_end_to_end(tmp_path: Path) -> None:
    db_file = tmp_path / "cqs_test.db"
    vault_dir = tmp_path / "cqs_vault"
    repo = ApplicationRepository(str(db_file))
    vault = ObsidianVaultAdapter(str(vault_dir))
    config = load_filter_config(Path("tests/fixtures/test_filters.yaml"))

    sample_offer = JobOffer(
        portal=PortalName.GETONBRD,
        title="Desarrollador Full Stack Junior",
        company="Globant Colombia",
        location="Remoto / Barranquilla",
        modality=WorkModality.REMOTE,
        url="https://getonbrd.com/jobs/globant-1",
        description="Stack principal: React, NestJS, TypeScript, PostgreSQL y Docker.",
    )

    mock_scraper = MagicMock()
    scan_ret = {
        PortalName.GETONBRD: PortalScanResult(
            portal=PortalName.GETONBRD,
            offers=(sample_offer,),
            error_message=None,
        )
    }
    mock_scraper.run_scan.return_value = scan_ret
    mock_scraper.scan_all.return_value = scan_ret

    # 1. ScanPortalsHandler
    scan_handler = ScanPortalsHandler(repository=repo, scraper=mock_scraper, vault=vault)
    scan_cmd = ScanPortalsCommand(
        portals=[PortalName.GETONBRD],
        limit_per_portal=5,
        headless=True,
        max_workers=2,
        sync_obsidian=True,
        vault_path=str(vault_dir),
        config=config,
    )
    scan_res = scan_handler.handle(scan_cmd)

    assert scan_res.total_scanned == 1
    assert scan_res.total_matched == 1
    assert scan_res.new_applications == 1
    assert scan_res.obsidian_synced is True
    assert scan_res.obsidian_created == 1

    # 2. GetApplicationsHandler
    get_apps_handler = GetApplicationsHandler(repository=repo)
    get_apps_res = get_apps_handler.handle(
        GetApplicationsQuery(
            status=ApplicationStatus.APPLIED.value,
            min_match_score=70,
            keyword="React",
        )
    )
    assert get_apps_res.total_count == 1
    assert get_apps_res.applications[0].company == "Globant Colombia"

    # 3. GetApplicationByIdHandler
    app_id = get_apps_res.applications[0].id
    get_by_id_handler = GetApplicationByIdHandler(repository=repo)
    get_by_id_res = get_by_id_handler.handle(GetApplicationByIdQuery(application_id=app_id))
    assert get_by_id_res.application is not None
    assert get_by_id_res.application.id == app_id

    # 4. SyncVaultHandler (full rebuild)
    sync_handler = SyncVaultHandler(vault=vault)
    sync_res = sync_handler.handle(
        SyncVaultCommand(
            applications=get_apps_res.applications,
            vault_path=str(vault_dir),
            full_rebuild=True,
        )
    )
    assert sync_res.created == 1
    assert sync_res.updated == 0
    assert sync_res.hubs_updated > 0

    repo.close()
