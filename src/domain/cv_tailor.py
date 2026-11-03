"""Adaptación determinista de la hoja de vida base (Markdown) a una vacante.

Solo reordena y resalta información que ya existe en `config/cv_base.md`; nunca agrega
tecnologías, años ni experiencia. El resumen reescrito por IA se valida contra el CV base.
"""

from dataclasses import dataclass, field, replace
import re

from src.domain.matcher import keyword_in_text

SKILLS_SECTION_PATTERN = re.compile(r"skill|habilidad|tecnolog|stack|competenc", re.IGNORECASE)
RANKED_SECTION_PATTERN = re.compile(r"project|proyecto|experien", re.IGNORECASE)
SUMMARY_SECTION_PATTERN = re.compile(r"summary|perfil|resumen|about|sobre\s+m|profile", re.IGNORECASE)
SKILL_LINE_PATTERN = re.compile(r"^(\s*[-*]\s*\*\*[^*]+\*\*\s*)(.+)$")
NUMBER_PATTERN = re.compile(r"\d+")

SUMMARY_MIN_CHARS = 40
SUMMARY_MAX_CHARS = 900


@dataclass(frozen=True, slots=True)
class CvSubsection:
    title: str
    lines: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CvSection:
    title: str
    lines: tuple[str, ...] = ()
    subsections: tuple[CvSubsection, ...] = ()


@dataclass(frozen=True, slots=True)
class CvDocument:
    header: tuple[str, ...] = ()
    sections: tuple[CvSection, ...] = field(default_factory=tuple)

    def find_section(self, pattern: re.Pattern[str]) -> CvSection | None:
        return next((s for s in self.sections if pattern.search(s.title)), None)


def _is_separator(line: str) -> bool:
    return line.strip() in {"---", "***", "___"}


def parse_cv_markdown(markdown: str) -> CvDocument:
    header: list[str] = []
    sections: list[CvSection] = []
    section_title: str | None = None
    section_lines: list[str] = []
    subsections: list[CvSubsection] = []
    sub_title: str | None = None
    sub_lines: list[str] = []

    def close_subsection() -> None:
        nonlocal sub_title, sub_lines
        if sub_title is not None:
            subsections.append(CvSubsection(sub_title, tuple(_trim_blank(sub_lines))))
        sub_title, sub_lines = None, []

    def close_section() -> None:
        nonlocal section_title, section_lines, subsections
        close_subsection()
        if section_title is not None:
            sections.append(CvSection(section_title, tuple(_trim_blank(section_lines)), tuple(subsections)))
        section_title, section_lines, subsections = None, [], []

    for line in markdown.splitlines():
        if _is_separator(line):
            continue
        if line.startswith("## "):
            close_section()
            section_title = line[3:].strip()
        elif line.startswith("### ") and section_title is not None:
            close_subsection()
            sub_title = line[4:].strip()
        elif sub_title is not None:
            sub_lines.append(line)
        elif section_title is not None:
            section_lines.append(line)
        else:
            header.append(line)
    close_section()

    return CvDocument(header=tuple(_trim_blank(header)), sections=tuple(sections))


def _trim_blank(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def cv_to_markdown(doc: CvDocument) -> str:
    out: list[str] = list(doc.header)
    for section in doc.sections:
        out += ["", f"## {section.title}"]
        if section.lines:
            out += list(section.lines)
        for sub in section.subsections:
            out += ["", f"### {sub.title}", *sub.lines]
    return "\n".join(out).strip() + "\n"


def _keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if keyword_in_text(text, kw))


def _reorder_skill_line(line: str, keywords: list[str]) -> str:
    match = SKILL_LINE_PATTERN.match(line)
    if not match:
        return line
    prefix, items_text = match.groups()
    items = [item.strip() for item in items_text.split(",") if item.strip()]
    # sorted() es estable: las habilidades pedidas suben y el resto conserva su orden original.
    ordered = sorted(items, key=lambda item: _keyword_hits(item, keywords) == 0)
    return prefix + ", ".join(ordered)


def _reorder_skills(section: CvSection, keywords: list[str]) -> CvSection:
    lines = [_reorder_skill_line(line, keywords) for line in section.lines]
    skill_lines = [line for line in lines if SKILL_LINE_PATTERN.match(line)]
    if len(skill_lines) == len([line for line in lines if line.strip()]):
        lines = sorted(skill_lines, key=lambda line: -_keyword_hits(line, keywords))
    return replace(section, lines=tuple(lines))


MISC_SUBSECTION_PATTERN = re.compile(r"^(?:otros|otras|other|others|more)\b", re.IGNORECASE)


def _rank_subsections(section: CvSection, keywords: list[str]) -> CvSection:
    def score(sub: CvSubsection) -> tuple[bool, int]:
        # Un bloque tipo "Otros proyectos" siempre va al final, aunque tenga coincidencias.
        is_misc = bool(MISC_SUBSECTION_PATTERN.search(sub.title))
        return is_misc, -_keyword_hits(" ".join((sub.title, *sub.lines)), keywords)

    return replace(section, subsections=tuple(sorted(section.subsections, key=score)))


def tailor_cv_document(doc: CvDocument, offer_keywords: list[str], summary: str | None = None) -> CvDocument:
    """Prioriza habilidades y proyectos según las keywords de la oferta y, si se da, reemplaza el resumen."""
    sections: list[CvSection] = []
    for section in doc.sections:
        if SKILLS_SECTION_PATTERN.search(section.title):
            section = _reorder_skills(section, offer_keywords)
        elif RANKED_SECTION_PATTERN.search(section.title) and section.subsections:
            section = _rank_subsections(section, offer_keywords)
        elif summary and SUMMARY_SECTION_PATTERN.search(section.title):
            section = replace(section, lines=(summary.strip(),))
        sections.append(section)
    return replace(doc, sections=tuple(sections))


def section_text(section: CvSection | None) -> str:
    if section is None:
        return ""
    return "\n".join(section.lines).strip()


def validate_tailored_summary(summary: str, cv_markdown: str, known_keywords: list[str]) -> str | None:
    """Devuelve el motivo de rechazo del resumen generado, o None si es seguro usarlo.

    Rechaza tecnologías o cifras que no aparezcan en el CV base, para que la IA no invente experiencia.
    """
    text = summary.strip()
    if not SUMMARY_MIN_CHARS <= len(text) <= SUMMARY_MAX_CHARS:
        return f"longitud fuera de rango ({len(text)} caracteres)"
    if text.startswith("#") or "\n#" in text:
        return "contiene encabezados Markdown"

    for kw in known_keywords:
        if keyword_in_text(text, kw) and not keyword_in_text(cv_markdown, kw):
            return f"menciona '{kw}', que no está en el CV base"

    cv_numbers = set(NUMBER_PATTERN.findall(cv_markdown))
    for number in NUMBER_PATTERN.findall(text):
        if number not in cv_numbers:
            return f"incluye la cifra '{number}', que no está en el CV base"

    return None
