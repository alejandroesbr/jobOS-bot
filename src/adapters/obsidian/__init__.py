"""Obsidian Adapter - Graphify-compatible vault synchronization.

This package provides the concrete implementation of KnowledgeVaultPort for
synchronizing job applications to an Obsidian vault with Graphify structure.

Graphify is a knowledge graph methodology for Obsidian that uses:
- Structured YAML frontmatter for metadata and Dataview queries
- Wikilinks ([[Link]]) for bidirectional navigation
- Hub-and-spoke organization (index pages linking to entity pages)
- Tag-based categorization for filtering and views

Modules:
- adapter: ObsidianVaultAdapter - Main implementation of KnowledgeVaultPort
- frontmatter: YAML frontmatter generation for application notes
- hubs: Hub page creation (index and entity pages for companies, skills, etc.)
- wikilinks: Wikilink formatting and parsing utilities

The vault structure created:
vault/
├── applications/          # Individual job application notes
├── companies/             # Company hub pages (index + entities)
├── skills/                # Technology/skill hub pages (index + entities)
├── portals/               # Portal index pages
└── status/                # Status index pages

Example usage:
    >>> from src.adapters.obsidian import ObsidianVaultAdapter
    >>> from src.ports.repository_port import ApplicationRepositoryPort
    >>>
    >>> adapter = ObsidianVaultAdapter("~/vaults/job-search")
    >>> repo: ApplicationRepositoryPort = ...
    >>> apps = repo.find_all(limit=1000)
    >>> created, updated = adapter.sync_applications(apps)
    >>> print(f"Synced: {created} new, {updated} updated")
"""
from src.adapters.obsidian.adapter import ObsidianVaultAdapter

__all__ = ["ObsidianVaultAdapter"]