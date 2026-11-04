# jobOS-bot v2.0

Motor concurrente de inteligencia laboral (**100% Python 3.11+** + Playwright Multi-Worker + SQLite 3FN + Obsidian Graph Vault / Graphify + Servidor MCP On-Demand) diseñado bajo **Clean Architecture**, **Ports & Adapters** y **CQS (Command Query Separation)**.

---

## 1. Comandos Nucleares de CLI (`cli.py`)

```bash
# 1. Escaneo Multi-Worker concurrente y sincronización con el Vault de Obsidian
python cli.py scan --portal all --workers 4 --limit 15 --vault-dir vault
python cli.py scan --portal linkedin,getonbrd --workers 2 --vault-dir vault

# 2. Sincronización de grafo local (Obsidian por defecto) o destino secundario (Notion)
python cli.py sync --target obsidian --vault-dir vault
python cli.py sync --target notion

# 3. Autenticación interactiva para persistir sesiones/cookies anti-detección
python cli.py auth
python cli.py auth --portal glassdoor

# 4. Exportación de registros desde SQLite a JSON o CSV
python cli.py export --format json --output exports/applications.json
python cli.py export --format csv --output exports/applications.csv

# 5. Verificación de calidad y tipado estricto
pytest -v
mypy --strict src cli.py tests
```

---

## 2. Arquitectura Limpia + CQS + Ports & Adapters

- **`cli.py`**: Entrypoint de línea de comandos (`Click` + `Rich`) que despacha exclusivamente los 4 comandos nucleares (`scan`, `sync`, `auth`, `export`) hacia los handlers de aplicación.
- **`src/domain/`** (Núcleo Puro, `0% I/O`):
  - `models.py`: Entidades y Value Objects inmutables (`@dataclass(frozen=True, slots=True)`, `StrEnum`).
  - `text_normalizer.py`: Normalización Unicode NFD, URLs canónicas, slugs y claves `dedup_key`.
  - `tech_tokenizer.py`: `TechTokenizer` — Lexer/tokenizador en $O(n)$ con diccionario hash de alias (`js` -> `JavaScript`, `c#` -> `CSharp`, `.net` -> `DotNet`) y soporte para símbolos `#+.-` sin falsos positivos de `\b`.
  - `fuzzy_matcher.py`: `FuzzyCascadeMatcher` — Cascada en 3 niveles: Hash Exacto $O(1)$ -> Plantilla Regex con slots $O(L)$ -> `RapidFuzz` con corte temprano (`score_cutoff >= 85%`).
  - `bayesian_scorer.py`: `BayesianScorer` — Suavizado bayesiano con prior $p_0$, peso de evidencia $\alpha$ y ponderación por rareza $IDF(t) = \log(N / (1 + df_t))$.
  - `graph_analyzer.py`: `GraphAnalyzer` — Proyección unipartita Skill-to-Skill de co-ocurrencia, detección de comunidades y matriz de priorización de brechas técnicas $\text{Prioridad}(s) = \text{Demanda}(s) \times (1 - \text{Dominio}(s))$.
  - `matcher.py`: `OfferMatcher` — Evalúa *Hard Rejects* únicamente sobre el título del cargo y calcula compatibilidad ponderada (`match_score >= 40%`).
- **`src/ports/`** (Contratos Abstractos):
  - `repository_port.py`: `ApplicationRepositoryPort`
  - `scraper_port.py`: `PortalScraperPort`
  - `vault_port.py`: `KnowledgeVaultPort`
  - `external_sync_port.py`: `ExternalSyncPort`
- **`src/application/`** (Patrón CQS — Command Query Separation):
  - **`commands/`**: `ScanPortalsCommand` (`scan_portals.py`), `SyncVaultCommand` (`sync_vault.py`), `SyncExternalCommand` (`sync_external.py`).
  - **`queries/`**: `GetApplicationsQuery` (`get_applications.py`), `GetApplicationByIdQuery` (`get_application_by_id.py`).
  - **`handlers/`**: `ScanPortalsHandler`, `SyncVaultHandler`, `SyncExternalHandler`, `GetApplicationsHandler`, `GetApplicationByIdHandler`.
- **`src/adapters/`** (Infraestructura Concreta):
  - **`obsidian/`**: `ObsidianVaultAdapter` (`adapter.py`, `frontmatter.py`, `wikilinks.py`, `hubs.py`) — Genera notas Markdown con YAML frontmatter y enlaces bidireccionales `[[Wikilinks]]` hacia hubs en `companies/`, `skills/`, `portals/` y `status/` para visualización en **Obsidian + Graphify**.
  - **`scrapers/`**: `MultiWorkerScraperOrchestrator` (`orchestrator.py`) con `ThreadPoolExecutor` y contextos Playwright aislados por worker sobre `linkedin.py`, `getonbrd.py`, `computrabajo.py`, `elempleo.py`, `glassdoor.py` e `indeed.py`.
  - **`db/`**: `SQLiteApplicationRepository` (`repository.py` + `schema.sql`) — Persistencia en 3FN con WAL, índice B-Tree compuesto `(company_norm, title_norm)`, *blocking* por empresa (`token_sort_ratio >= 85%`) y `UPSERT` atómico (`times_applied = times_applied + 1`).
  - **`mcp/`**: Servidor MCP On-Demand (`server.py`, Zero-Daemon via `stdio`) que expone 3 herramientas:
    1. `run_portal_scan_and_sync`: Ejecuta `ScanPortalsCommand` en paralelo y actualiza el Vault de Obsidian.
    2. `query_job_applications`: Ejecuta `GetApplicationsQuery` con filtros analíticos (`status`, `min_score`, `portal`, `limit`).
    3. `sync_obsidian_vault`: Ejecuta `SyncVaultCommand` para reconstruir el grafo completo en `vault/`.
  - **`notion/`**: `NotionSyncAdapter` (`notion_client.py`) — Adaptador secundario opcional (`ExternalSyncPort`).

---

## 3. Convenciones y Reglas Estrictas

- **Tipado Estricto (`mypy --strict`)**: Todo el código en `src/`, `cli.py` y `tests/` debe pasar `mypy --strict` con cero errores.
- **Separación CQS Pura**: Los *Commands* mutan estado (SQLite / Obsidian Vault) y devuelven resultados de ejecución; las *Queries* son lecturas puras e idempotentes sin efectos secundarios.
- **Zero-Daemon On-Demand**: El sistema no ejecuta demonios 24/7 en segundo plano; despierta bajo demanda vía MCP (`stdio`) o invocación puntual en CLI.
- **Click-and-Apply desde Obsidian**: No se inyectan scripts en formularios DOM de terceros; cada nota de vacante en `vault/applications/` incluye la URL canónica limpia y el análisis de brechas técnicas para postulación directa.
- **Hard Rejects Solo en el Título**: Las palabras clave de exclusión (*Senior*, *Lead*, *Staff*, *Architect*) se evalúan únicamente sobre el título de la oferta para evitar falsos descartes en el cuerpo de la descripción.
- **Privacidad**: Nunca subir al repositorio `.env`, `data/`, `vault/`, `exports/`, `config/profile.yaml` ni `config/cv_base.md`.
