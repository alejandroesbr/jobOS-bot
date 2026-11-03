from html import escape
from pathlib import Path
import re
from types import TracebackType

from playwright.sync_api import Browser, Playwright, sync_playwright

from src.domain.cv_tailor import CvDocument

BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BULLET_PATTERN = re.compile(r"^\s*[-*]\s+(.*)$")

# Plantilla de una sola columna, sin tablas ni imágenes, para que los ATS lean el texto en orden.
CV_STYLES = """
@page { size: Letter; margin: 14mm 16mm; }
* { box-sizing: border-box; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.4; color: #1a1a1a; margin: 0; }
h1 { font-size: 20pt; margin: 0 0 2pt; }
.headline { font-size: 11.5pt; font-weight: bold; color: #333; margin: 0 0 4pt; }
.contact { font-size: 9.5pt; color: #333; margin: 0 0 10pt; }
.contact a { color: #1a1a1a; text-decoration: none; }
h2 { font-size: 11.5pt; text-transform: uppercase; letter-spacing: 0.5pt; border-bottom: 1px solid #999;
     padding-bottom: 2pt; margin: 12pt 0 5pt; }
h3 { font-size: 10.5pt; margin: 7pt 0 1pt; }
p { margin: 0 0 4pt; }
ul { margin: 2pt 0 4pt; padding-left: 14pt; }
li { margin: 0 0 2pt; }
a { color: #1a1a1a; }
"""


def render_inline(text: str) -> str:
    html = escape(text, quote=True)
    html = LINK_PATTERN.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', html)
    html = BOLD_PATTERN.sub(r"<strong>\1</strong>", html)
    return ITALIC_PATTERN.sub(r"<em>\1</em>", html)


def _render_block(lines: tuple[str, ...]) -> str:
    out: list[str] = []
    in_list = False
    for line in lines:
        bullet = BULLET_PATTERN.match(line)
        if bullet:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{render_inline(bullet.group(1))}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.strip():
            out.append(f"<p>{render_inline(line.strip())}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _render_header(header: tuple[str, ...]) -> str:
    name = ""
    headline: list[str] = []
    contact: list[str] = []
    for line in header:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not name:
            name = stripped[2:].strip()
            continue
        bullet = BULLET_PATTERN.match(stripped)
        if bullet:
            contact.append(render_inline(bullet.group(1)))
        else:
            headline.append(render_inline(stripped))

    parts = [f"<h1>{escape(name)}</h1>"] if name else []
    if headline:
        parts.append(f'<p class="headline">{" ".join(headline)}</p>')
    if contact:
        parts.append(f'<p class="contact">{" &nbsp;·&nbsp; ".join(contact)}</p>')
    return "\n".join(parts)


def render_cv_html(doc: CvDocument, lang: str = "es") -> str:
    body: list[str] = [_render_header(doc.header)]
    for section in doc.sections:
        body.append(f"<h2>{render_inline(section.title)}</h2>")
        body.append(_render_block(section.lines))
        for sub in section.subsections:
            body.append(f"<h3>{render_inline(sub.title)}</h3>")
            body.append(_render_block(sub.lines))
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        f"<style>{CV_STYLES}</style></head><body>\n" + "\n".join(b for b in body if b) + "\n</body></html>"
    )


class PlaywrightPdfRenderer:
    """Convierte HTML a PDF con Chromium headless. Un solo navegador para todo el lote (single-thread)."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> "PlaywrightPdfRenderer":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def render(self, html: str, out_path: Path) -> None:
        if self._browser is None:
            raise RuntimeError("PlaywrightPdfRenderer debe usarse dentro de un bloque 'with'.")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page = self._browser.new_page()
        try:
            page.set_content(html, wait_until="load")
            page.pdf(path=str(out_path), format="Letter", print_background=True, prefer_css_page_size=True)
        finally:
            page.close()
