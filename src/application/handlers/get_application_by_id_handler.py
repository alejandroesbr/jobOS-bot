"""Get Application By ID Handler - Executes get application by ID query."""

import time
from src.application.queries import GetApplicationByIdQuery, GetApplicationByIdResult
from src.domain.models import ApplicationRecord
from src.ports.repository_port import ApplicationRepositoryPort


class GetApplicationByIdHandler:
    """Handles GetApplicationByIdQuery by fetching a single application from repository."""

    def __init__(self, repository: ApplicationRepositoryPort) -> None:
        self._repository = repository

    def handle(self, query: GetApplicationByIdQuery) -> GetApplicationByIdResult:
        """Execute the get application by ID query."""
        start_time = time.perf_counter()

        application = self._repository.find_by_id(query.application_id)

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return GetApplicationByIdResult(
            application=application,
            execution_time_ms=execution_time_ms,
        )