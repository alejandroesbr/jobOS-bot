import logging
import os
from pathlib import Path
import re
from typing import Any
import uuid

import httpx

from src.adapters.db.repository import ApplicationRepository
from src.config_loader import TechVocabulary
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


def _select_name(props: dict[str, Any], key: str) -> str | None:
    """Lee el valor de una propiedad select tolerando propiedades ausentes o vacías (select = null)."""
    select_val = (props.get(key) or {}).get("select") or {}
    name = select_val.get("name")
    return str(name) if name else None


def clean_notion_id(raw_id: str | None) -> str:
    if not raw_id:
        return ""
    cleaned = raw_id.strip()
    match = re.search(
        r"([a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        hex_val = match.group(1).replace("-", "").lower()
        return str(uuid.UUID(hex_val))
    return cleaned


class NotionClient:
    def __init__(
        self,
        api_token: str | None = None,
        database_id: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_token = api_token if api_token is not None else os.getenv("NOTION_TOKEN", "")
        raw_db_id = database_id if database_id is not None else os.getenv("NOTION_DATABASE_ID", "")
        self.database_id = clean_notion_id(raw_db_id)
        self.timeout = timeout
        self._resolved: bool = False

    def resolve_database_id(self) -> str:
        """Resolves whether database_id is a database or a page.
        If it is a page, discovers any child database or creates one automatically.
        """
        if not self.is_configured:
            return ""

        try:
            with httpx.Client(timeout=self.timeout) as client:
                db_res = client.get(f"{NOTION_API_BASE}/databases/{self.database_id}", headers=self._headers())
                if db_res.status_code == 200:
                    self._resolved = True
                    return self.database_id

                page_res = client.get(f"{NOTION_API_BASE}/pages/{self.database_id}", headers=self._headers())
                if page_res.status_code == 200:
                    blocks_res = client.get(
                        f"{NOTION_API_BASE}/blocks/{self.database_id}/children", headers=self._headers()
                    )
                    if blocks_res.status_code == 200:
                        blocks = blocks_res.json().get("results", [])
                        for block in blocks:
                            if block.get("type") == "child_database":
                                child_db_id = str(block.get("id"))
                                logger.info(
                                    f"Resolved child database '{block.get('child_database', {}).get('title')}' "
                                    f"({child_db_id}) inside page {self.database_id}"
                                )
                                self.database_id = child_db_id
                                self._persist_db_id_to_env(child_db_id)
                                self._resolved = True
                                return child_db_id

                        create_payload = {
                            "parent": {"type": "page_id", "page_id": self.database_id},
                            "title": [{"type": "text", "text": {"content": "Pipeline de Empleo"}}],
                            "properties": {
                                "Cargo": {"title": {}},
                                "Empresa": {"rich_text": {}},
                                "Portal": {"select": {}},
                                "Estado": {"select": {}},
                                "Modalidad": {"select": {}},
                                "Stack Detectado": {"multi_select": {}},
                                "Match (%)": {"number": {"format": "number"}},
                                "Veces Postulado": {"number": {"format": "number"}},
                                "Link Oferta": {"url": {}},
                                "Último Envío": {"date": {}},
                            },
                        }
                        create_res = client.post(
                            f"{NOTION_API_BASE}/databases", headers=self._headers(), json=create_payload
                        )
                        if create_res.status_code in {200, 201}:
                            new_db_id = str(create_res.json().get("id"))
                            logger.info(
                                f"Created new database 'Pipeline de Empleo' ({new_db_id}) inside page {self.database_id}"
                            )
                            self.database_id = new_db_id
                            self._persist_db_id_to_env(new_db_id)
                            self._resolved = True
                            return new_db_id
        except Exception as ex:
            logger.warning(f"Error resolving Notion database ID: {ex}")

        self._resolved = True
        return self.database_id

    def _persist_db_id_to_env(self, new_db_id: str) -> None:
        try:
            env_path = Path(".env")
            if env_path.is_file():
                content = env_path.read_text(encoding="utf-8")
                updated = re.sub(r"NOTION_DATABASE_ID=.*", f"NOTION_DATABASE_ID={new_db_id}", content)
                env_path.write_text(updated, encoding="utf-8")
        except Exception:
            pass

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token and self.database_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _query_all_pages(self, client: httpx.Client) -> list[dict[str, Any]] | None:
        """Consulta todas las páginas de la base de datos siguiendo la paginación de Notion (100 por página)."""
        pages: list[dict[str, Any]] = []
        body: dict[str, Any] = {"page_size": 100}
        while True:
            res = client.post(
                f"{NOTION_API_BASE}/databases/{self.database_id}/query",
                headers=self._headers(),
                json=body,
            )
            if res.status_code != 200:
                logger.warning(f"Notion query failed (HTTP {res.status_code}): {res.text}")
                return None
            data = res.json()
            pages.extend(data.get("results", []))
            next_cursor = data.get("next_cursor")
            if not data.get("has_more") or not next_cursor:
                return pages
            body = {"page_size": 100, "start_cursor": next_cursor}

    def push_application(self, record: ApplicationRecord) -> str | None:
        if not self.is_configured:
            return None

        if not self._resolved:
            self.resolve_database_id()

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
                elif res.status_code == 400 and "is a page, not a database" in res.text:
                    new_id = self.resolve_database_id()
                    payload["parent"]["database_id"] = new_id
                    retry_res = client.post(
                        f"{NOTION_API_BASE}/pages",
                        headers=self._headers(),
                        json=payload,
                    )
                    if retry_res.status_code in {200, 201}:
                        return str(retry_res.json().get("id"))
                    logger.warning(f"Notion push retry failed (HTTP {retry_res.status_code}): {retry_res.text}")
                    return None
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

        if not self._resolved:
            self.resolve_database_id()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                results = self._query_all_pages(client)
                if results is None:
                    return []

                updates: list[tuple[str, str]] = []
                for page in results:
                    page_id = page.get("id")
                    status_name = _select_name(page.get("properties", {}), "Estado")
                    if page_id and status_name:
                        updates.append((page_id, status_name))

                return updates
        except Exception as ex:
            logger.warning(f"Error pulling status updates from Notion: {ex}")
            return []

    def bootstrap_to_repository(
        self,
        repository: ApplicationRepository,
        vocabulary: TechVocabulary | None = None,
    ) -> int:
        if not self.is_configured:
            return 0

        if not self._resolved:
            self.resolve_database_id()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                pages = self._query_all_pages(client)
        except Exception as ex:
            logger.warning(f"Error bootstrapping Notion data: {ex}")
            return 0
        if pages is None:
            return 0

        restored_count = 0
        for page in pages:
            # Una página mal formada no debe cortar la restauración del resto.
            try:
                if self._restore_page(page, repository, vocabulary):
                    restored_count += 1
            except Exception as ex:
                logger.warning(f"Página de Notion omitida en bootstrap ({page.get('id')}): {ex}")
        return restored_count

    def _restore_page(
        self,
        page: dict[str, Any],
        repository: ApplicationRepository,
        vocabulary: TechVocabulary | None,
    ) -> bool:
        page_id = str(page.get("id"))
        props: dict[str, Any] = page.get("properties", {})

        title_arr = (props.get("Cargo") or {}).get("title") or []
        title = title_arr[0].get("text", {}).get("content", "") if title_arr else ""

        comp_arr = (props.get("Empresa") or {}).get("rich_text") or []
        company = comp_arr[0].get("text", {}).get("content", "") if comp_arr else ""

        if not title or not company:
            return False

        dedup_key = build_dedup_key(company, title)
        if repository.find_by_dedup_key(dedup_key) is not None:
            return False

        portal_str = _select_name(props, "Portal") or ""
        portal = PortalName(portal_str) if portal_str in PortalName._value2member_map_ else PortalName.LINKEDIN

        estado_str = _select_name(props, "Estado") or ""
        status = ApplicationStatus(estado_str) if estado_str in ApplicationStatus._value2member_map_ else ApplicationStatus.APPLIED

        modality_str = _select_name(props, "Modalidad") or ""
        modality = WorkModality(modality_str) if modality_str in WorkModality._value2member_map_ else WorkModality.REMOTE

        url = (props.get("Link Oferta") or {}).get("url") or f"https://notion.so/{page_id}"

        raw_score = (props.get("Match (%)") or {}).get("number")
        match_score = int(raw_score) if raw_score is not None else 70

        raw_times = (props.get("Veces Postulado") or {}).get("number")
        default_times = 0 if status == ApplicationStatus.PENDING else 1
        times_applied = int(raw_times) if raw_times is not None else default_times

        stack_tags = (props.get("Stack Detectado") or {}).get("multi_select") or []
        keywords = tuple(
            KeywordMatch(
                keyword=str(tag["name"]),
                is_matched=True,
                weight=vocabulary.get_weight(str(tag["name"])) if vocabulary else KeywordWeight.BONUS,
            )
            for tag in stack_tags
            if tag.get("name")
        )

        date_obj = (props.get("Último Envío") or {}).get("date") or {}
        applied_date = date_obj.get("start")
        applied_iso = f"{applied_date[:10]}T12:00:00Z" if applied_date else None

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
            keywords=keywords,
        )
        rec, _ = repository.record_submission(offer, evaluation, applied_at=applied_iso)
        repository.update_notion_page_id(rec.id, page_id)
        repository.update_status(rec.id, status)
        repository.update_times_applied(rec.id, times_applied)
        repository.update_notion_synced_status(rec.id, status)
        return True
