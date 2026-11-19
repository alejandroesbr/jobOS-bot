# Gemini API — hechos verificados

Verificados en la documentación oficial de Google (nov-2026). No agregar nada de memoria:
cualquier hecho nuevo se verifica en la doc oficial antes de entrar aquí.

## Modelos LLM

- LLM ingesta (extracción estructurada): `gemini-3.5-flash-lite`.
- LLM RAG Top 5: `gemini-3.8-flash`.

## Prohibidos

- `gemini-1.5-*`
- `gemini-2.0-*`
- `text-embedding-004`
- `embedding-001`
- `gemini-3.1-flash-lite` (apagado programado 7-may-2027)

## Embeddings

- Modelo: `gemini-embedding-2`.
- 3072 dims por defecto → usar `output_dimensionality=768`.
- Auto-normaliza dimensiones truncadas (no normalizar a mano).
- Límite 8192 tokens de entrada.

## Asimetría query / documento

- `gemini-embedding-2` **NO** acepta `task_type`. La asimetría se expresa por prefijo en el texto:
  - query → `"task: search result | query: {content}"`
  - documento → `"title: {title} | text: {content}"` (sin título: `"title: none"`)

## Batching

- Varios strings en `contents` → **UN** vector agregado.
- Para un vector por oferta, cada una en su propio objeto `Content`.

## Configuración

- IDs de modelo en `.env` / `filters.yaml`, nunca hardcodeados.
