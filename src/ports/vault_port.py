"""Knowledge Vault Port - Abstract interface for Obsidian vault operations.

This module defines the abstract interface (Port) for synchronizing job application
data to an Obsidian vault with Graphify-compatible structure. The vault serves as
a personal knowledge base for job search tracking with bidirectional links.

The Graphify structure includes:
- applications/: Individual job application notes with YAML frontmatter
- companies/: Company hub pages linking to their applications
- skills/: Technology/skill hub pages linking to relevant applications
- portals/: Portal index pages
- status/: Application status index pages

All notes use Obsidian wikilinks ([[Link]]) for bidirectional navigation.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.domain.models import ApplicationRecord


class KnowledgeVaultPort(ABC):
    """Abstract interface for synchronizing applications to an Obsidian vault.

    Implementations handle the file system operations for creating and maintaining
    a Graphify-compatible Obsidian vault structure. The vault provides a visual
    knowledge graph of job applications, companies, skills, and their relationships.

    Key responsibilities:
    - Create/update application notes with rich frontmatter
    - Maintain hub indexes (companies, skills, portals, statuses)
    - Generate bidirectional wikilinks between related entities
    - Support incremental sync and full rebuild operations

    Example:
        >>> adapter = ObsidianVaultAdapter("~/vaults/job-search")
        >>> apps = repository.find_all(limit=1000)
        >>> created, updated = adapter.sync_applications(apps, "~/vaults/job-search")
        >>> print(f"Synced: {created} new, {updated} updated")
    """

    @abstractmethod
    def sync_applications(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path,
    ) -> tuple[int, int]:
        """Synchronize all applications to the Obsidian vault.

        Performs incremental sync: creates new notes for new applications,
        updates existing notes for changed applications, and rebuilds hub indexes.

        Args:
            applications: List of ApplicationRecord objects to synchronize
            vault_path: Root directory path of the Obsidian vault

        Returns:
            Tuple of (created_count, updated_count) indicating how many
            application note files were created vs updated

        Raises:
            VaultError: If vault directory cannot be created or written
            ValueError: If applications list is empty or vault_path invalid
            OSError: If file system operations fail (permissions, disk space)

        Example:
            >>> adapter = ObsidianVaultAdapter()
            >>> apps = repo.find_all(limit=500)
            >>> created, updated = adapter.sync_applications(apps, Path("vault"))
            >>> print(f"Created: {created}, Updated: {updated}")
        """
        ...

    @abstractmethod
    def sync_single_application(
        self,
        application: ApplicationRecord,
        vault_path: Path,
    ) -> Path:
        """Synchronize a single application to the vault.

        Creates or updates a single application note and updates relevant
        hub indexes. More efficient than full sync when only one application
        has changed.

        Args:
            application: Single ApplicationRecord to synchronize
            vault_path: Root directory path of the Obsidian vault

        Returns:
            Path to the created or updated application note file

        Raises:
            VaultError: If vault directory cannot be accessed
            ValueError: If application is None or vault_path invalid
            OSError: If file write operation fails

        Example:
            >>> new_app = repo.find_by_id(123)
            >>> note_path = adapter.sync_single_application(new_app, Path("vault"))
            >>> print(f"Synced to: {note_path}")
        """
        ...

    @abstractmethod
    def create_hubs(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path,
    ) -> int:
        """Create hub files for companies, skills, portals, and statuses.

        Generates index pages and individual hub pages for all entities
        referenced in the applications list. Hubs provide navigation and
        aggregation views in the Obsidian graph.

        Args:
            applications: List of applications to derive hub entities from
            vault_path: Root directory path of the Obsidian vault

        Returns:
            Total number of hub files created or updated (index + entity pages)

        Raises:
            VaultError: If hub directories cannot be created
            ValueError: If applications list is empty or vault_path invalid

        Example:
            >>> apps = repo.find_all(limit=1000)
            >>> hub_count = adapter.create_hubs(apps, Path("vault"))
            >>> print(f"Created/updated {hub_count} hub files")
        """
        ...

    @abstractmethod
    def rebuild_vault(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path,
    ) -> tuple[int, int]:
        """Completely rebuild the vault from application data.

        Removes all existing application notes and recreates the entire
        vault structure from scratch. Use when vault structure changes
        or for initial setup.

        Args:
            applications: Complete list of all applications
            vault_path: Root directory path of the Obsidian vault

        Returns:
            Tuple of (created_count, updated_count) for application notes.
            Hub files are recreated but not counted in return value.

        Raises:
            VaultError: If vault cannot be cleared or recreated
            ValueError: If applications list is empty or vault_path invalid
            OSError: If file deletion/creation fails

        Example:
            >>> apps = repo.find_all(limit=2000)
            >>> created, updated = adapter.rebuild_vault(apps, Path("vault"))
            >>> print(f"Full rebuild: {created} notes created")
        """
        ...

    @abstractmethod
    def get_vault_path(self) -> Optional[Path]:
        """Get the configured vault path, if any.

        Returns the vault path that was set during adapter initialization
        or the last sync operation.

        Returns:
            Path to vault root directory if configured and exists, None otherwise

        Example:
            >>> vault_path = adapter.get_vault_path()
            >>> if vault_path:
            ...     print(f"Vault configured at: {vault_path}")
            ... else:
            ...     print("No vault configured")
        """
        ...