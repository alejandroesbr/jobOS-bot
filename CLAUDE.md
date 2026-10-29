# jobOS-bot

Copiloto local en Windows 11 (**100% Python** + Playwright + SQLite + Gemini + Notion + Rich) para escanear múltiples portales de empleo de forma secuencial (*single-thread*), filtrar vacantes Junior/Remoto/Barranquilla, asistir el autocompletado de formularios y preparar entrevistas técnicas (React, Node.js, NestJS, PostgreSQL). Diseñado para uso personal diario y como proyecto de ingeniería de software para portafolio.

## Commands
```powershell
python cli.py auth                            # Abre navegador para loguearse y exporta data/storage_state.json
python cli.py scan --portal all               # Escanea secuencialmente todos los portales habilitados
python cli.py scan --portal linkedin,getonbrd # Escanea portales específicos (single-thread)
python cli.py assist <url>                    # Autocompleta formulario con memoria local + Gemini (PC visible)
python cli.py stats                           # Ranking en consola (Rich) de tecnologías más pedidas
python cli.py tailor <job_id>                 # Sugiere ajustes al CV según la descripción del cargo
python cli.py prep <job_id>                   # Genera guía de entrevista en interviews/<empresa>.md
python cli.py sync                            # Sincroniza estados con Notion y marca follow-ups (+7 días)
python cli.py export                          # Exporta tabla applications a CSV
pytest                                        # Ejecuta la suite de tests unitarios (filtros, matcher, parsers)
docker compose run --rm jobos scan --portal all # Ejecución contenedorizada (Docker)
```

## Architecture
- `cli.py`: Único punto de entrada por línea de comandos con salida formateada en `Rich`.
- `src/models.py`: Modelos de datos tipados (`dataclasses`) para ofertas normalizadas (`JobOffer`), resultados de filtrado y respuestas de formulario.
- `src/db.py` + `src/schema.sql`: Capa SQLite (`data/jobs.db`) con 3 tablas (`applications`, `qa_memory`, `keyword_stats`) y deduplicación inter-portal. Sin ORM.
- `src/scrapers/`: Arquitectura basada en el patrón **Adapter/Strategy** (`base.py` con `BasePortalScraper`) ejecutada en **un solo hilo secuencial**:
  - `linkedin.py` (LinkedIn Jobs)
  - `getonbrd.py` (GetOnBrd)
  - `computrabajo.py` y `elempleo.py` (Mercado local Colombia)
  - `glassdoor.py` e `indeed.py` (Portales globales)
- `src/matcher.py`: Filtro Regex declarativo (`config/filters.yaml`), deduplicación y similitud Levenshtein (`rapidfuzz`, umbral `>= 85%`).
- `src/ai.py` y `src/notion.py`: Clientes ligeros para `gemini-2.5-flash` y Notion API.
- `tests/`: Pruebas unitarias deterministas con `pytest` (sin red ni navegador) para demostrar calidad de código en el portafolio.

## Conventions
- **100% Python con tipado estricto:** Usar type hints estándar de Python 3.11+ (`list[str]`, `str | None`, `dataclass`) en todas las funciones y módulos.
- **Postulación por Rango de % (No exige 100% de requisitos):** Si una oferta no tiene un *Hard Reject* (ej. Senior/+5 años) y alcanza el umbral mínimo de compatibilidad (`match_score >= 40%`), el bot envía la hoja de vida y postula aunque falten requisitos secundarios.
- **Re-postulación con Registro Único (`times_applied`):** Cuando vuelve a encontrar la misma oferta (en otro portal o republicada tras el cooldown), vuelve a postularse pero **nunca duplica la fila** en SQLite ni en Notion; hace `UPSERT` por `dedup_key` incrementando `times_applied = times_applied + 1` y anexando el envío a `submission_history`.
- **SQLite es la única fuente de verdad:** Notion es solo un espejo visual sincronizado bajo demanda con `python cli.py sync`.
- **Ejecución Single-Thread Multi-Portal:** Todos los scrapers comparten la misma sesión persistente de Playwright (`./data/browser_profile`, `headless=False`) y se ejecutan uno tras otro con aislamiento de errores (*graceful degradation*).
- **Configuración declarativa:** Toda regla de filtrado o dato personal vive en `config/filters.yaml`, `config/profile.yaml` y `config/cv_base.md`, nunca quemada en el código.
- **Caché de IA obligatorio:** Nunca llamar a Gemini dos veces para el mismo `job_id` o la misma pregunta normalizada en `qa_memory`.

## Traps
- **Detección anti-bot y Modo Dual (Local vs. Cloud):** En local usar `headless=False` con `./data/browser_profile`. Cuando corra con el PC apagado (GitHub Actions / Docker), usar `HEADLESS=true` inyectando `storage_state.json` y manteniendo siempre ejecución **single-thread secuencial** con pausas aleatorias (`2.5s` a `6.0s`).
- **Selectores rotos en un portal:** Si un portal cambia su DOM o pide captcha, el scraper de ese portal debe capturar la excepción, reportar el aviso en `Rich` y permitir que el orquestador continúe con el siguiente portal.
- **Ruido en keywords:** No usar TF-IDF abierto sobre texto libre; contar coincidencias únicamente contra la lista cerrada `tech_keywords` de `config/filters.yaml`.
- **HTML sucio a LLMs:** Extraer solo `inner_text()` del contenedor de la descripción (máx. 4,000 caracteres) antes de enviarlo a Gemini.

## Rules
- Never enviar un formulario automáticamente (`submit`); siempre detenerse para que el usuario revise y haga clic final.
- Never usar multithreading/multiprocessing para escaneo web ni crear demonios 24/7 en segundo plano, ORMs o UIs web propias.
- Never subir al repositorio `.env`, `data/`, `config/profile.yaml`, `config/cv_base.md`, `interviews/` ni `followups/`.
- Always mantener los tests unitarios en `tests/` pasando al modificar `matcher.py`, `db.py` o normalizadores.
- Always actualizar `PLAN.md` al completar cada paso.
