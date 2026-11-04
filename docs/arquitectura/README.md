# Documentación de Arquitectura — `jobOS-bot` v2.0

Bienvenido a la documentación técnica de arquitectura de **`jobOS-bot` v2.0**. Esta carpeta desglosa el diseño del sistema bajo **Clean Architecture**, **Ports & Adapters**, el patrón **CQS (Command Query Separation)**, el orquestador **Multi-Worker Concurrente**, la base de datos en grafo local con **Obsidian + Graphify** y la activación **Zero-Daemon On-Demand via MCP**.

> [!IMPORTANT]
> **Documento Rector de la v2.0:** Consulta primero [**11. Redefinición Arquitectónica v2.0: Clean Architecture, CQS, Multi-Worker, Grafo en Obsidian y Activación On-Demand via MCP (`11-redefinicion-cqs-obsidian-multiworker.md`)**](./11-redefinicion-cqs-obsidian-multiworker.md).

---

## Índice de Documentos

1. [**11. Redefinición Arquitectónica v2.0: Clean Architecture, CQS, Multi-Worker, Grafo en Obsidian y MCP (`11-redefinicion-cqs-obsidian-multiworker.md`)**](./11-redefinicion-cqs-obsidian-multiworker.md)
   * Especificación maestra de la arquitectura v2.0: separación CQS (`Commands` y `Queries`), `MultiWorkerScraperOrchestrator` con `ThreadPoolExecutor`, Vault de Obsidian con `[[Wikilinks]]` para **Graphify**, servidor MCP On-Demand (3 tools), CLI depurada de 4 comandos (`scan`, `sync`, `auth`, `export`) y mejoras algorítmicas (`TechTokenizer`, `FuzzyCascadeMatcher`, `BayesianScorer`, `GraphAnalyzer`).
2. [**00. Visión, Stack y Límites de Alcance (`00-vision-y-alcance.md`)**](./00-vision-y-alcance.md)
   * Diagnóstico de cuellos de botella, elección del stack **100% Python 3.11+**, principios de diseño y reglas estrictas anti-*overengineering*.
3. [**01. Motor de Scraping Multi-Portal (`01-scrapers-multiportal.md`)**](./01-scrapers-multiportal.md)
   * Implementación del patrón **Strategy / Adapter** (`BasePortalScraper`), evasión anti-bot y aislamiento de fallos (*graceful degradation*) sobre los 6 portales objetivo.
4. [**02. Modelo de Datos, Filtrado y Deduplicación (`02-filtrado-datos-y-deduplicacion.md`)**](./02-filtrado-datos-y-deduplicacion.md)
   * Esquema relacional en **SQLite**, motor de reglas declarativas (`filters.yaml`) y deduplicación inter-portal con índice compuesto y *blocking*.
5. [**04. Sincronización Externa con Notion (`04-sincronizacion-notion-y-followups.md`)**](./04-sincronizacion-notion-y-followups.md)
   * Protocolo secundario opcional de sincronización (`--target notion`) mediante `ExternalSyncPort` y `NotionSyncAdapter`.
6. [**05. Despliegue, Docker y Privacidad (`05-despliegue-hibrido-y-seguridad.md`)**](./05-despliegue-hibrido-y-seguridad.md)
   * Operación local y contenedorizada con Docker protegiendo sesiones y datos personales.
7. [**06. Estructura Clean Code y Plan de Pruebas (`06-estructura-clean-code-y-plan.md`)**](./06-estructura-clean-code-y-plan.md)
   * Reglas **DRY / KISS / YAGNI + Clean Code**, tipado estricto (`mypy --strict`) y pruebas deterministas (`pytest`).
8. [**07. Catálogo de Patrones de Arquitectura y de Diseño (`07-patrones-diseno-y-arquitectura.md`)**](./07-patrones-diseno-y-arquitectura.md)
   * Patrones arquitectónicos (Clean Architecture, Ports & Adapters, CQS) y de diseño aplicados en el proyecto.
9. [**08. Servidor MCP On-Demand (`08-servidor-mcp.md`)**](./08-servidor-mcp.md)
   * Exposición de los Commands y Queries mediante **Model Context Protocol (`stdio`)** para activación Just-In-Time desde Claude, Cursor o Antigravity.
10. [**09. Catálogo del Stack Tecnológico y Dependencias (`09-stack-tecnologico-y-dependencias.md`)**](./09-stack-tecnologico-y-dependencias.md)
    * Runtime Python 3.11+, librerías de producción (`requirements.txt`), tipado con `mypy --strict` y testing con `pytest`.
11. [**10. Flujo de Trabajo Gitflow y Convenciones de Commits (`10-gitflow-y-convenciones.md`)**](./10-gitflow-y-convenciones.md)
    * Estrategia de ramas (`main`, `develop`, `feature/*`, `hotfix/*`), merges explícitos (`--no-ff`) y estándar *Conventional Commits*.
