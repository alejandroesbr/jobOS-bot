"""CQS Queries - Read-only operations."""
from src.application.queries.get_applications import GetApplicationsQuery, GetApplicationsResult
from src.application.queries.get_application_by_id import GetApplicationByIdQuery, GetApplicationByIdResult

__all__ = [
    "GetApplicationsQuery",
    "GetApplicationsResult",
    "GetApplicationByIdQuery",
    "GetApplicationByIdResult",
]
