"""Ports layer - Abstract interfaces for Clean Architecture."""
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.scraper_port import PortalScraperPort
from src.ports.vault_port import KnowledgeVaultPort
from src.ports.external_sync_port import ExternalSyncPort

__all__ = [
    "ApplicationRepositoryPort",
    "PortalScraperPort",
    "KnowledgeVaultPort",
    "ExternalSyncPort",
]