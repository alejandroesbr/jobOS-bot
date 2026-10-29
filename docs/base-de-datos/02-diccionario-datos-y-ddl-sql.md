# 02. Diccionario de Datos, Índices y Esquema DDL (`schema.sql`)

Este documento contiene la especificación técnica exacta del motor **SQLite 3** (`src/adapters/db/schema.sql`), incluyendo los pragmas de integridad, restricciones de dominio (`CHECK`), índices de búsqueda y la transacción atómica de postulación/re-postulación.

---

## 1. Configuración del Motor SQLite (`PRAGMA`)

Al abrir cada conexión en `src/adapters/db/repository.py`, se ejecutan tres directivas obligatorias:

```sql
PRAGMA foreign_keys = ON;        -- Garantiza integridad referencial y ON DELETE CASCADE
PRAGMA journal_mode = WAL;       -- Write-Ahead Logging: lecturas rápidas sin bloqueo
PRAGMA synchronous = NORMAL;     -- Rendimiento óptimo en SSD local con seguridad ACID
```

---

## 2. Script DDL Completo (`src/adapters/db/schema.sql`)

```sql
-- 1. Tabla Maestra de Vacantes Únicas (3FN + Contador Sincronizado)
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT NOT NULL,
    modality TEXT NOT NULL CHECK (modality IN ('remote', 'hybrid', 'onsite')),
    description TEXT NOT NULL,
    match_score INTEGER NOT NULL CHECK (match_score BETWEEN 0 AND 100),
    times_applied INTEGER NOT NULL DEFAULT 0 CHECK (times_applied >= 0),
    status TEXT NOT NULL DEFAULT 'Pendiente' CHECK (
        status IN (
            'Pendiente',
            'Enviado',
            'Requiere Seguimiento',
            'Entrevista Programada',
            'Oferta Recibida',
            'Rechazado',
            'Descartado'
        )
    ),
    notion_page_id TEXT UNIQUE,
    cv_tailor_cache TEXT,
    interview_prep_path TEXT,
    first_applied_at TEXT,
    last_applied_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- 2. Tabla Hija de Envíos / Historial de Postulaciones por Vacante (1:N en 3FN)
CREATE TABLE IF NOT EXISTS application_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    portal TEXT NOT NULL CHECK (
        portal IN ('linkedin', 'getonbrd', 'computrabajo', 'elempleo', 'glassdoor', 'indeed')
    ),
    external_id TEXT,
    canonical_url TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE,
    UNIQUE (application_id, attempt_number)
);

-- 3. Tabla Relacional de Tecnologías por Vacante (1:N en 3FN para Radar de Mercado)
CREATE TABLE IF NOT EXISTS application_keywords (
    application_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    is_matched INTEGER NOT NULL CHECK (is_matched IN (0, 1)),
    weight INTEGER NOT NULL CHECK (weight IN (1, 2, 3)),
    PRIMARY KEY (application_id, keyword),
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);

-- 4. Tabla de Memoria Difusa de Autocompletado (3FN)
CREATE TABLE IF NOT EXISTS qa_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_norm TEXT NOT NULL UNIQUE,
    raw_example TEXT NOT NULL,
    answer TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general' CHECK (
        category IN ('salary_cop', 'salary_usd', 'experience', 'location', 'general')
    ),
    source TEXT NOT NULL DEFAULT 'profile_seed' CHECK (
        source IN ('profile_seed', 'user_confirmed')
    ),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Índices para consultas en < 1 ms
CREATE INDEX IF NOT EXISTS idx_applications_status_last_applied
    ON applications(status, last_applied_at);

CREATE INDEX IF NOT EXISTS idx_applications_match_score
    ON applications(match_score DESC);

CREATE INDEX IF NOT EXISTS idx_submissions_canonical_url
    ON application_submissions(canonical_url);

CREATE INDEX IF NOT EXISTS idx_submissions_app_portal
    ON application_submissions(application_id, portal, applied_at DESC);

CREATE INDEX IF NOT EXISTS idx_keywords_keyword
    ON application_keywords(keyword);
```

---

## 3. Transacción Atómica de Postulación y Re-Postulación (`repository.py`)

Cuando el bot se postula a una vacante (sea la primera vez o la enésima re-postulación), `ApplicationRepository.record_submission()` ejecuta una **única transacción ACID**:

### Caso A: Primera Postulación (`dedup_key` no existe)
1. Inserta en `applications` con `times_applied = 1`, `status = 'Enviado'`, `first_applied_at = now`, `last_applied_at = now`.
2. Inserta en `application_submissions` el intento `attempt_number = 1` con el `portal` y `canonical_url`.
3. Inserta en lote (`executemany`) los registros en `application_keywords` tanto para las tecnologías que hiciste match (`is_matched = 1`) como para las que te faltaron (`is_matched = 0`).

### Caso B: Re-Postulación (`dedup_key` ya existe en `applications`)
1. **No inserta otra fila en `applications` ni vuelve a duplicar `application_keywords`.**
2. Ejecuta sobre el registro maestro existente:
   ```sql
   UPDATE applications
   SET times_applied = times_applied + 1,
       last_applied_at = :applied_at,
       updated_at = :applied_at,
       status = CASE
           WHEN status = 'Requiere Seguimiento' THEN 'Enviado'
           ELSE status
       END
   WHERE id = :application_id;
   ```
3. Inserta únicamente el nuevo evento de envío en la tabla hija `application_submissions`:
   ```sql
   INSERT INTO application_submissions (
       application_id, attempt_number, portal, external_id, canonical_url, applied_at
   ) VALUES (
       :application_id, :new_attempt_number, :portal, :external_id, :canonical_url, :applied_at
   );
   ```

