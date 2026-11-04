"""Handler for GetApplicationByIdQuery."""
from src.application.queries.get_application_by_id import GetApplicationByIdQuery, GetApplicationByIdResult
from src.ports.repository_port import ApplicationRepositoryPort
from src.domain.models import ApplicationRecord


class GetApplicationByIdHandler:
    def __init__(self, repository: ApplicationRepositoryPort) -> None:
        self.repository = repository

    def handle(self, query: GetApplicationByIdQuery) -> GetApplicationByIdResult:
        application = self.repository.find_by_id(query.application_id)
        return GetApplicationByIdResult(application=application)
