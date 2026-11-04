"""Obsidian Vault Adapter - Graphify-compatible implementation.

This module provides the concrete implementation of KnowledgeVaultPort for
synchronizing job applications to an Obsidian vault with Graphify structure.

Graphify is a knowledge graph methodology for Obsidian that uses:
- Structured YAML frontmatter for metadata and queries
- Wikilinks ([[Link]]) for bidirectional navigation
- Hub-and-spoke organization (index pages linking to entity pages)
- Tag-based categorization for filtering and views

The adapter creates the following vault structure:
vault/
├── applications/          # Individual job application notes
│   ├── linkedin_12345.md
│   └── getonbrd_67890.md
├── companies/             # Company hub pages
│   ├── index.md           # Index of all companies
│   ├── Google.md          # Company page linking to its applications
│   └── Microsoft.md
├── skills/                # Technology/skill hub pages
│   ├── index.md           # Index of all skills by demand
│   ├── React.md           # Skill page linking to relevant applications
│   └── Python.md
├── portals/               # Portal index pages
│   └── index.md
└── status/                # Status index pages
    └── index.md
"""
from pathlib import Path
from typing import Optional

from src.ports.vault_port import KnowledgeVaultPort
from src.ports.repository_port import ApplicationRepositoryPort
from src.domain.models import ApplicationRecord
from src.adapters.obsidian.frontmatter import build_frontmatter, format_yaml_frontmatter
from src.adapters.obsidian.hubs import (
    create_hub_files,
    ensure_hub_directories,
    build_companies_index,
    build_skills_index,
    build_portals_index,
    build_status_index,
    create_company_hubs,
    create_skill_hubs,
    create_portal_hubs,
    create_status_hubs,
)
from src.adapters.obsidian.wikilinks import sanitize_for_filename


