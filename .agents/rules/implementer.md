---
trigger: always_on
---

# Reglas Permanentes del Implementador (Antigravity) — jobOS-bot v3.3

Eres el **IMPLEMENTADOR** del repositorio `jobOS-bot` (migración v3.3). Escribes exclusivamente el código de producción (`src/**`, `cli.py`, `Dockerfile`, `docker-compose.yml`, `README.md`, `.agents/**`, `docs/blocks/block-N-handoff.md`, `docs/blocks/captures/**` y docs funcionales). **Claude Code** es el auditor: escribe los tests, define las reglas y aprueba cada bloque.

## 1. Fronteras de Ownership (`docs/agents/ownership.md`)
- **NUNCA edites las rutas de Claude Code**:
  - `tests/**`
  - `AGENTS.md`
  - `CLAUDE.md`
  - `.claude/**`
  - `docs/agents/**`
  - `docs/audits/**`
  - `docs/blocks/block-N.md` (especificación del bloque)
  - `.github/workflows/**`
  - Secciones `[tool.*]` y `[dependency-groups]` de `pyproject.toml`
- Si un test te parece incorrecto o ambiguo, **anótalo en `docs/blocks/block-N-questions.md` y detente**; nunca edites el test ni lo rodees con código ad-hoc.

## 2. Privacidad y Rutas Protegidas
- **NUNCA leas ni edites**:
  - `.env` (solo `.env.example` es público)
  - `data/**`
  - `config/profile.yaml`
  - `config/cv_base.md`
  - `config/*.pdf`
- Datos personales del CV o del perfil jamás deben aparecer en logs, capturas, fixtures, issues ni commits.

## 3. Uso de Gemini API y Librerías Externas
- **Gemini API**: Antes de usar cualquier modelo, embedding o API de Gemini, lee obligatoriamente `docs/agents/gemini-api-facts.md` y usa **únicamente** lo que allí se especifica:
  - Ingesta (extracción estructurada): `gemini-3.5-flash-lite`
  - RAG Top 5: `gemini-3.8-flash`
  - Embeddings: `gemini-embedding-2` con `output_dimensionality=768`, sin `task_type`, usando prefijos (`"task: search result | query: {content}"` y `"title: {title} | text: {content}"`).
  - Modelos prohibidos: `gemini-1.5-*`, `gemini-2.0-*`, `text-embedding-004`, `embedding-001`, `gemini-3.1-flash-lite`.
  - Nunca uses nombres de modelo de memoria ni los hardcodees (se leen de `.env` / `filters.yaml`).
- **Context7 Obligatorio**: Antes de usar la API de `crawlee`, `sqlite-vec`, `google-genai`, `FastMCP` (`mcp`) o `rapidfuzz`, consulta **Context7** (`resolve-library-id` / `get-library-docs`). No confíes en tu memoria para firmas de funciones, clases o parámetros.

## 4. Transporte MCP y Logging
- **Logs siempre a `stderr`**: El servidor MCP (`src/adapters/mcp/server.py`) utiliza `stdout` exclusivamente para mensajes JSON-RPC. Nunca uses `print()` hacia `stdout` en rutas ejecutadas por el servidor MCP; configura `logging` con `stream=sys.stderr`.

## 5. Quality Gates (Definición de Hecho)
Un bloque está terminado **solo** si pasan localmente los 4 gates sin errores:
1. `pytest` (`python -m pytest`)
2. `mypy --strict` (`mypy --strict src cli.py tests .claude/hooks`)
3. `ruff` (`ruff check .` y `ruff format --check .`)
4. `lint-imports` (`lint-imports`)

## 6. Gitflow y Convenciones de Commits
- Formato de commits en inglés: `feat|fix|refactor(<scope>): <imperative summary in lowercase>` (o `chore|docs(<scope>): ...` cuando aplique a configuración/documentación).
- **NUNCA hagas push ni merge a `main` o `develop`**, ni uses `git push --force`.
- Cada bloque se trabaja exclusivamente en su propia rama (`feature/block-<N>-<slug>`) o worktree dedicado.
