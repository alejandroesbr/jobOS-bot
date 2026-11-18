# AGENTS.md — jobOS-bot

Fuente única de instrucciones para **todos** los agentes que trabajan en este repo
(Claude Code y Antigravity). Si algo aquí contradice otro documento, gana este archivo;
si contradice `docs/agents/*`, gana `docs/agents/*` en su tema específico.

---

## 1. Propósito

`jobOS-bot` es un motor de inteligencia laboral **100% Python 3.11+**: rastrea portales de empleo
en paralelo (Playwright multi-worker), filtra y puntúa ofertas contra el perfil del candidato,
persiste en **SQLite 3FN** y publica un grafo de conocimiento en un **Vault de Obsidian**
(`[[Wikilinks]]` hacia empresas, skills, portales y estados).

Estado: migración **v2.0 → v3.3** en curso, por bloques (`docs/blocks/block-N.md`).
Arquitectura: **Clean Architecture + Ports & Adapters + CQS**.

```
cli.py / src/adapters/mcp   → entrypoints (driving adapters)
src/application/            → commands/ (mutan) · queries/ (leen) · handlers/
src/ports/                  → contratos abstractos
src/domain/  (src/core/)    → núcleo puro, 0% I/O
src/adapters/               → db/ · scrapers/ · obsidian/ · notion/ · mcp/
```

## 2. Filosofía Zero-Daemon

- No hay procesos 24/7, cron ni workflows programados. El sistema **duerme** y despierta
  bajo demanda: una llamada MCP por `stdio` o una invocación puntual de la CLI.
- **Click-and-Apply**: no se inyectan scripts en formularios de terceros. Cada nota en
  `vault/applications/` trae la URL canónica limpia y el análisis de brechas; el humano postula.
- **Hard Rejects solo en el título** (*Senior*, *Lead*, *Staff*, *Architect*), nunca en la descripción.

## 3. CLI — 4 comandos nucleares (`cli.py`)

| Comando | Uso |
|---|---|
| `scan` | `python cli.py scan --portal all --workers 4 --limit 15 --vault-dir vault` |
| `sync` | `python cli.py sync --target obsidian --vault-dir vault` (o `--target notion`) |
| `auth` | `python cli.py auth [--portal glassdoor]` — sesión interactiva, persiste cookies |
| `export` | `python cli.py export --format json\|csv --output exports/applications.json` |

No se agregan comandos nuevos sin un bloque que lo especifique.

## 4. Servidor MCP — 3 tools (`src/adapters/mcp/server.py`, stdio)

| Tool | Tipo CQS | Efecto |
|---|---|---|
| `run_portal_scan_and_sync` | Command | Ejecuta `ScanPortalsCommand` en paralelo y actualiza el Vault |
| `query_job_applications` | Query | `GetApplicationsQuery` con filtros (`status`, `min_score`, `portal`, `limit`) |
| `sync_obsidian_vault` | Command | `SyncVaultCommand`: reconstruye el grafo completo en `vault/` |

**stdout pertenece al protocolo MCP.** Todo log va a `stderr`; un `print()` en el camino del
servidor rompe el transporte.

## 5. Reglas de código

- `mypy --strict` con cero errores en `src/`, `cli.py`, `tests/` y `.claude/hooks/`.
- Dominio puro: `src.domain` (y `src.core` cuando exista) **no importa** `src.adapters`,
  `sqlite3`, `httpx`, `playwright`, `crawlee`, `google`, `pydantic`, `mcp`
  (contrato import-linter en `pyproject.toml`).
- Entidades inmutables: `@dataclass(frozen=True, slots=True)`, `StrEnum`.
- CQS estricto: Commands mutan y devuelven un resultado de ejecución; Queries son lecturas
  idempotentes sin efectos secundarios.
- SQL siempre parametrizado. Nada de f-strings en queries.
- Gemini: modelos, dimensiones y prefijos según `docs/agents/gemini-api-facts.md`.
  IDs de modelo en `.env` / `filters.yaml`, nunca hardcodeados.
- Tests sin red: Gemini con respuestas grabadas en JSON, HTML de portales sanitizado, CV ficticio.

### Umbrales vigentes (verificados contra el código v2)

| Mecanismo | Valor real | Dónde |
|---|---|---|
| Blocking por empresa (dedup) | `token_sort_ratio >= 88` | `src/adapters/db/repository.py` (`find_by_company_blocking`, `threshold=88.0`) |
| Cascada de skills | 4 niveles: hash exacto → plantilla regex → RapidFuzz `token_set_ratio >= 85` → embeddings `>= 0.82` | `src/domain/fuzzy_matcher.py` (`FuzzyCascadeMatcher`) |
| Nivel 4 (embeddings) | **stub**: devuelve `None` y está apagado (`enable_embeddings=False`) | `match_embeddings` en el mismo archivo |
| Match mínimo de oferta | `min_match_score = 40` (configurable) | `config/filters.yaml` → `src/config_loader.py`, aplicado en `src/domain/matcher.py` |

