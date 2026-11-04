"""Ports layer - Abstract interfaces for Clean Architecture."""
from src.ports.external_sync_port import ExternalSyncPort, SyncReport
from src.ports.repository_port import ApplicationRepositoryPort
from src.ports.scraper_port import (
    MultiPortalScraperPort,
    PortalScanResult,
    PortalScraperPort,
)
from src.ports.vault_port import KnowledgeVaultPort

__all__ = [
    "ApplicationRepositoryPort",
    "PortalScraperPort",
    "MultiPortalScraperPort",
    "PortalScanResult",
    "KnowledgeVaultPort",
    "ExternalSyncPort",
    "SyncReport",
]
