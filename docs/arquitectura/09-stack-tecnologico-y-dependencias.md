# 09. Catálogo Completo del Stack Tecnológico, Frameworks y Dependencias

Este documento enumera **todas las tecnologías, librerías de terceros, módulos nativos de la librería estándar, servicios cloud gratuitos y herramientas de calidad/DevOps** que conforman `jobOS-bot`.

---

## 1. Lenguaje Base y Entorno de Ejecución (Runtime)

| Tecnología | Versión | Rol en el Proyecto |
| :--- | :--- | :--- |
| **Python** | `3.11+` (`3.11` / `3.12`) | Lenguaje único del sistema (100% Python), aprovechando mejoras de velocidad de CPython y soporte nativo de `StrEnum`, `Self` y tipado moderno. |
| **venv / pip** | Estándar | Aislamiento local del entorno virtual en Windows 11 (`.venv`). |

---

## 2. Dependencias Externas de Producción (`requirements.txt`)

Aplicando **KISS** y **Minimal Dependencies**, solo se instalan **8 paquetes externos** estrictamente justificados:

| Paquete (`pip`) | Motor Interno | Uso Específico en `jobOS-bot` |
| :--- | :--- | :--- |
| **`playwright`** | Chromium / C++ / Node | Automatización del navegador en **un solo hilo (*single-thread*)**, manejo de contexto persistente (`browser_profile` en local y `storage_state.json` en la nube) e inyección de bordes visuales en formularios (`assist`). |
| **`rapidfuzz`** | C++ compilado | Cálculo de similitud de cadenas (*Levenshtein / Token Set Ratio*) en `< 0.5 ms` para la memoria de autocompletado (`qa_memory`, umbral `>= 85%`). |
| **`google-genai`** | Python SDK Oficial | Cliente oficial para **`gemini-2.5-flash`** (usado únicamente en preguntas nuevas `< 85%`, adaptación quirúrgica de CV `tailor` y preparación de entrevistas `prep`). |
| **`httpx`** | HTTP/1.1 & HTTP/2 | Cliente HTTP moderno y ligero para consumir directamente la API REST v1 de **Notion** (`sync` Push/Pull y Bootstrap Multi-PC) sin SDKs pesados. |
| **`mcp`** (`FastMCP`) | Python / JSON-RPC (`stdio`) | SDK oficial de **Model Context Protocol** para exponer tus servicios de dominio a agentes de IA (`src/adapters/mcp/server.py`). |
| **`rich`** | Python Terminal UI | Renderizado de tablas estilizadas, barras de progreso por portal, paneles de diagnóstico y colores en la consola. |
| **`pyyaml`** | C (`LibYAML`) / Python | Lectura de la configuración declarativa (`config/filters.yaml` y `config/profile.yaml`). |
| **`python-dotenv`** | Python | Carga segura de variables de entorno desde `.env` en modo local (`GEMINI_API_KEY`, `NOTION_TOKEN`, `NOTION_DATABASE_ID`). |

---

## 3. Módulos de la Librería Estándar de Python (Cero Dependencias Extra)

En lugar de instalar librerías pesadas u ORMs innecesarios (**YAGNI**), explotamos al máximo la librería estándar de Python:

