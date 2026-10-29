from dataclasses import dataclass, field
import logging

from src.adapters.db.repository import ApplicationRepository
from src.adapters.scrapers.orchestrator import ScraperOrchestrator
from src.config_loader import FilterConfig, load_filter_config
from src.domain.matcher import OfferMatcher
from src.domain.models import ApplicationRecord, JobOffer, MatchEvaluation, PortalName

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvaluatedOfferItem:
    offer: JobOffer
    evaluation: MatchEvaluation
    is_new: bool
    is_reapplication: bool
    is_recorded: bool
    record: ApplicationRecord | None = None


@dataclass(frozen=True, slots=True)
class ScanSummary:
    total_scanned: int
    total_matched: int
    new_applications: int
    reapplications: int
    skipped_cooldown: int
    hard_rejected: int
    offers_by_portal: dict[str, int]
    errors_by_portal: dict[str, str]
    processed_items: tuple[EvaluatedOfferItem, ...] = ()


class ScanService:
    def __init__(
        self,
        repository: ApplicationRepository,
        config: FilterConfig | None = None,
        orchestrator: ScraperOrchestrator | None = None,
        matcher: OfferMatcher | None = None,
    ) -> None:
        self.repository = repository
        self.config = config if config is not None else load_filter_config()
        self.orchestrator = orchestrator if orchestrator is not None else ScraperOrchestrator()
        self.matcher = matcher if matcher is not None else OfferMatcher(self.config)

    def run_scan_pipeline(
        self,
        portals: list[PortalName],
        limit_per_portal: int = 15,
        headless: bool = True,
    ) -> ScanSummary:
        scan_results = self.orchestrator.run_scan(
            portals=portals,
            config=self.config,
            headless=headless,
            limit_per_portal=limit_per_portal,
        )

        total_scanned = 0
        total_matched = 0
        new_applications = 0
        reapplications = 0
        skipped_cooldown = 0
        hard_rejected = 0
        offers_by_portal: dict[str, int] = {}
        errors_by_portal: dict[str, str] = {}
        processed_items: list[EvaluatedOfferItem] = []

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
                    processed_items.append(
                        EvaluatedOfferItem(
                            offer=offer,
                            evaluation=evaluation,
                            is_new=False,
                            is_reapplication=False,
                            is_recorded=False,
                            record=None,
                        )
                    )
                    continue

                if not evaluation.should_apply:
                    processed_items.append(
                        EvaluatedOfferItem(
                            offer=offer,
                            evaluation=evaluation,
                            is_new=False,
                            is_reapplication=False,
                            is_recorded=False,
                            record=None,
                        )
                    )
                    continue

                total_matched += 1
                record, applied = self.repository.record_submission(
                    offer=offer,
                    evaluation=evaluation,
                    cooldown_days=self.config.matching.reapply_cooldown_days,
                )

                if applied:
                    is_first_time = record.times_applied == 1
                    if is_first_time:
                        new_applications += 1
                    else:
                        reapplications += 1

                    processed_items.append(
                        EvaluatedOfferItem(
                            offer=offer,
                            evaluation=evaluation,
                            is_new=is_first_time,
                            is_reapplication=not is_first_time,
                            is_recorded=True,
                            record=record,
                        )
                    )
                else:
                    skipped_cooldown += 1
                    processed_items.append(
                        EvaluatedOfferItem(
                            offer=offer,
                            evaluation=evaluation,
                            is_new=False,
                            is_reapplication=False,
                            is_recorded=False,
                            record=record,
                        )
                    )

        return ScanSummary(
            total_scanned=total_scanned,
            total_matched=total_matched,
            new_applications=new_applications,
            reapplications=reapplications,
            skipped_cooldown=skipped_cooldown,
            hard_rejected=hard_rejected,
            offers_by_portal=offers_by_portal,
            errors_by_portal=errors_by_portal,
            processed_items=tuple(processed_items),
        )
