"""Get Application By ID Query - Read-only query for single application.

This module defines the Query and Result data classes for retrieving
a single application by its primary key in the CQS architecture.
"""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationRecord


@dataclass(frozen=True, slots=True)
class GetApplicationByIdQuery:
    """Query to retrieve a single application by ID.

    Immutable query object for fetching a specific application record
    by its database primary key.

    Attributes:
        application_id: The database primary key (auto-increment integer)
            of the application to retrieve

    Example:
        >>> query = GetApplicationByIdQuery(application_id=42)
    """
    application_id: int


@dataclass(frozen=True, slots=True)
class GetApplicationByIdResult:
    """Result of get application by ID query.

    Immutable result object containing the application record if found,
    or None if no application exists with the given ID.

    Attributes:
        application: ApplicationRecord if found, None otherwise

    Example:
        >>> result = GetApplicationByIdResult(application=app_record)
        >>> if result.application:
        ...     print(f"Found: {result.application.title}")
        ... else:
        ...     print("Application not found")
    """
    application: Optional[ApplicationRecord]