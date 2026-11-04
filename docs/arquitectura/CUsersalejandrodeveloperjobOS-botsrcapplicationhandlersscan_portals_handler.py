"""Handler for ScanPortalsCommand."""
import time
import logging
from src.application.commands.scan_portals import ScanPortalsCommand, ScanPortalsResult
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.vault_port import KnowledgeVaultPort
from src.adapters.scrapers.orchestrator import MultiWorkerScraperOrchestrator
from src.domain.matcher import OfferMatcher
from src.domain.models import JobOffer, MatchEvaluation
from src.config_loader import FilterConfig, load_filter_config

logger = logging.getLogger(__name__)


class ScanPortalsHandler:
    def __init__(
        self,
        repository: ApplicationRepositoryPort,
        scraper_orchestrator: MultiWorkerScraperOrchestrator,
        matcher: OfferMatcher,
        vault_adapter: KnowledgeVaultPort | None = None,
    ) -> None:
        self.repository = repository
        self.scraper_orchestrator = scraper_orchestrator
        self.matcher = matcher
        self.vault_adapter = vault_adapter

    def handle(self, command: ScanPortalsCommand) -> ScanPortalsResult:
        start_time = time.perf_counter()
        config = command.config or load_filter_config()

        scan_results = self.scraper_orchestrator.run_scan(
            portals=command.portals,
            config=config,
            headless=command.headless,
            limit_per_portal=command.limit_per_portal,
        )

        total_scanned = 0
        total_matched = 0
        new_applications = 0
        reapplications = 0
        skipped_cooldown = 0
        hard_rejected = 0
        offers_by_portal: dict[str, int] = {}
        errors_by_portal: dict[str, str] = {}

        for portal_name, portal_result in scan_results.items():
            offers_count = len(portal_result.offers)
            offers_by_portal[portal_name.value] = offers_count
            total_scanned += offers_count

            if portal_result.error_message:
                errors_by_portal[portal_name.value] = portal_result.error_message

            for offer in portal_result.offers:
                evaluation = self.matcher.evaluate(offer)

                if evaluation.is_hard_rejected:
                    hard_rejected += 1
                    continue

                if not evaluation.should_apply:
                    continue

                total_matched += 1
                record, applied = self.repository.record_submission(
                    offer=offer,
                    evaluation=evaluation,
                    cooldown_days=config.matching.reapply_cooldown_days,
                )

                if applied:
                    if record.times_applied == 1:
                        new_applications += 1
                    else:
                        reapplications += 1
                else:
                    skipped_cooldown += 1

        obsidian_synced = False
        obsidian_created = 0
        obsidian_updated = 0

        if command.sync_obsidian and self.vault_adapter:
            all_apps = self.repository.find_all(limit=1000)
            obsidian_created, obsidian_updated = self.vault_adapter.sync_applications(
                all_apps, command.vault_path
            )
            obsidian_synced = True

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return ScanPortalsResult(
            total_scanned=total_scanned,
            total_matched=total_matched,
            new_applications=new_applications,
            reapplications=reapplications,
            skipped_cooldown=skipped_cooldown,
            hard_rejected=hard_rejected,
            offers_by_portal=offers_by_portal,
            errors_by_portal=errors_by_portal,
            obsidian_synced=obsidian_synced,
            obsidian_created=obsidian_created,
            obsidian_updated=obsidian_updated,
            execution_time_ms=execution_time_ms,
        )
