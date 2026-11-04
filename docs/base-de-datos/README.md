# Documentación de Base de Datos, Grafo Local y Normalización — `jobOS-bot` v2.0

Esta carpeta documenta en profundidad el **diseño relacional en SQLite (`data/jobs.db`)**, la aplicación de las **Formas Normales (1FN, 2FN, 3FN)**, el índice B-Tree compuesto con *blocking* por empresa y los algoritmos de **normalización léxica/semántica** (`text_normalizer.py`) que alimentan tanto la base de datos SQLite como el **Vault en Grafo de Obsidian + Graphify** (ver [**11. Redefinición Arquitectónica v2.0**](../arquitectura/11-redefinicion-cqs-obsidian-multiworker.md)).

---

## Índice de Documentos

1. [**01. Modelo Entidad-Relación y Formas Normales (1FN, 2FN, 3FN)**](./01-modelo-relacional-y-formas-normales.md)
   * Cómo aplicamos normalización relacional clásica para separar la **Vacante Única (`applications`)** de sus **Múltiples Envíos (`application_submissions`)** y sus **Tecnologías (`application_keywords`)**, evitando anomalías de inserción, actualización y conteo.
2. [**02. Diccionario de Datos, Índices B-Tree y Esquema DDL (`schema.sql`)**](./02-diccionario-datos-y-ddl-sql.md)
   * Especificación columna por columna de las tablas, restricciones `CHECK`/`UNIQUE`/`FOREIGN KEY`, índice compuesto `(company_norm, title_norm)`, configuración `PRAGMA` de SQLite (`WAL`) y la transacción atómica `UPSERT` (`times_applied = times_applied + 1`).
3. [**03. Normalización Léxica, URLs Canónicas y Claves (`text_normalizer.py`)**](./03-normalizacion-lexica-y-claves-deduplicacion.md)
   * Reglas deterministas para transformar texto sucio del DOM en claves limpias: normalización de empresas (`S.A.S.`, `Inc.`), títulos de cargos, slugs para nodos de Obsidian (`vault/`) y limpieza de URLs canónicas por portal para postulación **Click-and-Apply**.
