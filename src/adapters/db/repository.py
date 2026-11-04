from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from rapidfuzz import fuzz

from src.domain.models import (
    ApplicationRecord,
    ApplicationStatus,
    JobOffer,
    KeywordMatch,
    KeywordWeight,
    MatchEvaluation,
    PortalName,
    SubmissionAttempt,
    WorkModality,
)
from src.domain.text_normalizer import normalize_company_name, normalize_job_title
from src.ports.repository_port import ApplicationRepositoryPort


def _get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _days_between(date_str_1: str, date_str_2: str) -> float:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    dt1 = datetime.strptime(date_str_1, fmt).replace(tzinfo=timezone.utc)
    dt2 = datetime.strptime(date_str_2, fmt).replace(tzinfo=timezone.utc)
    return abs((dt1 - dt2).total_seconds()) / 86400.0


class ApplicationRepository(ApplicationRepositoryPort):
    def __init__(self, connection: sqlite3.Connection | str = ":memory:") -> None:
        if isinstance(connection, str):
            db_path = Path(connection)
            if db_path.name != ":memory:":
                db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(connection)
        else:
            self._conn = connection

        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self.initialize_schema()

    def initialize_schema(self) -> None:
        self._ensure_columns()
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.is_file():
            sql = schema_path.read_text(encoding="utf-8")
            self._conn.executescript(sql)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        cursor = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='applications';"
        )
        if not cursor.fetchone():
            return

        col_cursor = self._conn.execute("PRAGMA table_info(applications);")
        existing_cols = {str(row["name"]) for row in col_cursor.fetchall()}
        with self._conn:
            if "company_norm" not in existing_cols:
                self._conn.execute(
                    "ALTER TABLE applications ADD COLUMN company_norm TEXT NOT NULL DEFAULT '';"
                )
            if "title_norm" not in existing_cols:
                self._conn.execute(
                    "ALTER TABLE applications ADD COLUMN title_norm TEXT NOT NULL DEFAULT '';"
                )
            rows = self._conn.execute(
                "SELECT id, company, title FROM applications WHERE company_norm = '' OR title_norm = '';"
            ).fetchall()
            for r in rows:
                self._conn.execute(
                    "UPDATE applications SET company_norm = ?, title_norm = ? WHERE id = ?;",
                    (normalize_company_name(str(r["company"])), normalize_job_title(str(r["title"])), int(r["id"])),
                )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_applications_company_title ON applications(company_norm, title_norm);"
            )

    def close(self) -> None:
        self._conn.close()

    def should_reapply(
        self,
        existing_record: ApplicationRecord,
        new_portal: PortalName,
        current_time_iso: str,
        cooldown_days: int = 3,
    ) -> tuple[bool, str]:
        if not existing_record.status.allows_reapplication():
            return False, f"Application is in terminal or protected status: '{existing_record.status.value}'."

        portals_used = {sub.portal for sub in existing_record.submissions}
        if new_portal not in portals_used:
            return True, f"New portal '{new_portal.value}' detected."

        if not existing_record.last_applied_at:
            return True, "No previous submission date recorded."

        elapsed_days = _days_between(current_time_iso, existing_record.last_applied_at)
        if elapsed_days >= cooldown_days:
            return True, f"Cooldown satisfied: {elapsed_days:.1f} days elapsed (minimum: {cooldown_days})."

        return False, f"Cooldown active: only {elapsed_days:.1f} days elapsed on portal '{new_portal.value}'."

    def find_by_dedup_key(self, dedup_key: str) -> ApplicationRecord | None:
        cursor = self._conn.execute(
            "SELECT * FROM applications WHERE dedup_key = ?", (dedup_key,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._hydrate_application(row)

    def find_by_id(self, application_id: int) -> ApplicationRecord | None:
        cursor = self._conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._hydrate_application(row)

    def find_by_company_blocking(
        self,
        company: str,
        title: str,
        threshold: float = 88.0,
    ) -> ApplicationRecord | None:
        company_norm = normalize_company_name(company)
        title_norm = normalize_job_title(title)
        if not company_norm or not title_norm:
            return None

        cursor = self._conn.execute(
            "SELECT * FROM applications WHERE company_norm = ?",
            (company_norm,),
        )
        rows = cursor.fetchall()
        best_row: sqlite3.Row | None = None
        best_score = 0.0

        for row in rows:
            candidate_title_norm = str(row["title_norm"]) or normalize_job_title(str(row["title"]))
            score = float(fuzz.token_sort_ratio(title_norm, candidate_title_norm))
            if score >= threshold and score > best_score:
                best_score = score
                best_row = row

        if best_row is not None:
            return self._hydrate_application(best_row)
        return None

    def find_all(
        self,
        status: ApplicationStatus | None = None,
        min_match: int | None = None,
        keyword: str | None = None,
        limit: int = 50,
    ) -> list[ApplicationRecord]:
        clauses: list[str] = []
        params: list[Any] = []

        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)

        if min_match is not None:
            clauses.append("match_score >= ?")
            params.append(min_match)

        if keyword is not None and keyword.strip():
            kw_pattern = f"%{keyword.strip().lower()}%"
            clauses.append(
                "("
                "LOWER(title) LIKE ? OR "
                "LOWER(company) LIKE ? OR "
                "LOWER(description) LIKE ? OR "
                "EXISTS ("
                "SELECT 1 FROM application_keywords ak "
                "WHERE ak.application_id = applications.id AND LOWER(ak.keyword) LIKE ?"
                ")"
                ")"
            )
            params.extend([kw_pattern, kw_pattern, kw_pattern, kw_pattern])

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = (
            f"SELECT * FROM applications{where_sql} "
            "ORDER BY match_score DESC, last_applied_at DESC LIMIT ?"
        )
        params.append(limit)
        cursor = self._conn.execute(query_sql, tuple(params))
        return [self._hydrate_application(row) for row in cursor.fetchall()]

    def record_submission(
        self,
        offer: JobOffer,
        evaluation: MatchEvaluation,
        applied_at: str | None = None,
        cooldown_days: int = 3,
    ) -> tuple[ApplicationRecord, bool]:
        timestamp = applied_at or _get_utc_now_iso()
        existing = self.find_by_dedup_key(evaluation.dedup_key)
        if existing is None:
            existing = self.find_by_company_blocking(offer.company, offer.title)

        if existing is None:
            return self._create_new_application(offer, evaluation, timestamp)

        eligible, _ = self.should_reapply(
            existing_record=existing,
            new_portal=offer.portal,
            current_time_iso=timestamp,
            cooldown_days=cooldown_days,
        )

        if not eligible:
            return existing, False

        return self._update_existing_reapplication(existing, offer, evaluation, timestamp)

    def _create_new_application(
        self,
        offer: JobOffer,
        evaluation: MatchEvaluation,
        timestamp: str,
    ) -> tuple[ApplicationRecord, bool]:
        company_norm = normalize_company_name(offer.company)
        title_norm = normalize_job_title(offer.title)
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO applications (
                    dedup_key, title, company, company_norm, title_norm,
                    location, modality, description, match_score, times_applied, status,
                    first_applied_at, last_applied_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                ON CONFLICT(dedup_key) DO UPDATE SET
                    times_applied = applications.times_applied + 1,
                    last_applied_at = excluded.last_applied_at,
                    updated_at = excluded.updated_at,
                    status = CASE
                        WHEN applications.status = 'Requiere Seguimiento' THEN 'Enviado'
                        ELSE applications.status
                    END
                """,
                (
                    evaluation.dedup_key,
                    offer.title,
                    offer.company,
                    company_norm,
                    title_norm,
                    offer.location,
                    offer.modality.value,
                    offer.description,
                    evaluation.match_score,
                    ApplicationStatus.APPLIED.value,
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            if cursor.lastrowid:
                app_id = int(cursor.lastrowid)
                attempt_num = 1
            else:
                row = self._conn.execute(
                    "SELECT id, times_applied FROM applications WHERE dedup_key = ?",
                    (evaluation.dedup_key,),
                ).fetchone()
                if not row:
                    raise RuntimeError("Failed to obtain id after inserting application.")
                app_id = int(row["id"])
                attempt_num = int(row["times_applied"])

            self._conn.execute(
                """
                INSERT INTO application_submissions (
                    application_id, attempt_number, portal, external_id, canonical_url, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (app_id, attempt_num, offer.portal.value, offer.external_id, evaluation.canonical_url, timestamp),
            )

            if evaluation.keywords:
                self._conn.executemany(
                    """
                    INSERT OR IGNORE INTO application_keywords (application_id, keyword, is_matched, weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (app_id, kw.keyword, 1 if kw.is_matched else 0, int(kw.weight))
                        for kw in evaluation.keywords
                    ],
                )

        record = self.find_by_id(app_id)
        if not record:
            raise RuntimeError("Failed to retrieve created application record.")
        return record, True

    def _update_existing_reapplication(
        self,
        existing: ApplicationRecord,
        offer: JobOffer,
        evaluation: MatchEvaluation,
        timestamp: str,
    ) -> tuple[ApplicationRecord, bool]:
        new_times_applied = existing.times_applied + 1
        with self._conn:
            self._conn.execute(
                """
                UPDATE applications
                SET times_applied = ?,
                    last_applied_at = ?,
                    updated_at = ?,
                    status = CASE
                        WHEN status = 'Requiere Seguimiento' THEN 'Enviado'
                        ELSE status
                    END
                WHERE id = ?
                """,
                (new_times_applied, timestamp, timestamp, existing.id),
            )

            self._conn.execute(
                """
                INSERT INTO application_submissions (
                    application_id, attempt_number, portal, external_id, canonical_url, applied_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    existing.id,
                    new_times_applied,
                    offer.portal.value,
                    offer.external_id,
                    evaluation.canonical_url,
                    timestamp,
                ),
            )

            if evaluation.keywords:
                self._conn.executemany(
                    """
                    INSERT OR IGNORE INTO application_keywords (application_id, keyword, is_matched, weight)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (existing.id, kw.keyword, 1 if kw.is_matched else 0, int(kw.weight))
                        for kw in evaluation.keywords
                    ],
                )

        updated_record = self.find_by_id(existing.id)
        if not updated_record:
            raise RuntimeError("Failed to retrieve updated application record.")
        return updated_record, True

    def update_status(self, application_id: int, status: ApplicationStatus) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE applications
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, _get_utc_now_iso(), application_id),
            )
            return cursor.rowcount > 0

    def update_notion_page_id(self, application_id: int, notion_page_id: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE applications
                SET notion_page_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (notion_page_id, _get_utc_now_iso(), application_id),
            )
            return cursor.rowcount > 0

    def get_keyword_stats(self) -> list[tuple[str, int, int]]:
        cursor = self._conn.execute(
            """
            SELECT keyword,
                   COUNT(application_id) AS total_jobs,
                   SUM(is_matched) AS matched_jobs
            FROM application_keywords
            GROUP BY keyword
            ORDER BY total_jobs DESC, keyword ASC
            """
        )
        return [(str(row["keyword"]), int(row["total_jobs"]), int(row["matched_jobs"])) for row in cursor.fetchall()]

    def _hydrate_application(self, row: sqlite3.Row) -> ApplicationRecord:
        app_id = int(row["id"])
        sub_cursor = self._conn.execute(
            "SELECT * FROM application_submissions WHERE application_id = ? ORDER BY attempt_number ASC",
            (app_id,),
        )
        submissions = tuple(
            SubmissionAttempt(
                attempt_number=int(s["attempt_number"]),
                portal=PortalName(s["portal"]),
                canonical_url=str(s["canonical_url"]),
                applied_at=str(s["applied_at"]),
                external_id=str(s["external_id"]) if s["external_id"] else None,
            )
            for s in sub_cursor.fetchall()
        )

        kw_cursor = self._conn.execute(
            "SELECT * FROM application_keywords WHERE application_id = ? ORDER BY weight DESC, keyword ASC",
            (app_id,),
        )
        keywords = tuple(
            KeywordMatch(
                keyword=str(k["keyword"]),
                is_matched=bool(k["is_matched"]),
                weight=KeywordWeight(int(k["weight"])),
            )
            for k in kw_cursor.fetchall()
        )

        return ApplicationRecord(
            id=app_id,
            dedup_key=str(row["dedup_key"]),
            title=str(row["title"]),
            company=str(row["company"]),
            location=str(row["location"]),
            modality=WorkModality(row["modality"]),
            description=str(row["description"]),
            match_score=int(row["match_score"]),
            times_applied=int(row["times_applied"]),
            status=ApplicationStatus(row["status"]),
            first_applied_at=str(row["first_applied_at"]) if row["first_applied_at"] else None,
            last_applied_at=str(row["last_applied_at"]) if row["last_applied_at"] else None,
            notion_page_id=str(row["notion_page_id"]) if row["notion_page_id"] else None,
            submissions=submissions,
            keywords=keywords,
        )
