"""Handler for GetApplicationsQuery."""
from src.application.queries.get_applications import GetApplicationsQuery, GetApplicationsResult
from src.ports.repository_port import ApplicationRepositoryPort
from src.domain.models import ApplicationRecord, ApplicationStatus


class GetApplicationsHandler:
    def __init__(self, repository: ApplicationRepositoryPort) -> None:
        self.repository = repository

    def handle(self, query: GetApplicationsQuery) -> GetApplicationsResult:
        all_records = self.repository.find_all(
            status=query.status,
            limit=query.limit + query.offset,
        )

        filtered = []
        for record in all_records:
            if query.min_match and record.match_score < query.min_match:
                continue
            if query.keyword:
                kw_lower = query.keyword.lower()
                if not (
                    kw_lower in record.title.lower()
                    or kw_lower in record.company.lower()
                    or kw_lower in record.description.lower()
                    or any(kw_lower in kw.keyword.lower() for kw in record.keywords)
                ):
                    continue
            filtered.append(record)

        start = query.offset
        end = query.offset + query.limit
        paginated = filtered[start:end]

        return GetApplicationsResult(
            applications=paginated,
            total_count=len(filtered),
            limit=query.limit,
            offset=query.offset,
        )
