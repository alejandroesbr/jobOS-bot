"""Handler for SyncVaultCommand."""
from src.application.commands.sync_vault import SyncVaultCommand, SyncVaultResult
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.vault_port import KnowledgeVaultPort


class SyncVaultHandler:
    def __init__(
        self,
        repository: ApplicationRepositoryPort,
        vault_adapter: KnowledgeVaultPort,
    ) -> None:
        self.repository = repository
        self.vault_adapter = vault_adapter

    def handle(self, command: SyncVaultCommand) -> SyncVaultResult:
        applications = self.repository.find_all(limit=1000)

        if command.full_rebuild:
            created, updated = self.vault_adapter.rebuild_vault(
                command.vault_path, applications
            )
        else:
            created, updated = self.vault_adapter.sync_applications(
                applications, command.vault_path
            )

        return SyncVaultResult(
            created=created,
            updated=updated,
            total_applications=len(applications),
            vault_path=command.vault_path,
        )