| Módulo Estándar | Qué Reemplaza (Ahorro de Bloat) | Uso en el Proyecto |
| :--- | :--- | :--- |
| **`sqlite3`** | Reemplaza SQLAlchemy / Tortoise / Prisma | Motor relacional ACID en archivo local (`data/jobs.db`), modo `WAL`, claves foráneas (`3FN`) y pruebas ultrarrápidas en `:memory:`. |
| **`dataclasses` + `typing` + `enum`** | Reemplaza esquemas complejos en el dominio interno | Contratos inmutables `@dataclass(frozen=True, slots=True)`, `StrEnum` y `Literal` (mentalidad TypeScript). |
| **`re` + `unicodedata`** | Reemplaza librerías pesadas de NLP (NLTK / spaCy) | Descomposición Unicode (`NFD` para quitar tildes), Regex pre-compilados para whitelists/blacklists y generación de `dedup_key`. |
| **`urllib.parse`** | Reemplaza `furl` / `yarl` | Limpieza y normalización de URLs canónicas (`urlsplit`, `parse_qsl`, `urlencode`). |
| **`csv` + `json` + `pathlib`** | Reemplaza `pandas` (ahorra >150 MB) | Exportación directa de SQLite a CSV (`cli.py export`), serialización y manejo multiplataforma de rutas. |
| **`argparse`** | Reemplaza frameworks CLI pesados | Definición limpia de subcomandos en `cli.py` (`auth`, `scan`, `assist`, `stats`, `tailor`, `prep`, `sync`, `export`). |

---

## 4. Dependencias de Testing y Calidad de Código (Dev & Portafolio)

| Herramienta | Propósito |
| :--- | :--- |
| **`pytest`** | Ejecución de pruebas unitarias deterministas (**F.I.R.S.T.**) sobre normalizadores, motor de scoring (`Match %`), repositorio SQLite en memoria y motor `qa_engine`. |
| **`mypy` / Type Hints** | Verificación estática de tipos para garantizar que no existan llamadas con tipos incompatibles ni uso de `Any` entre capas. |

---

## 5. Servicios Externos, Infraestructura y DevOps (100% Gratis — \$0/mes)

| Categoría | Tecnología / Plataforma | Rol en la Arquitectura | Costo |
| :--- | :--- | :--- | :--- |
| **Modelo de IA (LLM)** | **Google Gemini API (`gemini-2.5-flash`)** | Asistencia en preguntas de formulario inéditas, sugerencias de CV y planes de estudio de entrevistas. | **\$0.00** (Free Tier Google AI Studio) |
| **CRM / Dashboard Móvil y Web** | **Notion + Notion REST API (`v1`)** | Tablero visual Kanban/Tabla accesible desde tu celular o PC, sincronizado bajo demanda y usado como respaldo para clonar en otro PC. | **\$0.00** (Plan Personal Gratis) |
| **Protocolo de Agentes IA** | **MCP (`Model Context Protocol` via `stdio`)** | Permite consultar tu base de datos de postulaciones desde Antigravity, Claude Code, Claude Desktop o Cursor en cualquier PC. | **\$0.00** (Abierto / Local) |
| **Ejecución Cloud (PC Apagado)** | **GitHub Actions (`cron` + `workflow_dispatch`)** | Corre el bot automáticamente por horario o desde la app móvil de GitHub cuando tu PC está apagado. | **\$0.00** (Gratis en repositorios de GitHub) |
| **Persistencia en la Nube** | **GitHub Actions Cache (`actions/cache`) + Secrets** | Conserva tu archivo `data/jobs.db` entre corridas en la nube e inyecta `PLAYWRIGHT_STORAGE_STATE` de forma encriptada. | **\$0.00** (Incluido en GitHub) |
| **Contenedorización** | **Docker + Docker Compose** (`mcr.microsoft.com/playwright/python`) | Empaqueta Python + Chromium y sus dependencias del sistema para ejecución aislada y demostración de DevOps en tu portafolio. | **\$0.00** |

---

## 6. Portales de Empleo Soportados (Adaptadores de Scraping)

1. **LinkedIn Jobs** (`src/adapters/scrapers/linkedin.py`)
2. **GetOnBrd** (`src/adapters/scrapers/getonbrd.py`)
3. **Computrabajo Colombia** (`src/adapters/scrapers/computrabajo.py`)
4. **Elempleo.com** (`src/adapters/scrapers/elempleo.py`)
5. **Glassdoor** (`src/adapters/scrapers/glassdoor.py`)
6. **Indeed Colombia** (`src/adapters/scrapers/indeed.py`)

