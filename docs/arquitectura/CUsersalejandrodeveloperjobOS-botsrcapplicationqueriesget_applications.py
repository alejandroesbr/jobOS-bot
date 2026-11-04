"""Get Applications Query - Read-only query for application listings."""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationStatus, ApplicationRecord


@dataclass(frozen=True, slots=True)
class GetApplicationsQuery:
    """Query to retrieve applications with filters."""
    status: Optional[ApplicationStatus] = None
    min_match: Optional[int] = None
    keyword: Optional[str] = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetApplicationsResult:
    """Result of get applications query."""
    applications: list[ApplicationRecord]
    total_count: int
    limit: int
    offset: int
