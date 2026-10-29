import logging
import os
from typing import Any

import httpx

from src.adapters.db.repository import ApplicationRepository
from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    WorkModality,
)
from src.domain.text_normalizer import build_dedup_key

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(
        self,
        api_token: str | None = None,
        database_id: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_token = api_token or os.getenv("NOTION_TOKEN", "")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID", "")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token and self.database_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def push_application(self, record: ApplicationRecord) -> str | None:
        if not self.is_configured:
            return None

        # Build properties payload
        primary_submission = record.submissions[0] if record.submissions else None
        portal_val = primary_submission.portal.value if primary_submission else "linkedin"
        url_val = primary_submission.canonical_url if primary_submission else "https://example.com"
        applied_at_val = record.last_applied_at or record.first_applied_at

        stack_tags = [{"name": kw.keyword[:100]} for kw in record.keywords if kw.is_matched][:10]

        properties: dict[str, Any] = {
            "Cargo": {"title": [{"text": {"content": record.title[:100]}}]},
            "Empresa": {"rich_text": [{"text": {"content": record.company[:100]}}]},
            "Portal": {"select": {"name": portal_val}},
            "Estado": {"select": {"name": record.status.value}},
            "Modalidad": {"select": {"name": record.modality.value}},
            "Stack Detectado": {"multi_select": stack_tags},
            "Match (%)": {"number": record.match_score},
            "Veces Postulado": {"number": record.times_applied},
            "Link Oferta": {"url": url_val},
        }

        if applied_at_val:
            properties["Último Envío"] = {"date": {"start": applied_at_val[:10]}}

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    f"{NOTION_API_BASE}/pages",
                    headers=self._headers(),
                    json=payload,
                )
                if res.status_code in {200, 201}:
                    data = res.json()
                    page_id = str(data.get("id"))
                    return page_id
                else:
                    logger.warning(f"Notion push failed (HTTP {res.status_code}): {res.text}")
                    return None
        except Exception as ex:
            logger.warning(f"Error pushing application to Notion: {ex}")
            return None

    def update_application(self, page_id: str, record: ApplicationRecord) -> bool:
        if not self.is_configured:
            return False

        properties: dict[str, Any] = {
            "Estado": {"select": {"name": record.status.value}},
            "Veces Postulado": {"number": record.times_applied},
        }
        if record.last_applied_at:
            properties["Último Envío"] = {"date": {"start": record.last_applied_at[:10]}}

        payload = {"properties": properties}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.patch(
                    f"{NOTION_API_BASE}/pages/{page_id}",
                    headers=self._headers(),
                    json=payload,
                )
                return res.status_code == 200
        except Exception as ex:
            logger.warning(f"Error updating application in Notion: {ex}")
            return False

    def pull_status_updates(self) -> list[tuple[str, str]]:
        if not self.is_configured:
            return []

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                    headers=self._headers(),
                    json={},
                )
                if res.status_code != 200:
                    logger.warning(f"Notion query failed (HTTP {res.status_code}): {res.text}")
                    return []

                data = res.json()
                results = data.get("results", [])
                updates: list[tuple[str, str]] = []

                for page in results:
                    page_id = page.get("id")
                    props = page.get("properties", {})
                    estado_prop = props.get("Estado", {})
                    select_val = estado_prop.get("select") or {}
                    status_name = select_val.get("name")
                    if page_id and status_name:
                        updates.append((page_id, status_name))

                return updates
        except Exception as ex:
            logger.warning(f"Error pulling status updates from Notion: {ex}")
            return []

    def bootstrap_to_repository(self, repository: ApplicationRepository) -> int:
        if not self.is_configured:
            return 0

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(
                    f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                    headers=self._headers(),
                    json={},
                )
                if res.status_code != 200:
                    return 0

                pages = res.json().get("results", [])
                restored_count = 0

                for page in pages:
                    page_id = page.get("id")
                    props = page.get("properties", {})

                    title_arr = props.get("Cargo", {}).get("title", [])
                    title = title_arr[0].get("text", {}).get("content", "") if title_arr else ""

                    comp_arr = props.get("Empresa", {}).get("rich_text", [])
                    company = comp_arr[0].get("text", {}).get("content", "") if comp_arr else ""

                    if not title or not company:
                        continue

                    portal_str = props.get("Portal", {}).get("select", {}).get("name", "linkedin")
                    portal = PortalName(portal_str) if portal_str in PortalName._value2member_map_ else PortalName.LINKEDIN

                    estado_str = props.get("Estado", {}).get("select", {}).get("name", "Enviado")
                    status = ApplicationStatus(estado_str) if estado_str in ApplicationStatus._value2member_map_ else ApplicationStatus.APPLIED

                    modality_str = props.get("Modalidad", {}).get("select", {}).get("name", "remote")
                    modality = WorkModality(modality_str) if modality_str in WorkModality._value2member_map_ else WorkModality.REMOTE

                    url = props.get("Link Oferta", {}).get("url") or f"https://notion.so/{page_id}"
                    match_score = int(props.get("Match (%)", {}).get("number") or 70)
                    times_applied = int(props.get("Veces Postulado", {}).get("number") or 1)

                    date_obj = props.get("Último Envío", {}).get("date") or {}
                    applied_date = date_obj.get("start")
                    applied_iso = f"{applied_date}T12:00:00Z" if applied_date else "2026-10-28T12:00:00Z"

                    dedup_key = build_dedup_key(company, title)
                    existing = repository.find_by_dedup_key(dedup_key)

                    if existing is None:
                        offer = JobOffer(
                            portal=portal,
                            title=title,
                            company=company,
                            location="Colombia",
                            modality=modality,
                            url=url,
                            description=f"Restaurada desde Notion ({page_id})",
                        )
                        evaluation = MatchEvaluation(
                            dedup_key=dedup_key,
                            canonical_url=url,
                            match_score=match_score,
                            should_apply=True,
                            is_hard_rejected=False,
                            rejection_reason=None,
                            keywords=(),
                        )
                        rec, _ = repository.record_submission(offer, evaluation, applied_at=applied_iso)
                        repository.update_notion_page_id(rec.id, page_id)
                        repository.update_status(rec.id, status)
                        restored_count += 1

                return restored_count
        except Exception as ex:
            logger.warning(f"Error bootstrapping Notion data: {ex}")
            return 0
