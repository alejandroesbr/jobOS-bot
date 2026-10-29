PRAGMA foreign_keys = ON;

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

CREATE TABLE IF NOT EXISTS application_keywords (
    application_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    is_matched INTEGER NOT NULL CHECK (is_matched IN (0, 1)),
    weight INTEGER NOT NULL CHECK (weight IN (1, 2, 3)),
    PRIMARY KEY (application_id, keyword),
    FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
);

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
