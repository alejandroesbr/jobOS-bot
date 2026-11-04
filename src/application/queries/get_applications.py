"""Get Applications Query - Read-only query for application listings.

This module defines the Query and Result data classes for retrieving
paginated, filtered application listings in the CQS architecture.

The GetApplicationsQuery supports filtering by status, minimum match score,
and keyword search, with pagination support for large datasets.
"""
from dataclasses import dataclass
from typing import Optional
from src.domain.models import ApplicationStatus, ApplicationRecord


@dataclass(frozen=True, slots=True)
class GetApplicationsQuery:
    """Query to retrieve applications with filters.

    Immutable query object for retrieving a paginated, filtered list of
    job applications from the repository.

    Attributes:
        status: Optional filter by application status as string (e.g., "Sent", "Interview Scheduled").
            Uses string for CLI compatibility rather than enum.
        min_match_score: Optional minimum match score percentage (0-100)
        keyword: Optional search term for title, company, description, or keywords
        limit: Maximum number of results to return (default: 50)
        offset: Number of results to skip for pagination (default: 0)

    Example:
        >>> # Get first page of sent applications with match >= 70%
        >>> query = GetApplicationsQuery(
        ...     status="Sent",
        ...     min_match_score=70,
        ...     limit=20,
        ...     offset=0
        ... )
        >>>
        >>> # Search for React-related applications
        >>> query = GetApplicationsQuery(keyword="react", limit=10)
        >>>
        >>> # Get second page of results
        >>> query = GetApplicationsQuery(limit=20, offset=20)
    """
    status: Optional[str] = None  # String for CLI compatibility
    min_match_score: Optional[int] = None
    keyword: Optional[str] = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class GetApplicationsResult:
    """Result of get applications query.

    Immutable result object containing the paginated application list
    and metadata for pagination controls and performance monitoring.

    Attributes:
        applications: List of ApplicationRecord objects for the current page
        total_count: Total number of applications matching filters (all pages)
        execution_time_ms: Query execution time in milliseconds

    Example:
        >>> result = GetApplicationsResult(
        ...     applications=[app1, app2, ...],
        ...     total_count=150,
        ...     execution_time_ms=45
        ... )
        >>> print(f"Found {result.total_count} total, showing {len(result.applications)}")
    """
    applications: list[ApplicationRecord]
    total_count: int
    execution_time_ms: int