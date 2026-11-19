---
name: portal-parser
description: >-
  Use this skill when building, updating, or debugging job portal scrapers and
  HTML parsers in jobOS-bot. Enforces 2-stage scraping (card -> detail), pure
  HTML-to-dataclass parser functions without network I/O, and sanitized DOM
  captures in docs/blocks/captures/<portal>/.
---

# Portal Parser Skill (`portal-parser`)

Guía para implementar y mantener scrapers y parsers de portales de empleo (`linkedin`, `getonbrd`, `computrabajo`, `elempleo`, `glassdoor`, `indeed`) en `jobOS-bot v3.3`.

## 1. Arquitectura de Scraping en 2 Etapas (Tarjeta $\rightarrow$ Detalle)

Todo scraper sigue el flujo en dos etapas:
1. **Etapa 1 — Listado de Tarjetas (`card`)**:
   - Extrae las tarjetas resumen desde la página de resultados de búsqueda.
   - Ejecuta el pre-filtrado rápido en memoria (título contra `title_blacklist`, empresa contra `company_blacklist`) **antes** de navegar al detalle, evitando peticiones innecesarias (*early exit*).
2. **Etapa 2 — Detalle de la Oferta (`detail`)**:
   - Solo para las tarjetas que superan el pre-filtro, obtiene la vista de detalle y extrae la descripción completa y metadatos adicionales.

## 2. Parsers como Funciones Puras (`HTML -> dataclass`, 0% Red)

- **Separación estricta entre transporte y parsing**:
  - Cada parser de tarjeta y de detalle debe ser una **función pura** que recibe un string HTML (o fragmento DOM serializado) y devuelve dataclasses inmutables (`RawJobCard`, `JobOffer`, etc.).
  - **Cero red en el parser**: los parsers no abren sesiones de navegador, no hacen llamadas HTTP ni leen archivos de configuración o base de datos.
  - Si utilizas `crawlee` o utilidades de extracción, consulta **Context7** antes de invocar su API para verificar firmas exactas.
  - Esto garantiza que todos los tests unitarios de Claude Code puedan ejecutarse 100% offline sobre fixtures HTML deterministas.

## 3. Captura e Inspección del DOM con el Navegador Integrado

Cuando necesites inspeccionar la estructura DOM real de un portal o capturar páginas de muestra para que Claude Code genere fixtures de pruebas:

1. **Usa el navegador integrado de Antigravity** (nunca agregues un servidor MCP de navegador externo).
2. **Guarda el HTML capturado** en:
   `docs/blocks/captures/<portal>/` (por ejemplo, `docs/blocks/captures/linkedin/search_cards.html` y `docs/blocks/captures/linkedin/job_detail.html`).
3. **SANITIZACIÓN OBLIGATORIA antes de guardar o commitear**:
   - Elimina cualquier aparición de tu nombre real, correo electrónico, teléfono, URL de perfil personal o identificadores de cuenta.
   - Elimina tokens CSRF, `session_id`, cabeceras/cookies de sesión, scripts con datos de usuario embebidos (`window.__INITIAL_STATE__` con PII, etiquetas `<meta name="csrf-token">`, etc.).
   - Verifica con `grep -i` que ningún dato de `config/profile.yaml` ni credenciales aparezcan en el archivo `.html`.
4. **Handoff a Claude Code**:
   - Una vez guardadas las capturas sanitizadas en `docs/blocks/captures/<portal>/`, notifícalo en `docs/blocks/block-N-handoff.md`. Claude Code es el encargado de convertirlas en fixtures dentro de `tests/fixtures/`. Nunca escribas directamente en `tests/**`.
