from dataclasses import dataclass
import re
from typing import Protocol

from rapidfuzz import fuzz, process

from src.domain.models import (
    AnswerSource,
    CandidateProfile,
    PortalName,
    QuestionCategory,
    QuestionMatch,
)
from src.domain.text_normalizer import normalize_form_question

SALARY_INTENT_PATTERN = re.compile(
    r"\b(?:salario|sueldo|aspiracion|expectativa\s+salarial|remuneracion|pretension|salary|compensation|pay|rate)\b",
    re.IGNORECASE,
)

USD_CURRENCY_PATTERN = re.compile(
    r"\b(?:usd|us\$|dolar|dolares|dollar|dollars)\b",
    re.IGNORECASE,
)

COP_CURRENCY_PATTERN = re.compile(
    r"\b(?:cop|pesos?|colombia|millon|millones|colombianos?)\b",
    re.IGNORECASE,
)

EXPERIENCE_INTENT_PATTERN = re.compile(
    r"\b(?:experiencia|anos?|anios?|experience|years|cuanto\s+tiempo|how\s+long)\b",
    re.IGNORECASE,
)

KNOWN_TECH_ALIASES: dict[str, str] = {
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "nestjs": "NestJS",
    "nest": "NestJS",
    "nest.js": "NestJS",
    "nextjs": "Next.js",
    "next": "Next.js",
    "next.js": "Next.js",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "sql": "SQL",
    "git": "Git",
    "docker": "Docker",
    "aws": "AWS",
    "redis": "Redis",
    "graphql": "GraphQL",
    "tailwind": "Tailwind",
    "python": "Python",
    "express": "Express",
    "prisma": "Prisma",
    "typeorm": "TypeORM",
    "rest api": "REST API",
    "html": "HTML",
    "css": "CSS",
    "jest": "Jest",
    "linux": "Linux",
    "ci/cd": "CI/CD",
}


class QARepositoryPort(Protocol):
    def upsert_qa_memory(
        self,
        question_norm: str,
        raw_example: str,
        answer: str,
        category: QuestionCategory = ...,
        source: AnswerSource = ...,
    ) -> None: ...

    def get_all_qa_memory(self) -> list[tuple[str, str, str, str]]: ...


@dataclass(frozen=True, slots=True)
class _InternalQAEntry:
    question_norm: str
    raw_example: str
    answer: str
    category: QuestionCategory
    source: AnswerSource
    target_tech: str | None = None


