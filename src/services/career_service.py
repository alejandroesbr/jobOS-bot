from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
import re

from src.adapters.ai.gemini_client import GeminiClient
from src.adapters.db.repository import ApplicationRepository
from src.adapters.notion.notion_client import NotionClient
from src.config_loader import load_candidate_profile
from src.domain.models import ApplicationRecord, ApplicationStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SyncReport:
    pushed_new: int
    updated_existing: int
    pulled_statuses: int
    interview_preps_triggered: int
    stalled_followups: int
    bootstrapped_from_notion: int = 0


class CareerService:
    def __init__(
        self,
        repository: ApplicationRepository,
        gemini_client: GeminiClient | None = None,
        notion_client: NotionClient | None = None,
    ) -> None:
        self.repository = repository
        self.gemini_client = gemini_client or GeminiClient()
        self.notion_client = notion_client or NotionClient()

    def tailor_cv(self, application_id: int) -> str:
        record = self.repository.find_by_id(application_id)
        if not record:
            raise ValueError(f"Application ID {application_id} not found in database.")

        if record.cv_tailor_cache:
            return record.cv_tailor_cache

        cv_path = Path("config/cv_base.md")
        if not cv_path.is_file():
            cv_path = Path("config/cv_base.example.md")

        cv_text = cv_path.read_text(encoding="utf-8") if cv_path.is_file() else "# Hoja de Vida Base"

        analysis = self.gemini_client.tailor_cv(
            job_title=record.title,
            job_description=record.description,
            cv_base_markdown=cv_text,
        )

        self.repository.save_cv_tailor_cache(application_id, analysis)
        return analysis

    def prepare_interview(self, application_id: int) -> Path:
        record = self.repository.find_by_id(application_id)
        if not record:
            raise ValueError(f"Application ID {application_id} not found in database.")

        clean_company = re.sub(r"[^a-zA-Z0-9_-]", "_", record.company).strip("_")
        out_dir = Path("interviews")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{application_id}_{clean_company.lower()}.md"

        profile = load_candidate_profile()
        candidate_stack = list(profile.experience_years.keys())

        prep_content = self.gemini_client.prepare_interview(
            job_title=record.title,
            company=record.company,
            job_description=record.description,
            candidate_stack=candidate_stack,
        )

        out_file.write_text(prep_content, encoding="utf-8")
        self.repository.save_interview_prep_path(application_id, str(out_file))
        return out_file

    def check_followups(self, days_threshold: int = 7) -> list[ApplicationRecord]:
        all_apps = self.repository.find_all(status=ApplicationStatus.APPLIED, limit=500)
        stalled: list[ApplicationRecord] = []
        now_utc = datetime.now(timezone.utc)

        for app in all_apps:
            date_str = app.last_applied_at or app.first_applied_at
            if not date_str:
                continue

            try:
                applied_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                elapsed_days = (now_utc - applied_dt).total_seconds() / 86400.0
                if elapsed_days >= days_threshold:
                    self.repository.update_status(app.id, ApplicationStatus.FOLLOW_UP_REQUIRED)
                    stalled.append(app)
            except Exception:
                continue

        if stalled:
            followups_dir = Path("followups")
            followups_dir.mkdir(parents=True, exist_ok=True)
            report_file = followups_dir / "pendientes.md"

            lines = ["# Mensajes de Seguimiento Pendientes (Follow-ups)\n"]
            for app in stalled:
                lines.append(f"## {app.company} — {app.title}")
                lines.append(f"* **ID:** {app.id} | **Postulado:** {app.last_applied_at}")
                lines.append(
                    "```text\n"
                    f"Hola equipo de {app.company},\n"
                    f"Espero se encuentren muy bien. Les escribo para hacer un breve seguimiento a mi postulación "
                    f"para la posición de {app.title}. Me entusiasma mucho la oportunidad de aportar mi experiencia "
                    "en desarrollo full stack (React, Node.js, NestJS y PostgreSQL) a su equipo. "
                    "Quedo atento ante cualquier duda o siguiente paso del proceso.\n"
                    "¡Muchas gracias por su tiempo!\n```\n"
                )

            report_file.write_text("\n".join(lines), encoding="utf-8")

        return stalled

    def sync_with_notion(self) -> SyncReport:
        pushed_new = 0
        updated_existing = 0
        pulled_statuses = 0
        preps_triggered = 0
        bootstrapped = 0

        # Step 0: Multi-PC Bootstrap if local DB is empty
        all_local = self.repository.find_all(limit=10)
        if not all_local and self.notion_client.is_configured:
            bootstrapped = self.notion_client.bootstrap_to_repository(self.repository)

        # Step 1: PUSH un-synced to Notion
        unpushed = [app for app in self.repository.find_all(limit=500) if not app.notion_page_id]
        for app in unpushed:
            page_id = self.notion_client.push_application(app)
            if page_id:
                self.repository.update_notion_page_id(app.id, page_id)
                pushed_new += 1

        # Step 2: PUSH updates for re-applied offers
        reapplied = [app for app in self.repository.find_all(limit=500) if app.times_applied > 1 and app.notion_page_id]
        for app in reapplied:
            if app.notion_page_id:
                if self.notion_client.update_application(app.notion_page_id, app):
                    updated_existing += 1

        # Step 3: PULL manual status changes from Notion
        if self.notion_client.is_configured:
            updates = self.notion_client.pull_status_updates()
            page_map = {app.notion_page_id: app for app in self.repository.find_all(limit=500) if app.notion_page_id}

            for page_id, status_val in updates:
                if page_id in page_map:
                    local_app = page_map[page_id]
                    if local_app.status.value != status_val:
                        try:
                            new_status = ApplicationStatus(status_val)
                            self.repository.update_status(local_app.id, new_status)
                            pulled_statuses += 1

                            # Auto-trigger interview prep if changed to Interview
                            if (
                                new_status == ApplicationStatus.INTERVIEW_SCHEDULED
                                and not local_app.interview_prep_path
                            ):
                                self.prepare_interview(local_app.id)
                                preps_triggered += 1
                        except ValueError:
                            pass

        # Step 4: Check stalled follow-ups
        stalled = self.check_followups(days_threshold=7)

        return SyncReport(
            pushed_new=pushed_new,
            updated_existing=updated_existing,
            pulled_statuses=pulled_statuses,
            interview_preps_triggered=preps_triggered,
            stalled_followups=len(stalled),
            bootstrapped_from_notion=bootstrapped,
        )

