# 07. Catálogo de Patrones de Arquitectura y de Diseño

Este documento enumera todos los **Patrones de Arquitectura** y **Patrones de Diseño (GoF y Enterprise)** aplicados en `jobOS-bot`, indicando en qué archivo exacto se implementan y qué problema real resuelven sin violar **KISS** ni **YAGNI**.

---

## 1. Patrones de Arquitectura (Nivel Macro / Sistema)

| # | Patrón de Arquitectura | Dónde se Aplica | Qué Problema Resuelve |
| :--- | :--- | :--- | :--- |
| **1** | **Hexagonal Architecture (Ports & Adapters / Clean Architecture Ligera)** | Todo `src/` (`domain/`, `adapters/`, `services/`, `ui/`) | Aísla las reglas de negocio (`matcher.py`, `qa_engine.py`, `models.py`) de las herramientas externas (`Playwright`, `SQLite`, `Gemini`, `Notion`). Permite probar el 100% del dominio con `pytest` sin abrir el navegador ni conectarse a internet. |
| **2** | **Local-First Architecture** | `data/jobs.db` + `src/adapters/notion/notion_client.py` | **SQLite local es la única fuente de verdad.** El bot funciona a máxima velocidad (`< 2 ms`) sin depender de la red, y **Notion** actúa únicamente como una vista sincronizada bajo demanda (`sync`). |
| **3** | **Human-in-the-Loop (Copilot Pattern)** | `src/services/assist_service.py` | En lugar de una automatización ciega propensa a errores, el bot rellena el formulario, clasifica visualmente la confianza (verde = memoria exacta, amarillo = IA) y delega la decisión crítica final (*Submit*) al humano. |
| **4** | **Pipes and Filters (Pipeline Secuencial)** | Flujo de escaneo en `scan_service.py` y `matcher.py` | Procesa cada vacante a través de etapas desacopladas en serie: `Extracción Tarjeta -> Pre-filtro Blacklist -> Extracción Detalle -> Normalización -> Cálculo Match % -> Upsert SQLite`. Si una vacante cae en la etapa 2, ahorra las etapas 3 a 6. |
| **5** | **Command-Query Separation (CQS)** | `src/adapters/db/repository.py` y `src/domain/` | Separa estrictamente las funciones que **consultan datos** (Queries: `find_by_dedup_key`, `calculate_match_score`, sin efectos secundarios) de las que **modifican estado** (Commands: `record_submission_attempt`, `update_status`). |

---

## 2. Patrones de Diseño (Nivel Micro / Código y Clases)

### A. Patrones de Comportamiento (Behavioral Patterns)

| # | Patrón de Diseño | Dónde se Aplica | Por Qué Respeta DRY / KISS / YAGNI |
| :--- | :--- | :--- | :--- |
| **1** | **Strategy Pattern** | `src/adapters/scrapers/` (`LinkedInScraper`, `GetOnBrdScraper`, `ComputrabajoScraper`, etc.) | Permite cambiar o combinar algoritmos de extracción según el portal (`--portal linkedin,getonbrd`) en tiempo de ejecución sin usar bloques gigantes de `if/elif/else` por cada sitio web. |
| **2** | **Template Method Pattern** | `BasePortalScraper.scan()` en `src/adapters/scrapers/base.py` | **Puro DRY:** Define el esqueleto fijo del escaneo (navegar -> pausa humana -> extraer tarjetas -> pre-filtrar -> abrir detalles -> devolver `JobOffer`) en la clase padre. Las 6 clases hijas solo implementan los selectores DOM de su portal. |
| **3** | **State Pattern (Implícito / Máquina de Estados)** | `ApplicationStatus` en `src/domain/models.py` y `career_service.py` | Gobierna las transiciones válidas de una vacante (`Detectada -> Postulada -> Requiere Seguimiento -> Entrevista Programada / Rechazado`) y bloquea re-postulaciones cuando el estado ya es *Entrevista* o *Rechazado*. |
| **4** | **Chain of Responsibility (Guard Clauses Filter Chain)** | `OfferMatcher.evaluate()` en `src/domain/matcher.py` | Evalúa secuencialmente los filtros excluyentes (*Blacklist de empresa -> Blacklist de título Senior -> Whitelist de ubicación -> Umbral Match >= 40%*), cortando la ejecución (*Return Early*) apenas falla una regla. |

### B. Patrones Estructurales (Structural Patterns)

| # | Patrón de Diseño | Dónde se Aplica | Por Qué Respeta DRY / KISS / YAGNI |
| :--- | :--- | :--- | :--- |
| **5** | **Adapter / Wrapper Pattern** | `scrapers/*.py`, `gemini_client.py`, `notion_client.py` | Traduce el HTML caótico de 6 portales distintos y las respuestas JSON de las APIs de Google y Notion a nuestros modelos internos limpios (`JobOffer`, `QuestionMatch`). |
| **6** | **Repository Pattern** | `ApplicationRepository` en `src/adapters/db/repository.py` | Encapsula todo el SQL parametrizado (`INSERT ... ON CONFLICT(dedup_key) DO UPDATE SET times_applied = times_applied + 1`) en un solo lugar, manteniendo los servicios limpios de sentencias SQL. |
| **7** | **Facade Pattern** | `src/services/` (`scan_service.py`, `assist_service.py`, `career_service.py`) | Expone métodos simples de alto nivel para que `cli.py` tenga menos de 100 líneas y no tenga que coordinar directamente Playwright + Matcher + SQLite + Gemini + Rich. |
| **8** | **Cache-Aside (Read-Through Cache)** | `qa_memory` y `cv_tailor_cache` en SQLite + `gemini_client.py` | Antes de gastar tokens y tiempo llamando a Gemini (`400–2,000 ms`), verifica en SQLite (`< 0.5 ms`) si la pregunta (`>= 85%` con `RapidFuzz`) o la oferta ya tienen respuesta guardada. |

### C. Patrones Creacionales y de Dominio (Creational & DDD Tactical Patterns)

| # | Patrón de Diseño | Dónde se Aplica | Por Qué Respeta DRY / KISS / YAGNI |
| :--- | :--- | :--- | :--- |
| **9** | **Value Object / Immutable DTO** | `@dataclass(frozen=True, slots=True)` en `src/domain/models.py` | Inspirado en TypeScript (`readonly interface`): objetos como `JobOffer` o `MatchEvaluation` son 100% inmutables una vez creados, evitando mutaciones accidentales entre capas. |
| **10** | **Factory / Registry Pattern** | `ScraperOrchestrator` en `src/adapters/scrapers/orchestrator.py` | Mapa declarativo (`PORTAL_REGISTRY: dict[PortalName, type[BasePortalScraper]]`) que instancia únicamente los scrapers solicitados en el comando `--portal` sin `switch/case`. |
| **11** | **Dependency Injection (Por Constructor / Parámetro)** | Todos los servicios (`src/services/`) y tests (`tests/`) | Las clases reciben sus dependencias (`repository`, `config`, `matcher`) por constructor en vez de instanciar globales ocultos. Así en `pytest` inyectamos una base de datos `:memory:` en 1 línea. |

