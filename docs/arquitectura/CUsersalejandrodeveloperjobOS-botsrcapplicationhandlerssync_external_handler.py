"""Handler for SyncExternalCommand (Notion sync)."""
from src.application.commands.sync_external import SyncExternalCommand, SyncExternalResult
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.external_sync_port import ExternalSyncPort


class SyncExternalHandler:
    def __init__(
        self,
        repository: ApplicationRepositoryPort,
        external_sync: ExternalSyncPort,
    ) -> None:
        self.repository = repository
        self.external_sync = external_sync

    def handle(self, command: SyncExternalCommand) -> SyncExternalResult:
        if not self.external_sync.is_configured:
            return SyncExternalResult(
                pushed_new=0,
                updated_existing=0,
                pulled_statuses=0,
                interview_preps_triggered=0,
                bootstrapped_from_notion=0,
                stalled_followups=0,
            )

        report = self.external_sync.sync()
        return SyncExternalResult(
            pushed_new=report.pushed_new,
            updated_existing=report.updated_existing,
            pulled_statuses=report.pulled_statuses,
            interview_preps_triggered=report.interview_preps_triggered,
            bootstrapped_from_notion=report.bootstrapped_from_notion,
            stalled_followups=report.stalled_followups,
        )
