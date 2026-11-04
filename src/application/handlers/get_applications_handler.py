"""Get Applications Handler - Executes get applications query.

This module contains the GetApplicationsHandler which executes the
GetApplicationsQuery by fetching filtered, paginated application listings
from the repository in the CQS architecture.

The handler performs:
1. Status string to enum conversion (for CLI compatibility)
2. Repository query with status filter
3. In-memory filtering by minimum match score and keyword
4. Pagination (offset/limit)
5. Execution time measurement
"""
import time
from src.application.queries import GetApplicationsQuery, GetApplicationsResult
from src.domain.models import ApplicationRecord, ApplicationStatus
from src.ports.repository_port import ApplicationRepositoryPort


class GetApplicationsHandler:
    """Handles GetApplicationsQuery by fetching filtered applications from repository.

    This handler executes read-only queries for application listings with
    support for filtering, search, and pagination. It's designed for
    CLI display, dashboard rendering, and API responses.

    The handler uses string-based status filtering (for CLI compatibility)
    and performs additional in-memory filtering for match score and keyword
    search since the repository's find_all has limited filter capabilities.

    Attributes:
        _repository: ApplicationRepositoryPort implementation for data access

    Example:
        >>> handler = GetApplicationsHandler(repository=sqlite_repo)
        >>> query = GetApplicationsQuery(
        ...     status="Sent",
        ...     min_match_score=70,
        ...     keyword="react",
        ...     limit=20,
        ...     offset=0
        ... )
        >>> result = handler.handle(query)
        >>> for app in result.applications:
        ...     print(f"{app.title} @ {app.company} ({app.match_score}%)")
    """

    def __init__(self, repository: ApplicationRepositoryPort) -> None:
        """Initialize the handler with repository dependency.

        Args:
            repository: ApplicationRepositoryPort implementation for data access

        Example:
            >>> handler = GetApplicationsHandler(SQLiteApplicationRepository("data/jobs.db"))
        """
        self._repository = repository

    def handle(self, query: GetApplicationsQuery) -> GetApplicationsResult:
        """Execute the get applications query.

        Performs the complete query workflow:
        1. Convert status string to ApplicationStatus enum (if provided)
        2. Fetch applications from repository with status filter
        3. Apply in-memory filters (min_match_score, keyword)
        4. Apply pagination (offset/limit)
        5. Measure and return execution time

        Args:
            query: GetApplicationsQuery with filters and pagination parameters

        Returns:
            GetApplicationsResult containing:
                - applications: Paginated list of ApplicationRecord objects
                - total_count: Total matching applications (before pagination)
                - execution_time_ms: Query execution time in milliseconds

        Example:
            >>> query = GetApplicationsQuery(
            ...     status="Sent",
            ...     min_match_score=70,
            ...     keyword="python",
            ...     limit=10,
            ...     offset=0
            ... )
            >>> result = handler.handle(query)
            >>> print(f"Showing {len(result.applications)} of {result.total_count} total")
            >>> print(f"Query took {result.execution_time_ms}ms")
        """
        start_time = time.perf_counter()

        # Convert status string to enum if provided
        status = None
        if query.status:
            try:
                status = ApplicationStatus(query.status)
            except ValueError:
                status = None

        # Fetch applications with generous limit for filtering and pagination
        fetch_limit = max(query.limit + query.offset, 500)
        applications = self._repository.find_all(
            status=status,
            min_match=query.min_match_score,
            keyword=query.keyword,
            limit=fetch_limit,
        )

        # Apply additional in-memory filters
        if query.min_match_score is not None:
            applications = [a for a in applications if a.match_score >= query.min_match_score]

        if query.keyword:
            kw_lower = query.keyword.lower()
            applications = [
                a for a in applications
                if kw_lower in a.title.lower()
                or kw_lower in a.company.lower()
                or kw_lower in a.description.lower()
                or any(kw_lower in k.keyword.lower() for k in a.keywords)
            ]

        # Apply pagination
        total_count = len(applications)
        paginated = applications[query.offset : query.offset + query.limit]

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        return GetApplicationsResult(
            applications=paginated,
            total_count=total_count,
            execution_time_ms=execution_time_ms,
            limit=query.limit,
            offset=query.offset,
        )