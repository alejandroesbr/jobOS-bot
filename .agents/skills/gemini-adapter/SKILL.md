---
name: gemini-adapter
description: >-
  Use this skill when implementing or modifying the Gemini LLM and embedding
  adapters in jobOS-bot (src/adapters/llm/). Enforces docs/agents/gemini-api-facts.md,
  Context7 verification for google-genai, and strict isolation of Pydantic schemas
  in src/adapters/llm/schemas.py with conversion to core/domain frozen dataclasses.
---

# Gemini Adapter Skill (`gemini-adapter`)

Guía obligatoria para construir o modificar el adaptador de Gemini (`src/adapters/llm/`) en `jobOS-bot v3.3`.

## 1. Verificación Previa Obligatoria

1. **Lee `docs/agents/gemini-api-facts.md`** antes de escribir una sola línea de código. Nunca uses nombres de modelos, dimensiones ni parámetros de memoria.
2. **Consulta Context7** para el SDK `google-genai` (y `sqlite-vec` si interactúas con vectores) para verificar las firmas vigentes de `Client`, `models.generate_content`, `models.embed_content` y `types.EmbedContentConfig` / `types.GenerateContentConfig`.

## 2. Reglas de Modelos y Embeddings (`gemini-api-facts.md`)

- **Modelos permitidos**:
  - LLM ingesta (extracción estructurada): `gemini-3.5-flash-lite`
  - LLM RAG Top 5: `gemini-3.8-flash`
  - Embeddings: `gemini-embedding-2`
- **Modelos estrictamente prohibidos**:
  - `gemini-1.5-*`, `gemini-2.0-*`, `text-embedding-004`, `embedding-001`, `gemini-3.1-flash-lite`.
- **Configuración externa**:
  - Los IDs de modelo se leen desde `.env` / `config/filters.yaml`; **nunca** se hardcodean como literales fijos de negocio sin configuración.
- **Reglas de `gemini-embedding-2`**:
  - Produce 3072 dimensiones por defecto $\rightarrow$ **siempre configurar `output_dimensionality=768`**.
  - `gemini-embedding-2` ya auto-normaliza las dimensiones truncadas (**no normalizar vectores a mano**).
  - Límite de entrada: `8192` tokens.
  - **Sin `task_type`**: `gemini-embedding-2` **NO** acepta `task_type`. La asimetría query/documento se expresa mediante prefijos en el texto:
    - Query: `"task: search result | query: {content}"`
    - Documento: `"title: {title} | text: {content}"` (si no hay título, usar `"title: none"`).
  - **Batching de embeddings**:
    - Pasar varios strings dentro de `contents` produce **UN solo vector agregado**.
    - Para obtener un vector por cada oferta, cada oferta debe ir en su propio objeto `Content` separado.

## 3. Aislamiento de Esquemas Pydantic (`src/adapters/llm/schemas.py`)

- **Frontera arquitectónica (`lint-imports`)**:
  - El núcleo (`src/domain/` / `src/core/`) y `src/ports/` tienen **prohibido importar `pydantic` o `google`**.
  - Todos los esquemas `pydantic.BaseModel` utilizados para *Structured Outputs* (`response_schema`) de Gemini deben vivir **exclusivamente en `src/adapters/llm/schemas.py`**.
- **Conversión en el Adaptador**:
  - El adaptador en `src/adapters/llm/` recibe la respuesta validada por Pydantic desde `google-genai` y la convierte inmediatamente a las `@dataclass(frozen=True, slots=True)` definidas en el núcleo (`src/domain/` / `src/core/`) antes de retornarla a través del puerto.
- **Logging**:
  - Cualquier log del adaptador debe ir a `stderr` (nunca `print()` en `stdout`).
