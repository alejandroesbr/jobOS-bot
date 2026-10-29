# Documentación de Arquitectura — `jobOS-bot`

Bienvenido a la documentación técnica de arquitectura de **`jobOS-bot`**. Esta carpeta desglosa el diseño del sistema en módulos especializados, explicando los patrones de diseño, diagramas de flujo, modelo de datos y decisiones de ingeniería.

---

## Índice de Documentos

1. [**00. Visión, Stack y Límites de Alcance (`00-vision-y-alcance.md`)**](./00-vision-y-alcance.md)
   * Diagnóstico de cuellos de botella reales, elección del stack **100% Python**, principios de diseño y reglas estrictas anti-*overengineering*.
2. [**01. Motor de Scraping Multi-Portal Secuencial (`01-scrapers-multiportal.md`)**](./01-scrapers-multiportal.md)
   * Implementación del patrón **Strategy / Adapter** (`BasePortalScraper`), ejecución *single-thread* sobre los 6 portales objetivo, evasión anti-bot y aislamiento de fallos (*graceful degradation*).
3. [**02. Modelo de Datos, Filtrado y Deduplicación (`02-filtrado-datos-y-deduplicacion.md`)**](./02-filtrado-datos-y-deduplicacion.md)
   * Esquema relacional en **SQLite**, motor de reglas declarativas (`filters.yaml`), radar estadístico de tecnologías y deduplicación inter-portal.
4. [**03. Copiloto de Autocompletado e IA Quirúrgica (`03-copiloto-ia-y-autocompletado.md`)**](./03-copiloto-ia-y-autocompletado.md)
   * Funcionamiento de la memoria difusa (`qa_memory` + `RapidFuzz >= 85%`), integración con **Gemini 2.5 Flash**, flujo *Human-in-the-Loop* en el navegador, adaptación de CV (`tailor`) y preparación de entrevistas (`prep`).
5. [**04. Sincronización con Notion y Seguimiento (`04-sincronizacion-notion-y-followups.md`)**](./04-sincronizacion-notion-y-followups.md)
   * Protocolo de sincronización ligera (*Push / Pull*) entre SQLite y **Notion API**, además del detector automático de postulaciones estancadas (`+7` y `+14` días).
6. [**05. Despliegue Híbrido (\$0/mes), Docker y Privacidad (`05-despliegue-hibrido-y-seguridad.md`)**](./05-despliegue-hibrido-y-seguridad.md)
   * Cómo opera el bot en **Modo Local Interactivo** (Windows 11) y en **Modo Cloud con PC Apagado** (GitHub Actions + `actions/cache` + Secrets + Docker) sin costo alguno, protegiendo tus datos personales.
7. [**06. Tipo de Arquitectura, Árbol de Módulos, Clean Code y Plan de Pruebas (`06-estructura-clean-code-y-plan.md`)**](./06-estructura-clean-code-y-plan.md)
   * Definición de la **Lightweight Hexagonal Architecture (Ports & Adapters)**, árbol completo de archivos, reglas **DRY / KISS / YAGNI + Clean Code (mentalidad TypeScript)** y plan de implementación/pruebas en 6 bloques.
8. [**07. Catálogo de Patrones de Arquitectura y de Diseño (`07-patrones-diseno-y-arquitectura.md`)**](./07-patrones-diseno-y-arquitectura.md)
   * Lista completa de los 5 patrones de arquitectura y 11 patrones de diseño aplicados en el proyecto, dónde vive cada uno y qué problema resuelve.
9. [**08. Servidor MCP Nativo y Sincronización Multi-PC (`08-servidor-mcp.md`)**](./08-servidor-mcp.md)
   * Exposición de los servicios de dominio mediante **Model Context Protocol (`stdio`)** con 5 herramientas para agentes de IA y *bootstrap* desde Notion al cambiar de PC.
10. [**09. Catálogo Completo del Stack Tecnológico, Frameworks y Dependencias (`09-stack-tecnologico-y-dependencias.md`)**](./09-stack-tecnologico-y-dependencias.md)
    * Lista exhaustiva del runtime, las 8 librerías de producción (`requirements.txt`), módulos de la librería estándar, herramientas de testing (`pytest`), Docker, GitHub Actions y APIs externas.
11. [**10. Flujo de Trabajo Gitflow y Convenciones de Commits (`10-gitflow-y-convenciones.md`)**](./10-gitflow-y-convenciones.md)
    * Estrategia de ramas (`main`, `develop`, `feature/block-*`, `hotfix/*`), merges explícitos (`--no-ff`) y estándar *Conventional Commits*.

