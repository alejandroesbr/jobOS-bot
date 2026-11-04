# Documentación de Lógica de Negocio — `jobOS-bot` v2.0

Esta carpeta define las **reglas de negocio, fórmulas de decisión algorítmica y comportamientos estratégicos** de `jobOS-bot` v2.0. Para la visión integral de Clean Architecture, CQS, Multi-Worker y el grafo en Obsidian + Graphify, consulta [**11. Redefinición Arquitectónica v2.0 (`11-redefinicion-cqs-obsidian-multiworker.md`)**](../arquitectura/11-redefinicion-cqs-obsidian-multiworker.md).

---

## Índice de Reglas de Negocio

1. [**01. Motor de Scoring (%), Tokenizador $O(n)$ y Suavizado Bayesiano (`01-motor-scoring-y-umbrales.md`)**](./01-motor-scoring-y-umbrales.md)
   * Evaluación de *Hard Rejects* exclusivamente sobre el título del cargo, extracción de tecnologías en $O(n)$ (`TechTokenizer`), ponderación con suavizado bayesiano e IDF (`BayesianScorer`) y regla de umbral flexible (`match_score >= 40%`).
2. [**02. Ciclo de Postulación, Re-Postulación y Contador Único (`02-ciclo-postulacion-y-repostulacion.md`)**](./02-ciclo-postulacion-y-repostulacion.md)
   * Deduplicación mediante `dedup_key` y *blocking* difuso por empresa (`company_norm` + `token_sort_ratio >= 85%`), actualización atómica con `UPSERT` (`times_applied = times_applied + 1`) y trazabilidad en `application_submissions`.
3. [**04. Máquina de Estados, Flujo Click-and-Apply en Obsidian y Seguimiento (`04-estados-seguimiento-y-entrevistas.md`)**](./04-estados-seguimiento-y-entrevistas.md)
   * Ciclo de vida de una postulación (`Nuevo`, `Postulado`, `Entrevista`, `Descartado`), navegación visual en el grafo de Obsidian (`vault/`) y postulación directa mediante enlaces canónicos limpios.