class ObsidianVaultAdapter(KnowledgeVaultPort):
    """Adapter for syncing applications to Obsidian vault with Graphify structure.

    This adapter implements the KnowledgeVaultPort interface using the local
    filesystem. It creates markdown files with YAML frontmatter and wikilinks
    following Graphify conventions for knowledge graph visualization in Obsidian.

    The adapter maintains internal directory paths for each vault section
    and provides methods for incremental sync, single-item sync, hub creation,
    and full vault rebuild.

    Attributes:
        vault_path: Root path of the Obsidian vault
        applications_dir: Path to applications/ subdirectory
        companies_dir: Path to companies/ subdirectory
        skills_dir: Path to skills/ subdirectory
        portals_dir: Path to portals/ subdirectory
        status_dir: Path to status/ subdirectory

    Example:
        >>> adapter = ObsidianVaultAdapter("~/vaults/job-search")
        >>> apps = repository.find_all(limit=1000)
        >>> created, updated = adapter.sync_applications(apps)
        >>> print(f"Synced: {created} new, {updated} updated")
    """

    def __init__(self, vault_path: Path | str = "vault") -> None:
        """Initialize the adapter with a vault path.

        Args:
            vault_path: Root directory path for the Obsidian vault.
                Defaults to "vault" in current working directory.
                Can be absolute or relative path.

        Example:
            >>> adapter = ObsidianVaultAdapter("~/vaults/job-search")
            >>> adapter = ObsidianVaultAdapter("/absolute/path/to/vault")
        """
        self.vault_path = Path(vault_path).expanduser()
        self.applications_dir = self.vault_path / "applications"
        self.companies_dir = self.vault_path / "companies"
        self.skills_dir = self.vault_path / "skills"
        self.portals_dir = self.vault_path / "portals"
        self.status_dir = self.vault_path / "status"

    def sync_applications(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path | str | None = None,
    ) -> tuple[int, int]:
        """Sync applications to Obsidian vault.

        Performs incremental synchronization: creates new notes for new applications,
        updates existing notes for changed applications, and rebuilds all hub indexes.
        This is the main entry point for bulk vault synchronization.

        Args:
            applications: List of ApplicationRecord objects to synchronize.
                Should be the complete set of applications for accurate hub indexes.
            vault_path: Optional override for vault path. If provided, updates
                the adapter's internal vault path for this and future operations.

        Returns:
            Tuple of (created_count, updated_count) indicating how many
            application note files were created vs updated.

        Raises:
            VaultError: If vault directories cannot be created or written
            ValueError: If applications list is empty
            OSError: If file system operations fail (permissions, disk space)

        Example:
            >>> adapter = ObsidianVaultAdapter("vault")
            >>> apps = repo.find_all(limit=1000)
            >>> created, updated = adapter.sync_applications(apps)
            >>> print(f"Created: {created}, Updated: {updated}")
        """
        if vault_path is not None:
            self.vault_path = Path(vault_path).expanduser()
            self._update_paths()

        self._ensure_directories()
        self._create_all_hubs(applications)

        created = 0
        updated = 0

        for app in applications:
            note_path = self._get_note_path(app)
            if note_path.exists():
                updated += 1
            else:
                created += 1
            self._write_application_note(app, note_path)

        # Update hub indexes and entity hub pages with latest data
        build_companies_index(applications, self.companies_dir)
        build_skills_index(applications, self.skills_dir)
        build_portals_index(applications, self.portals_dir)
        build_status_index(applications, self.status_dir)
        create_company_hubs(applications, self.companies_dir)
        create_skill_hubs(applications, self.skills_dir)
        create_portal_hubs(applications, self.portals_dir)
        create_status_hubs(applications, self.status_dir)

        return created, updated

    def sync_single_application(
        self,
        application: ApplicationRecord,
        vault_path: Path | str | None = None,
    ) -> Path:
        """Synchronize a single application to the vault.

        Creates or updates a single application note without overwriting
        global hub index files with a partial single-element list.

        Args:
            application: Single ApplicationRecord to synchronize
            vault_path: Optional override for vault path

        Returns:
            Path to the created or updated application note file

        Raises:
            VaultError: If vault directories cannot be accessed
            ValueError: If application is None or vault_path invalid
            OSError: If file write operation fails

        Example:
            >>> new_app = repo.find_by_id(123)
            >>> note_path = adapter.sync_single_application(new_app)
            >>> print(f"Synced to: {note_path}")
        """
        if vault_path is not None:
            self.vault_path = Path(vault_path).expanduser()
            self._update_paths()

        self._ensure_directories()
        ensure_hub_directories(self)
        create_hub_files(self)

        note_path = self._get_note_path(application)
        self._write_application_note(application, note_path)

        return note_path

    def create_hubs(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path | str | None = None,
    ) -> int:
        """Create hub files for companies, skills, portals, and statuses.

        Generates all hub index pages and individual entity hub pages
        from the provided applications. Does not create application notes.

        Args:
            applications: List of applications to derive hub entities from
            vault_path: Optional override for vault path

        Returns:
            Number of hub files created/updated (index pages + entity pages)

        Raises:
            VaultError: If hub directories cannot be created
            ValueError: If applications list is empty or vault_path invalid

        Example:
            >>> apps = repo.find_all(limit=1000)
            >>> hub_count = adapter.create_hubs(apps)
            >>> print(f"Created/updated {hub_count} hub files")
        """
        if vault_path is not None:
            self.vault_path = Path(vault_path).expanduser()
            self._update_paths()

        self._ensure_directories()
        self._create_all_hubs(applications)

        # Build dynamic indexes and entity hubs
        build_companies_index(applications, self.companies_dir)
        build_skills_index(applications, self.skills_dir)
        build_portals_index(applications, self.portals_dir)
        build_status_index(applications, self.status_dir)
        create_company_hubs(applications, self.companies_dir)
        create_skill_hubs(applications, self.skills_dir)
        create_portal_hubs(applications, self.portals_dir)
        create_status_hubs(applications, self.status_dir)

        # Count hub files created
        count = 0
        for hub_dir in [self.companies_dir, self.skills_dir, self.portals_dir, self.status_dir]:
            count += len(list(hub_dir.glob("*.md")))

        return count

    def rebuild_vault(
        self,
        applications: list[ApplicationRecord],
        vault_path: Path | str = "vault",
    ) -> tuple[int, int]:
        """Completely rebuild the vault from application data.

        Removes all existing application notes and recreates the entire
        vault structure from scratch. Use when vault structure changes
        or for initial setup.

        Args:
            applications: Complete list of all applications
            vault_path: Root path of the Obsidian vault (required for rebuild)

        Returns:
            Tuple of (created_count, updated_count) for application notes.
            Since this is a rebuild, updated_count will always be 0.

        Raises:
            VaultError: If vault cannot be cleared or recreated
            ValueError: If applications list is empty or vault_path invalid
            OSError: If file deletion/creation fails

        Example:
            >>> apps = repo.find_all(limit=2000)
            >>> created, updated = adapter.rebuild_vault(apps, "vault")
            >>> print(f"Full rebuild: {created} notes created")
        """
        self.vault_path = Path(vault_path).expanduser()
        self._update_paths()
        self._ensure_directories()

        # Remove existing application notes
        for note in self.applications_dir.glob("*.md"):
            note.unlink()

        return self.sync_applications(applications)

    def get_vault_path(self) -> Optional[Path]:
        """Get the configured vault path.

        Returns:
            Path to vault root directory if it exists, None otherwise

        Example:
            >>> vault_path = adapter.get_vault_path()
            >>> if vault_path:
            ...     print(f"Vault at: {vault_path}")
            ... else:
            ...     print("Vault not initialized")
        """
        return self.vault_path if self.vault_path.exists() else None

    def _ensure_directories(self) -> None:
        """Ensure all vault directories exist.

        Creates the five main vault subdirectories if they don't exist:
        applications/, companies/, skills/, portals/, status/

        Raises:
            OSError: If directory creation fails (permissions, etc.)
        """
        for dir_path in [
            self.applications_dir,
            self.companies_dir,
            self.skills_dir,
            self.portals_dir,
            self.status_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _update_paths(self) -> None:
        """Update internal paths when vault_path changes.

        Recalculates all subdirectory paths based on the new vault_path.
        Called after vault_path is modified via sync methods.
        """
        self.applications_dir = self.vault_path / "applications"
        self.companies_dir = self.vault_path / "companies"
        self.skills_dir = self.vault_path / "skills"
        self.portals_dir = self.vault_path / "portals"
        self.status_dir = self.vault_path / "status"

    def _create_all_hubs(self, applications: list[ApplicationRecord]) -> None:
        """Create all hub directories and index files.

        Initializes the static hub index templates (portals, status) and
        ensures all hub directories exist.

        Args:
            applications: List of applications (used for dynamic hubs)
        """
        ensure_hub_directories(self)
        create_hub_files(self)

    def _get_note_path(self, app: ApplicationRecord) -> Path:
        """Generate note filename from dedup_key.

        Creates a filesystem-safe filename from the application's deduplication
        key by replacing path separators and special characters.

        Args:
            app: ApplicationRecord to generate path for

        Returns:
            Path to the application note file (may not exist yet)

        Example:
            >>> app.dedup_key = "linkedin::12345"
            >>> path = adapter._get_note_path(app)
            >>> print(path)  # vault/applications/linkedin_12345.md
        """
        safe_name = sanitize_for_filename(app.dedup_key.replace("::", "_"))
        return self.applications_dir / f"{safe_name}.md"

    def _write_application_note(self, app: ApplicationRecord, note_path: Path) -> None:
        """Write application note with frontmatter and content.

        Generates a complete markdown note with YAML frontmatter containing
        all application metadata and wikilinks, followed by human-readable
        content sections.

        Args:
            app: ApplicationRecord to write
            note_path: Target file path for the note

        Raises:
            OSError: If file write fails
        """
        # Extract matched skills
        matched_skills = [kw.keyword for kw in app.keywords if kw.is_matched]

        fm = build_frontmatter(app, matched_skills)
        frontmatter_yaml = format_yaml_frontmatter(fm)

        # Build content
        portal_value = app.submissions[0].portal.value if app.submissions else "unknown"
        url_value = app.submissions[0].canonical_url if app.submissions else "#"

        content_lines = [
            frontmatter_yaml,
            "",
            f"# {app.title}",
            f"**Empresa:** {fm.company_link}",
            f"**Portal:** {fm.portal_link}",
            f"**Modalidad:** {app.modality.value}",
            f"**Ubicación:** {app.location}",
            f"**Match Score:** {app.match_score}%",
            f"**Veces Postulado:** {app.times_applied}",
            f"**Estado:** {fm.status_link}",
            "",
            "## Enlace a la Oferta",
            f"[{url_value}]({url_value})",
            "",
            "## Descripción",
            app.description[:3000] if app.description else "*Sin descripción disponible*",
            "",
            "## Keywords Detectadas",
        ]

        for kw in app.keywords:
            status = "✅" if kw.is_matched else "❌"
            weight_label = {3: "CORE", 2: "SECONDARY", 1: "BONUS"}.get(int(kw.weight), "UNKNOWN")
            safe_kw = sanitize_for_filename(kw.keyword)
            content_lines.append(f"- {status} **[[{safe_kw}]]** ({weight_label})")

        note_path.write_text("\n".join(content_lines), encoding="utf-8")