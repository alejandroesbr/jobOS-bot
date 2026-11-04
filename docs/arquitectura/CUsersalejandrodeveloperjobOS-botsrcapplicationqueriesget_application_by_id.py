"""Get Application By ID Query - Read-only query for single application."""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationRecord


@dataclass(frozen=True, slots=True)
class GetApplicationByIdQuery:
    """Query to retrieve a single application by ID."""
    application_id: int


@dataclass(frozen=True, slots=True)
class GetApplicationByIdResult:
    """Result of get application by ID query."""
    application: Optional[ApplicationRecord]
