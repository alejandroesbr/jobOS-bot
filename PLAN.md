# jobOS-bot — Plan Maestro de Implementación y Pruebas

**Goal:** Construir `jobOS-bot` en **100% Python 3.11+** bajo **Lightweight Hexagonal Architecture (Ports & Adapters)** aplicando estrictamente **DRY, KISS, YAGNI y Clean Code (con tipado estricto estilo TypeScript)**, escaneo multi-portal _single-thread_, postulación por rango de `%` (`>= 40%`), re-postulación con contador único (`times_applied`) y ejecución Cloud a costo **$0/mes**.
**Done when:** Los 6 bloques están implementados, verificados uno por uno con `pytest` y pruebas de CLI en vivo (`scan`, `assist`, `stats`, `tailor`, `prep`, `sync`, `export`), sin código muerto ni duplicado.

## Constraints & Engineering Rules (Clean Code + DRY/KISS/YAGNI)

- **Idioma y Nombres:** Código, identificadores, tipos y tests 100% en inglés con nombres reveladores de intención (prohibido `data`, `info`, `manager`, `temp`). Documentación y UI en español.
- **Tipado Estricto (Mentalidad TypeScript):** Uso obligatorio de `@dataclass(frozen=True, slots=True)`, `StrEnum` y `Literal`. Cero `Any` o diccionarios sin estructura entre capas.
- **Funciones Pequeñas y Puras:** `< 20` líneas ideal, responsabilidad única (SRP), _Return Early_ (Guard Clauses), 0–3 parámetros (agrupar en `dataclass` si hay más) y separación Command-Query (CQS).
- **Lógica de Negocio Central:**
    1. Si la oferta no viola un _Hard Reject_ y alcanza **`match_score >= 40%`**, postula y envía CV aunque no cumpla el 100% de requisitos.
    2. Si vuelve a encontrar la misma oferta (`dedup_key`), vuelve a postularse pero **nunca duplica la fila**: incrementa `times_applied = times_applied + 1` y anexa a `submission_history`.

---

## Steps (Construcción y Prueba Bloque por Bloque)

### Bloque 1: Cimientos, Modelos Tipados Inmutables y Normalizador (`domain`)

- [x]   1. Crear `.gitignore`, `.env.example`, `requirements.txt`, `pyproject.toml` y estructura de paquetes (`src/domain`, `src/adapters`, `src/services`, `src/ui`, `tests`) — `pyproject.toml`, `requirements.txt`
- [x]   2. Implementar modelos de dominio inmutables (`JobOffer`, `MatchEvaluation`, `ApplicationRecord`, `SubmissionAttempt`, `QuestionMatch`, `ApplicationStatus`) — `src/domain/models.py`
- [x]   3. Implementar normalizador de texto, limpieza de URLs canónicas y generador de `dedup_key` (`company_norm::title_norm`) — `src/domain/text_normalizer.py`
- [x]   4. **Prueba Bloque 1:** Crear y ejecutar tests deterministas del normalizador y modelos — verificar con `pytest tests/test_text_normalizer.py -v`

### Bloque 2: Motor de Scoring (`Match >= 40%`) y Configuración Declarativa

- [x]   5. Crear `config/filters.yaml` (whitelists/blacklists, pesos Core/Secundario/Complementario, umbral `min_match_score: 40`, `reapply_cooldown_days`) y cargador tipado — `config/filters.yaml`, `src/config_loader.py`
- [x]   6. Implementar `OfferMatcher` en `src/domain/matcher.py` (evaluación de _Hard Rejects_, cálculo ponderado de `%`, piso para ofertas cortas y detección de `matched_keywords` vs `missing_keywords`) — `src/domain/matcher.py`
- [x]   7. **Prueba Bloque 2:** Crear y ejecutar tests unitarios cubriendo rechazo duro, postulación parcial (`40%–69%`) y match ideal (`>= 70%`) — verificar con `pytest tests/test_matcher.py -v`

### Bloque 3: Persistencia SQLite y Re-Postulación con Contador Único (`times_applied`)

- [x]   8. Crear esquema DDL en `src/adapters/db/schema.sql` (`applications` con `dedup_key UNIQUE`, `times_applied`, `submission_history`, `qa_memory`, `keyword_stats`) — `src/adapters/db/schema.sql`
- [x]   9. Implementar `ApplicationRepository` en `src/adapters/db/repository.py` con SQL parametrizado, regla `should_reapply()` y `UPSERT` que incrementa `times_applied` sin duplicar registros — `src/adapters/db/repository.py`
- [x]   10. **Prueba Bloque 3:** Probar en SQLite `:memory:` primera postulación (`times_applied=1`), re-postulación en otro portal (`times_applied=2`), bloqueo durante cooldown y congelamiento en estado _Entrevista_ — verificar con `pytest tests/test_repository.py -v`

### Bloque 4: Motor de Memoria Difusa para Formularios (`qa_engine` + `RapidFuzz`)

