"""Application Repository Port - Abstract interface for persistence operations.

This module defines the abstract interface (Port) for application data persistence
following the Clean Architecture pattern. Concrete implementations (Adapters) handle
the actual storage mechanism (e.g., SQLite, PostgreSQL, in-memory).

The port isolates the application layer from persistence details, enabling:
- Easy testing with mock implementations
- Swapping storage backends without changing business logic
- Clear separation of concerns between domain logic and data access
"""
from abc import ABC, abstractmethod
from typing import Optional

from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobOffer,
    MatchEvaluation,
    PortalName,
)


class ApplicationRepositoryPort(ABC):
    """Abstract interface for application persistence operations.

    This port defines the contract for storing and retrieving job application records.
    Implementations must provide thread-safe operations and handle connection lifecycle.

    Attributes:
        None (interface only)

    Example:
        >>> repo = SQLiteApplicationRepository("data/jobs.db")
        >>> record = repo.find_by_dedup_key("linkedin::12345")
        >>> if record:
        ...     print(f"Found: {record.title} @ {record.company}")
    """

    @abstractmethod
    def find_by_dedup_key(self, dedup_key: str) -> Optional[ApplicationRecord]:
        """Find an application by its deduplication key.

        The deduplication key uniquely identifies a job offer across portals
        (format: "portal::external_id"). Used to detect re-applications.

        Args:
            dedup_key: Unique identifier in format "portal::external_id"
                (e.g., "linkedin::12345", "getonbrd::67890")

        Returns:
            ApplicationRecord if found, None otherwise

        Raises:
            RepositoryError: If database connection fails
            ValueError: If dedup_key format is invalid

        Example:
            >>> record = repo.find_by_dedup_key("linkedin::12345")
            >>> assert record is not None
            >>> print(record.times_applied)  # Number of times applied to this offer
        """
        ...

    @abstractmethod
    def find_by_id(self, application_id: int) -> Optional[ApplicationRecord]:
        """Find an application by its primary key (database ID).

        Args:
            application_id: Auto-increment integer primary key

        Returns:
            ApplicationRecord if found, None otherwise

        Raises:
            RepositoryError: If database connection fails
            ValueError: If application_id is negative

        Example:
            >>> record = repo.find_by_id(42)
            >>> if record:
            ...     print(f"Application #{record.id}: {record.title}")
        """
        ...

    @abstractmethod
    def find_all(
        self,
        status: Optional[ApplicationStatus] = None,
        min_match: Optional[int] = None,
        keyword: Optional[str] = None,
        limit: int = 50,
    ) -> list[ApplicationRecord]:
        """Find applications with optional filters.

        Supports filtering by status, minimum match score, and keyword search
        across title, company, description, and matched keywords.

        Args:
            status: Filter by application status (e.g., ApplicationStatus.SENT)
            min_match: Minimum match score percentage (0-100)
            keyword: Search term to match against title, company, description, keywords
            limit: Maximum number of records to return (default: 50)

        Returns:
            List of ApplicationRecord objects matching criteria, ordered by
            most recent first (by last_applied_at or first_applied_at)

        Raises:
            RepositoryError: If database connection fails
            ValueError: If limit is negative or min_match not in 0-100 range

        Example:
            >>> # Get all sent applications with match >= 70%
            >>> apps = repo.find_all(
            ...     status=ApplicationStatus.SENT,
            ...     min_match=70,
            ...     limit=20
            ... )
            >>> # Search for React-related applications
            >>> apps = repo.find_all(keyword="react", limit=10)
        """
        ...

    @abstractmethod
    def record_submission(
        self,
        offer: JobOffer,
        evaluation: MatchEvaluation,
        applied_at: Optional[str] = None,
        cooldown_days: int = 3,
    ) -> tuple[ApplicationRecord, bool]:
        """Record a new application or re-application.

        Implements upsert logic: creates new record if dedup_key doesn't exist,
        or updates existing record incrementing times_applied. Respects cooldown
        period to prevent duplicate submissions within a short timeframe.

        Args:
            offer: Normalized JobOffer from scraper
            evaluation: MatchEvaluation with score, matched keywords, hard reject flags
            applied_at: ISO timestamp of application (default: current UTC time)
            cooldown_days: Minimum days between re-applications to same offer (default: 3)

        Returns:
            tuple: (ApplicationRecord, bool) where:
                - ApplicationRecord: The created or updated record
                - bool: True if application was recorded, False if skipped due to cooldown

        Raises:
            RepositoryError: If database operation fails
            ValueError: If cooldown_days is negative or offer/evaluation invalid

        Example:
            >>> record, applied = repo.record_submission(offer, evaluation)
            >>> if applied:
            ...     print(f"Applied! Total applications to this offer: {record.times_applied}")
            ... else:
            ...     print("Skipped - within cooldown period")
        """
        ...

    @abstractmethod
    def update_status(self, application_id: int, status: ApplicationStatus) -> bool:
        """Update the status of an application.

        Args:
            application_id: Primary key of the application
            status: New ApplicationStatus value

        Returns:
            True if record was updated, False if application_id not found

        Raises:
            RepositoryError: If database operation fails
            ValueError: If application_id is negative or status invalid

        Example:
            >>> success = repo.update_status(42, ApplicationStatus.INTERVIEW_SCHEDULED)
            >>> if success:
            ...     print("Status updated to INTERVIEW_SCHEDULED")
        """
        ...

    @abstractmethod
    def update_notion_page_id(self, application_id: int, notion_page_id: str) -> bool:
        """Link a Notion page ID to an application.

        Used during Notion sync to track which Notion page corresponds to
        each application record.

        Args:
            application_id: Primary key of the application
            notion_page_id: Notion page UUID (e.g., "abc123-def456-...")

        Returns:
            True if record was updated, False if application_id not found

        Raises:
            RepositoryError: If database operation fails
            ValueError: If application_id is negative or notion_page_id empty

        Example:
            >>> success = repo.update_notion_page_id(42, "abc123-def456-789")
            >>> assert success
        """
        ...

    @abstractmethod
    def get_keyword_stats(self) -> list[tuple[str, int, int]]:
        """Get statistics for keywords: (keyword, total_jobs, matched_jobs).

        Aggregates keyword frequency across all applications, showing how many
        total job postings mention each keyword and how many of those were
        matched (applied to).

        Returns:
            List of tuples: (keyword, total_jobs, matched_jobs), sorted by
            total_jobs descending

        Raises:
            RepositoryError: If database operation fails

        Example:
            >>> stats = repo.get_keyword_stats()
            >>> for keyword, total, matched in stats[:10]:
            ...     print(f"{keyword}: {matched}/{total} ({matched/total*100:.1f}%)")
        """
        ...

    @abstractmethod
    def upsert_qa_memory(
        self,
        question_norm: str,
        raw_example: str,
        answer: str,
    ) -> None:
        """Upsert a question-answer pair into the QA memory.

        Stores normalized question patterns with example raw questions and
        generated answers for form autocompletion assistance. Uses
        question_norm as the deduplication key.

        Args:
            question_norm: Normalized question pattern (lowercase, stripped,
                punctuation removed, e.g., "what is your experience with react")
            raw_example: Original raw question text from a form
            answer: Generated or user-provided answer to store

        Raises:
            RepositoryError: If database operation fails
            ValueError: If any argument is empty or None

        Example:
            >>> repo.upsert_qa_memory(
            ...     question_norm="what is your experience with react",
            ...     raw_example="¿Cuál es tu experiencia con React?",
            ...     answer="3 years building production React applications..."
            ... )
        """
        ...

    @abstractmethod
    def get_all_qa_memory(self) -> list[tuple[str, str, str, str]]:
        """Get all QA memory entries: (question_norm, raw_example, answer, category).

        Retrieves all stored question-answer pairs for use in form autocompletion.

        Returns:
            List of tuples: (question_norm, raw_example, answer, category)

        Raises:
            RepositoryError: If database operation fails

        Example:
            >>> qa_pairs = repo.get_all_qa_memory()
            >>> for norm, raw, ans, cat in qa_pairs:
            ...     print(f"Q: {raw} -> A: {ans[:50]}...")
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the repository connection.

        Releases any held resources (database connections, file handles, etc.).
        Should be called during application shutdown.

        Raises:
            RepositoryError: If closing connection fails

        Example:
            >>> repo.close()
            >>> # Repository no longer usable after this
        """
        ...