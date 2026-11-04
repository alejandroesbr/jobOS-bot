"""CQS Queries - Read-only operations for the application layer.

This package contains all query classes for the Command Query Separation (CQS)
architecture. Queries represent intent to read system state without modifying it
and are handled by corresponding Query Handlers.

Queries:
- GetApplicationsQuery / GetApplicationsResult: Retrieve paginated, filtered application listings
- GetApplicationByIdQuery / GetApplicationByIdResult: Retrieve a single application by primary key

Each query is an immutable dataclass (frozen=True, slots=True) containing
all parameters needed for the read operation. Results are also immutable dataclasses
capturing the retrieved data with metadata (total count, execution time).

Example usage:
    >>> from src.application.queries import GetApplicationsQuery
    >>> from src.domain.models import ApplicationStatus
    >>>
    >>> query = GetApplicationsQuery(
    ...     status="Sent",
    ...     min_match_score=70,
    ...     keyword="react",
    ...     limit=20,
    ...     offset=0
    ... )
    >>> result = handler.handle(query)
"""
from src.application.queries.get_applications import GetApplicationsQuery, GetApplicationsResult
from src.application.queries.get_application_by_id import GetApplicationByIdQuery, GetApplicationByIdResult

__all__ = [
    "GetApplicationsQuery",
    "GetApplicationsResult",
    "GetApplicationByIdQuery",
    "GetApplicationByIdResult",
]