Si un documento dice otra cosa (p. ej. "blocking 85%" o "cascada de 3 niveles"), manda el código; corrige el documento.

## 6. Rutas protegidas (privacidad)

Ningún agente lee, edita ni sube al repo:

- `.env` (solo `.env.example` es público)
- `data/**`
- `config/profile.yaml`, `config/cv_base.md`, `config/*.pdf`
- `vault/`, `exports/` (salidas generadas, en `.gitignore`)

Datos del CV o del perfil **nunca** aparecen en logs, fixtures, issues ni commits.

## 7. División de roles

Detalle completo: [`docs/agents/ownership.md`](docs/agents/ownership.md). Resumen:

- **Antigravity** — escribe el código de producción: `src/**`, `cli.py`, Docker, `README.md`,
  `.agents/**`, handoffs y capturas de bloque, resto de `docs/`.
- **Claude Code** — auditor: escribe tests, reglas y especificaciones (`tests/**`, `AGENTS.md`,
  `CLAUDE.md`, `.claude/**`, `docs/agents/**`, `docs/audits/**`, `docs/blocks/block-N.md`,
  `.github/workflows/**`, secciones `[tool.*]` de `pyproject.toml`). **Nunca edita `src/` ni `cli.py`.**

Un agente que necesite un cambio en una ruta ajena lo pide en el handoff o en la auditoría;
no lo hace él mismo.

## 8. Flujo por bloque

1. Claude Code escribe `docs/blocks/block-N.md` (especificación) y los tests que fallan.
2. Antigravity implementa en `feature/block-<N>-<slug>` hasta poner los tests en verde y
   deja `docs/blocks/block-N-handoff.md`.
3. Claude Code audita → `docs/audits/block-N-roundK.md` con veredicto
   `APPROVED` o `CHANGES_REQUESTED`.
4. Merge a `develop` solo con `APPROVED` **y** aprobación explícita del humano.

## 9. Gitflow y commits

Detalle: [`docs/arquitectura/10-gitflow-y-convenciones.md`](docs/arquitectura/10-gitflow-y-convenciones.md).

| Rama | Uso |
|---|---|
| `main` | Versiones estables. Nadie hace push directo. |
| `develop` | Integración. Solo recibe merges `--no-ff` aprobados. Nadie hace push directo. |
| `feature/block-<N>-<slug>` | Un bloque, nace de `develop`. |
| `chore/<slug>`, `docs/<slug>` | Configuración / documentación. |
| `hotfix/<slug>`, `release/vX.Y.Z` | Desde `main`. |

Commits en **inglés**, Conventional Commits:

```
<type>(<scope>): <imperative summary in lowercase>
```

Tipos: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`. Ejemplos:
`test(block-3): add failing tests for vec0 schema`, `chore(agents): add stop hook gate`.

Prohibido: `git push --force` (en cualquier variante), push a `main`/`develop`, commitear rutas protegidas.

## 10. Cómo verificar (quality gates)

Instalar dependencias de desarrollo (pip ≥ 25.1):

```bash
pip install -r requirements.txt
pip install --group dev
```

Gates (los mismos que corre CI en cada PR a `develop`):

```bash
ruff check .
ruff format --check .
mypy --strict src cli.py tests .claude/hooks
lint-imports
python -m pytest
```

Un bloque no está terminado si un gate falla. Los hooks de Claude Code corren una versión
reducida (solo archivos modificados) al terminar cada turno; la suite completa corre en CI.

## 11. Punteros a documentación

| Tema | Documento |
|---|---|
| Arquitectura rectora v2 (CQS, Obsidian, multi-worker, MCP) | `docs/arquitectura/11-redefinicion-cqs-obsidian-multiworker.md` |
| Índice de arquitectura | `docs/arquitectura/README.md` |
| Scrapers multiportal | `docs/arquitectura/01-scrapers-multiportal.md` |
| Filtrado y deduplicación | `docs/arquitectura/02-filtrado-datos-y-deduplicacion.md` |
| Servidor MCP | `docs/arquitectura/08-servidor-mcp.md` |
| Stack y dependencias | `docs/arquitectura/09-stack-tecnologico-y-dependencias.md` |
| Base de datos (3FN, DDL, normalización) | `docs/base-de-datos/` |
| Scoring, postulación, estados | `docs/logica-negocio/` |
| Dueños de cada ruta | `docs/agents/ownership.md` |
| Hechos verificados de la API Gemini | `docs/agents/gemini-api-facts.md` |
| Especificaciones y handoffs por bloque | `docs/blocks/` |
| Auditorías | `docs/audits/` |