class QuestionAnswerEngine:
    def __init__(
        self,
        profile: CandidateProfile | None = None,
        repository: QARepositoryPort | None = None,
        similarity_threshold: float = 85.0,
    ) -> None:
        self.profile = profile
        self.repository = repository
        self.similarity_threshold = similarity_threshold
        self._entries: dict[str, _InternalQAEntry] = {}

        if self.profile is not None:
            self.seed_from_profile(self.profile)

        if self.repository is not None:
            self.load_from_repository()

    def seed_from_profile(self, profile: CandidateProfile) -> None:
        self.profile = profile
        # 1. Personal Identity & Links
        self._add_seed("nombre completo", profile.personal.full_name, QuestionCategory.GENERAL)
        self._add_seed("full name", profile.personal.full_name, QuestionCategory.GENERAL)
        self._add_seed("correo electronico", profile.personal.email, QuestionCategory.GENERAL)
        self._add_seed("email address", profile.personal.email, QuestionCategory.GENERAL)
        self._add_seed("numero de telefono celular", profile.personal.phone, QuestionCategory.GENERAL)
        self._add_seed("phone number", profile.personal.phone, QuestionCategory.GENERAL)
        self._add_seed("perfil de linkedin", profile.personal.linkedin_url, QuestionCategory.GENERAL)
        self._add_seed("linkedin profile url", profile.personal.linkedin_url, QuestionCategory.GENERAL)
        self._add_seed("perfil de github", profile.personal.github_url, QuestionCategory.GENERAL)
        self._add_seed("github profile url", profile.personal.github_url, QuestionCategory.GENERAL)
        self._add_seed("portafolio personal", profile.personal.portfolio_url, QuestionCategory.GENERAL)
        self._add_seed("portfolio url", profile.personal.portfolio_url, QuestionCategory.GENERAL)
        self._add_seed("ciudad de residencia", profile.personal.city, QuestionCategory.LOCATION)
        self._add_seed("current city location", profile.personal.city, QuestionCategory.LOCATION)

        # 2. Residency, Work Permits & Availability
        self._add_seed("resides en barranquilla colombia", "Sí", QuestionCategory.LOCATION)
        self._add_seed("resides en colombia", "Sí", QuestionCategory.LOCATION)
        self._add_seed("do you live in colombia", "Yes", QuestionCategory.LOCATION)
        self._add_seed("cuentas con permiso legal para trabajar en colombia", "Sí", QuestionCategory.GENERAL)
        self._add_seed("permiso de trabajo en colombia", "Sí", QuestionCategory.GENERAL)
        self._add_seed("legal work authorization in colombia", "Yes", QuestionCategory.GENERAL)
        self._add_seed("requieres patrocinio de visa", "No", QuestionCategory.GENERAL)
        self._add_seed("requieres patrocinio de visa para trabajar remoto", "No", QuestionCategory.GENERAL)
        self._add_seed("patrocinio de visa", "No", QuestionCategory.GENERAL)
        self._add_seed("do you require visa sponsorship", "No", QuestionCategory.GENERAL)
        self._add_seed("visa sponsorship", "No", QuestionCategory.GENERAL)
        self._add_seed("disponibilidad para trabajar remoto", "Sí", QuestionCategory.GENERAL)
        self._add_seed("willing to work remotely", "Yes", QuestionCategory.GENERAL)
        self._add_seed("disponibilidad para trabajar hibrido", "Sí", QuestionCategory.GENERAL)
        self._add_seed("willing to work hybrid", "Yes", QuestionCategory.GENERAL)
        self._add_seed("disponibilidad de incorporacion", profile.preferences.notice_period, QuestionCategory.GENERAL)
        self._add_seed("tiempo de preaviso", profile.preferences.notice_period, QuestionCategory.GENERAL)
        self._add_seed("notice period", profile.preferences.notice_period, QuestionCategory.GENERAL)
        self._add_seed("notice period availability", profile.preferences.notice_period, QuestionCategory.GENERAL)
        self._add_seed("nivel de ingles", profile.preferences.english_level, QuestionCategory.GENERAL)
        self._add_seed("english level", profile.preferences.english_level, QuestionCategory.GENERAL)
        self._add_seed("english proficiency level", profile.preferences.english_level, QuestionCategory.GENERAL)

        # 3. Salary in COP
        cop_val = str(profile.salary.cop_monthly)
        self._add_seed("expectativa salarial mensual en pesos colombianos", cop_val, QuestionCategory.SALARY_COP)
        self._add_seed("expectativa salarial mensual en cop", cop_val, QuestionCategory.SALARY_COP)
        self._add_seed("cual es tu salario esperado en pesos colombianos", cop_val, QuestionCategory.SALARY_COP)
        self._add_seed("salario esperado cop", cop_val, QuestionCategory.SALARY_COP)
        self._add_seed("aspiracion salarial cop", cop_val, QuestionCategory.SALARY_COP)
        self._add_seed("aspiracion salarial en pesos colombianos", cop_val, QuestionCategory.SALARY_COP)

        # 4. Salary in USD
        usd_val = str(profile.salary.usd_monthly)
        self._add_seed("expectativa salarial mensual en dolares", usd_val, QuestionCategory.SALARY_USD)
        self._add_seed("expectativa salarial mensual en usd", usd_val, QuestionCategory.SALARY_USD)
        self._add_seed("salary expectation in usd", usd_val, QuestionCategory.SALARY_USD)
        self._add_seed("expected monthly salary in usd", usd_val, QuestionCategory.SALARY_USD)
        self._add_seed("desired salary in usd", usd_val, QuestionCategory.SALARY_USD)
        self._add_seed("monthly salary expectation in usd", usd_val, QuestionCategory.SALARY_USD)

        # 5. Technology Experience Years
        for tech, years in profile.experience_years.items():
            tech_clean = tech.lower()
            years_str = str(years)
            self._add_seed(f"cuantos anos de experiencia tienes con {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"cuantos anos de experiencia tienes en {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"anos de experiencia con {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"experiencia con {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"experiencia en {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"years of experience with {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"years of experience in {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)
            self._add_seed(f"experience with {tech_clean}", years_str, QuestionCategory.EXPERIENCE, tech=tech)

    def _add_seed(
        self,
        raw_question: str,
        answer: str,
        category: QuestionCategory,
        tech: str | None = None,
    ) -> None:
        norm = normalize_form_question(raw_question)
        if norm:
            self._entries[norm] = _InternalQAEntry(
                question_norm=norm,
                raw_example=raw_question,
                answer=answer,
                category=category,
                source=AnswerSource.PROFILE_SEED,
                target_tech=tech,
            )

    def persist_seeds(self) -> int:
        if self.repository is None:
            return 0
        count = 0
        for entry in self._entries.values():
            if entry.source == AnswerSource.PROFILE_SEED:
                self.repository.upsert_qa_memory(
                    question_norm=entry.question_norm,
                    raw_example=entry.raw_example,
                    answer=entry.answer,
                    category=entry.category,
                    source=entry.source,
                )
                count += 1
        return count

    def load_from_repository(self) -> int:
        if self.repository is None:
            return 0
        items = self.repository.get_all_qa_memory()
        loaded = 0
        for question_norm, raw_example, answer, category_str in items:
            cat = (
                QuestionCategory(category_str)
                if category_str in QuestionCategory._value2member_map_
                else QuestionCategory.GENERAL
            )
            # Database records have priority if user_confirmed, or hydrate cache
            self._entries[question_norm] = _InternalQAEntry(
                question_norm=question_norm,
                raw_example=raw_example,
                answer=answer,
                category=cat,
                source=AnswerSource.USER_CONFIRMED,
            )
            loaded += 1
        return loaded

    def add_qa_entry(
        self,
        raw_question: str,
        answer: str,
        category: QuestionCategory = QuestionCategory.GENERAL,
        source: AnswerSource = AnswerSource.USER_CONFIRMED,
    ) -> QuestionMatch:
        norm = normalize_form_question(raw_question)
        if not norm:
            raise ValueError("Question cannot be empty after normalization.")

        entry = _InternalQAEntry(
            question_norm=norm,
            raw_example=raw_question,
            answer=answer,
            category=category,
            source=source,
        )
        self._entries[norm] = entry

        if self.repository is not None:
            self.repository.upsert_qa_memory(
                question_norm=norm,
                raw_example=raw_question,
                answer=answer,
                category=category,
                source=source,
            )

        return QuestionMatch(
            question_norm=norm,
            answer=answer,
            similarity_score=100.0,
            category=category,
            source=source,
            is_confident_match=True,
        )

    def find_answer(
        self,
        question: str,
        portal: PortalName | None = None,
        is_numeric_input: bool = False,
    ) -> QuestionMatch:
        query_norm = normalize_form_question(question)
        if not query_norm:
            return QuestionMatch(
                question_norm="",
                answer="",
                similarity_score=0.0,
                category=QuestionCategory.GENERAL,
                source=AnswerSource.PROFILE_SEED,
                is_confident_match=False,
            )

        # 1. Exact match in memory (fast-path O(1))
        if query_norm in self._entries:
            entry = self._entries[query_norm]
            formatted = self._format_answer(entry.answer, entry.category, is_numeric_input)
            return QuestionMatch(
                question_norm=entry.question_norm,
                answer=formatted,
                similarity_score=100.0,
                category=entry.category,
                source=entry.source,
                is_confident_match=True,
            )

        # 2. ATS Knock-out Rules: Salary Intent & Currency
        if SALARY_INTENT_PATTERN.search(query_norm):
            return self._handle_salary_query(query_norm, portal, is_numeric_input)

        # 3. ATS Knock-out Rules: Experience Years Intent
        if EXPERIENCE_INTENT_PATTERN.search(query_norm):
            match = self._handle_experience_query(query_norm, is_numeric_input)
            if match is not None:
                return match

        # 4. RapidFuzz similarity across all registered questions
        return self._fuzzy_match_general(query_norm, is_numeric_input)

    def _handle_salary_query(
        self,
        query_norm: str,
        portal: PortalName | None,
        is_numeric_input: bool,
    ) -> QuestionMatch:
        currency = self._detect_currency(query_norm, portal)
        candidate_keys = [
            k for k, entry in self._entries.items() if entry.category == currency
        ]

        fuzzy_score = 0.0
        best_norm = query_norm
        source = AnswerSource.PROFILE_SEED

        if candidate_keys:
            best_match = process.extractOne(query_norm, candidate_keys, scorer=fuzz.token_set_ratio)
            if best_match:
                best_norm, fuzzy_score, _ = best_match
                source = self._entries[best_norm].source

        # Always build the right salary from candidate profile
        if self.profile is not None:
            if currency == QuestionCategory.SALARY_USD:
                ans = (
                    str(self.profile.salary.usd_monthly)
                    if is_numeric_input
                    else f"${self.profile.salary.usd_monthly} USD mensual"
                )
            else:
                ans = (
                    str(self.profile.salary.cop_monthly)
                    if is_numeric_input
                    else f"${self.profile.salary.cop_monthly:,} COP mensual"
                )
        else:
            ans = self._entries[best_norm].answer if best_norm in self._entries else ""

        # Confident match if currency was clearly detected or fuzzy score >= threshold
        score = max(float(fuzzy_score), 90.0)
        return QuestionMatch(
            question_norm=best_norm,
            answer=ans,
            similarity_score=score,
            category=currency,
            source=source,
            is_confident_match=True,
        )

    def _handle_experience_query(
        self,
        query_norm: str,
        is_numeric_input: bool,
    ) -> QuestionMatch | None:
        tech = self._detect_technology(query_norm)
        if not tech:
            return None

        # Filter candidate keys for the same target technology
        candidate_keys = [
            k
            for k, entry in self._entries.items()
            if entry.category == QuestionCategory.EXPERIENCE and entry.target_tech == tech
        ]

        fuzzy_score = 0.0
        best_norm = query_norm
        source = AnswerSource.PROFILE_SEED

        if candidate_keys:
            best_match = process.extractOne(query_norm, candidate_keys, scorer=fuzz.token_set_ratio)
            if best_match:
                best_norm, fuzzy_score, _ = best_match
                source = self._entries[best_norm].source

        years = self.profile.get_experience_years(tech) if self.profile else 1
        if is_numeric_input:
            ans = str(years)
        else:
            ans = f"{years} año" if years == 1 else f"{years} años"

        score = max(float(fuzzy_score), 90.0)
        return QuestionMatch(
            question_norm=best_norm,
            answer=ans,
            similarity_score=score,
            category=QuestionCategory.EXPERIENCE,
            source=source,
            is_confident_match=True,
        )

    def _fuzzy_match_general(
        self,
        query_norm: str,
        is_numeric_input: bool,
    ) -> QuestionMatch:
        if not self._entries:
            return QuestionMatch(
                question_norm=query_norm,
                answer="",
                similarity_score=0.0,
                category=QuestionCategory.GENERAL,
                source=AnswerSource.PROFILE_SEED,
                is_confident_match=False,
            )

        best_match = process.extractOne(
            query_norm,
            self._entries.keys(),
            scorer=fuzz.token_set_ratio,
        )

        if not best_match:
            return QuestionMatch(
                question_norm=query_norm,
                answer="",
                similarity_score=0.0,
                category=QuestionCategory.GENERAL,
                source=AnswerSource.PROFILE_SEED,
                is_confident_match=False,
            )

        matched_key, score, _ = best_match
        entry = self._entries[matched_key]
        score_val = float(score)

        if score_val >= self.similarity_threshold:
            formatted = self._format_answer(entry.answer, entry.category, is_numeric_input)
            return QuestionMatch(
                question_norm=entry.question_norm,
                answer=formatted,
                similarity_score=score_val,
                category=entry.category,
                source=entry.source,
                is_confident_match=True,
            )

        return QuestionMatch(
            question_norm=entry.question_norm,
            answer="",
            similarity_score=score_val,
            category=entry.category,
            source=entry.source,
            is_confident_match=False,
        )

    def _detect_currency(
        self,
        query_text: str,
        portal: PortalName | None = None,
    ) -> QuestionCategory:
        if USD_CURRENCY_PATTERN.search(query_text):
            return QuestionCategory.SALARY_USD
        if COP_CURRENCY_PATTERN.search(query_text):
            return QuestionCategory.SALARY_COP
        if portal == PortalName.GETONBRD:
            return QuestionCategory.SALARY_USD
        if portal in {PortalName.COMPUTRABAJO, PortalName.ELEMPLEO}:
            return QuestionCategory.SALARY_COP
        return QuestionCategory.SALARY_COP

    def _detect_technology(self, query_text: str) -> str | None:
        norm = query_text.lower()
        # 1. Profile technologies (prefer longer names first)
        if self.profile:
            for tech in sorted(self.profile.experience_years.keys(), key=len, reverse=True):
                pattern = rf"\b{re.escape(tech.lower())}\b"
                if re.search(pattern, norm):
                    return tech

        # 2. Known aliases
        for alias, canonical in sorted(KNOWN_TECH_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, norm):
                return canonical

        # 3. Trailing word after prepositions 'con', 'en', 'with', 'in'
        match = re.search(r"\b(?:con|en|with|in)\s+([a-zA-Z0-9#+.]+)", query_text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            excluded = {"anos", "anios", "years", "el", "la", "los", "las", "tu", "su", "un", "una", "este", "esta"}
            if candidate.lower() not in excluded:
                return candidate
        return None

    def _format_answer(
        self,
        raw_answer: str,
        category: QuestionCategory,
        is_numeric_input: bool,
    ) -> str:
        if is_numeric_input:
            digits = re.sub(r"\D", "", raw_answer)
            return digits if digits else raw_answer

        if category == QuestionCategory.EXPERIENCE and raw_answer.isdigit():
            return f"{raw_answer} año" if raw_answer == "1" else f"{raw_answer} años"

        if category == QuestionCategory.SALARY_COP and raw_answer.isdigit():
            return f"${int(raw_answer):,} COP mensual"

        if category == QuestionCategory.SALARY_USD and raw_answer.isdigit():
            return f"${raw_answer} USD mensual"

        return raw_answer
