# Documentación de Base de Datos y Normalización — `jobOS-bot`

Esta carpeta documenta en profundidad el **diseño relacional en SQLite (`data/jobs.db`)**, la aplicación de las **Formas Normales (1FN, 2FN, 3FN)** y los algoritmos de **normalización léxica/semántica** (`text_normalizer.py`) que garantizan que nunca se dupliquen vacantes ni se contaminen las métricas cuando el bot se re-postula.

---

## Índice de Documentos

1. [**01. Modelo Entidad-Relación y Formas Normales (1FN, 2FN, 3FN)**](./01-modelo-relacional-y-formas-normales.md)
   * Cómo aplicamos normalización relacional clásica para separar la **Vacante Única (`applications`)** de sus **Múltiples Envíos (`application_submissions`)** y sus **Tecnologías (`application_keywords`)**, evitando anomalías de inserción, actualización y conteo.
2. [**02. Diccionario de Datos, Índices y Esquema DDL (`schema.sql`)**](./02-diccionario-datos-y-ddl-sql.md)
   * Especificación columna por columna de las 4 tablas, restricciones `CHECK`/`UNIQUE`/`FOREIGN KEY`, configuración `PRAGMA` de SQLite (`WAL`) y la transacción exacta de re-postulación (`times_applied + 1`).
3. [**03. Normalización Léxica, URLs Canónicas y Claves (`text_normalizer.py`)**](./03-normalizacion-lexica-y-claves-deduplicacion.md)
   * Reglas deterministas para transformar texto sucio del DOM en claves limpias: normalización de empresas (`S.A.S.`, `Inc.`), títulos de cargos, limpieza de URLs por portal y normalización de preguntas para `RapidFuzz`.