- [x]   11. Crear plantillas `config/profile.example.yaml` y `config/cv_base.example.md` — `config/`
- [x]   12. Implementar `QuestionAnswerEngine` en `src/domain/qa_engine.py` (similitud `RapidFuzz >= 85%`, detección de moneda salarial `COP` vs `USD` y semilla inicial desde `profile.yaml`) — `src/domain/qa_engine.py`
- [x]   13. **Prueba Bloque 4:** Crear y ejecutar tests de similitud difusa y reglas ATS de salario/experiencia — verificar con `pytest tests/test_qa_engine.py -v`

### Bloque 5: Scrapers Multi-Portal Single-Thread y CLI con `Rich`

- [x]   14. Implementar gestor de contexto Playwright (`browser.py`), contrato `BasePortalScraper` (`base.py` con _Template Method_ DRY) y `ScraperOrchestrator` (`orchestrator.py` con aislamiento de errores) — `src/adapters/scrapers/`
- [x]   15. Implementar los 6 adaptadores de portales (`linkedin.py`, `getonbrd.py`, `computrabajo.py`, `elempleo.py`, `glassdoor.py`, `indeed.py`) — `src/adapters/scrapers/`
- [x]   16. Implementar `scan_service.py`, interfaz `src/ui/console.py` (`Rich`) y comandos `auth`, `scan`, `stats`, `export` en `cli.py` — `src/services/scan_service.py`, `src/ui/console.py`, `cli.py`
- [x]   17. **Prueba Bloque 5:** Verificar ejecución real de CLI (`python cli.py stats`, `python cli.py export`, `python cli.py scan --portal getonbrd --limit 5`)

### Bloque 6: Copiloto `assist`, Gemini (`tailor` / `prep`), Notion Multi-PC (`sync`), Servidor MCP y Cloud $0

- [x]   18. Implementar `GeminiClient` (`src/adapters/ai/gemini_client.py`) y `NotionClient` (`src/adapters/notion/notion_client.py` con soporte de _bootstrap_ para clonar datos en otro PC) — `src/adapters/`
- [x]   19. Implementar `assist_service.py` (autocompletado con bordes verde/amarillo y pausa antes de Submit) y `career_service.py` (`tailor`, `prep`, `sync`, `followups`) — `src/services/`
- [x]   20. Implementar Servidor MCP (`src/adapters/mcp/server.py`) con 5 herramientas (`get_pipeline_overview`, `search_applications`, `get_market_stack_radar`, `prepare_job_application_kit`, `sync_pipeline_with_notion`) y sus tests — `src/adapters/mcp/server.py`, `tests/test_mcp_server.py`
- [x]   21. Crear `Dockerfile`, `docker-compose.yml` y workflows `.github/workflows/ci.yml` + `.github/workflows/scheduled_scan.yml` — `Dockerfile`, `.github/workflows/`
- [x]   22. **Prueba Bloque 6 (End-to-End):** Ejecutar suite completa `pytest` y validar comandos CLI (`tailor`, `prep`, `sync`, `assist`) y el servidor MCP (`python -m src.adapters.mcp.server`)

## Log

- 2026-10-28 — Definida arquitectura modular en `docs/arquitectura/` (00 al 10), lógica de negocio en `docs/logica-negocio/` (01 al 05) y base de datos 3FN en `docs/base-de-datos/` (01 al 03) bajo principios Clean Code, tipado estricto estilo TypeScript, DRY, KISS y YAGNI.
- 2026-10-28 — **Bloque 1 completado y verificado** en rama `feature/block-1-domain-normalizer` (`11 passed` en `pytest` y `mypy --strict` sin errores).
- 2026-10-28 — **Bloque 2 completado y verificado** en rama `feature/block-2-matcher-scoring` (`20 passed` en `pytest` y `mypy --strict` sin errores en 12 archivos).
- 2026-10-28 — **Bloque 3 completado y verificado** en rama `feature/block-3-sqlite-repository` (`27 passed` en `pytest` y `mypy --strict` sin errores en 15 archivos).
- 2026-10-28 — **Bloque 4 completado y verificado** en rama `feature/block-4-qa-fuzzy-engine` (`41 passed` en `pytest` y `mypy --strict` sin errores en 17 archivos).
- 2026-10-28 — **Bloque 5 completado y verificado** en rama `feature/block-5-multiportal-scrapers` (`50 passed` en `pytest`, comandos CLI en vivo validados y `mypy --strict` sin errores en 32 archivos).
- 2026-10-28 — **Bloque 6 completado y verificado** en rama `feature/block-6-ai-notion-mcp-cloud` (`65 passed` en `pytest`, Servidor MCP con 5 herramientas, Copiloto assist, Gemini offline-safe, Notion multi-PC bootstrap, Docker/GitHub Actions y `mypy --strict` sin errores en 44 archivos).
