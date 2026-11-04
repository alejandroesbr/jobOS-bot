-- jobOS-bot v2.0 Database Schema
-- Clean Architecture + CQS + Multi-Worker + Obsidian Graph Database
-- SQLite with UPSERT, Composite Indexes, Blocking Strategy

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

-- ============================================================================
-- CORE TABLES (Preserved from v1 with enhancements)
-- ============================================================================

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

-- ============================================================================
-- v2.0 ENHANCEMENTS: Composite Indexes for Query Performance
-- ============================================================================

-- Composite index for "open applications by portal + match_score" query pattern
CREATE INDEX IF NOT EXISTS idx_applications_status_portal_score
    ON applications(status, portal, match_score DESC);

-- Composite index for "recent applications by company" query pattern
CREATE INDEX IF NOT EXISTS idx_applications_company_last_applied
    ON applications(company, last_applied_at DESC);

-- Composite index for "applications needing follow-up" query pattern
CREATE INDEX IF NOT EXISTS idx_applications_followup
    ON applications(status, first_applied_at) WHERE status IN ('Enviado', 'Entrevista Programada');

-- Composite index for submission history lookups
CREATE INDEX IF NOT EXISTS idx_submissions_app_portal_canonical
    ON application_submissions(application_id, portal, canonical_url);

-- Composite index for keyword analytics with match filter
CREATE INDEX IF NOT EXISTS idx_keywords_app_weight_matched
    ON application_keywords(application_id, weight DESC, is_matched);

-- ============================================================================
-- v2.0 NEW TABLES: Bayesian Scoring Support
-- ============================================================================

-- Keyword IDF cache for Bayesian scoring (auto-updated by background job or sync)
CREATE TABLE IF NOT EXISTS keyword_idf (
    keyword TEXT PRIMARY KEY,
    document_frequency INTEGER NOT NULL DEFAULT 1,
    inverse_document_frequency REAL NOT NULL DEFAULT 1.0,
    total_documents INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Skill co-occurrence matrix for Graph Analyzer (FP-Growth associations)
CREATE TABLE IF NOT EXISTS skill_cooccurrence (
    skill_a TEXT NOT NULL,
    skill_b TEXT NOT NULL,
    cooccurrence_count INTEGER NOT NULL DEFAULT 1,
    support REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    lift REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (skill_a, skill_b),
    CHECK (skill_a < skill_b)
);

-- Company clusters from Louvain community detection
CREATE TABLE IF NOT EXISTS company_communities (
    company TEXT PRIMARY KEY,
    community_id INTEGER NOT NULL,
    modularity_class INTEGER NOT NULL,
    degree_centrality REAL NOT NULL DEFAULT 0.0,
    betweenness_centrality REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- ============================================================================
-- v2.0 NEW TABLES: Multi-Worker Metrics & Observability
-- ============================================================================

-- Worker execution metrics for monitoring concurrent scraping
CREATE TABLE IF NOT EXISTS worker_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portal TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    duration_ms INTEGER,
    offers_found INTEGER NOT NULL DEFAULT 0,
    offers_matched INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    error_details TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed', 'timeout')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Scan session metadata for audit trail
CREATE TABLE IF NOT EXISTS scan_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    portals TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    total_scanned INTEGER NOT NULL DEFAULT 0,
    total_matched INTEGER NOT NULL DEFAULT 0,
    new_applications INTEGER NOT NULL DEFAULT 0,
    reapplications INTEGER NOT NULL DEFAULT 0,
    skipped_cooldown INTEGER NOT NULL DEFAULT 0,
    hard_rejected INTEGER NOT NULL DEFAULT 0,
    obsidian_synced INTEGER NOT NULL DEFAULT 0,
    execution_time_ms INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at TEXT
);

-- ============================================================================
-- v2.0 TRIGGERS: Auto-maintenance
-- ============================================================================

-- Auto-update updated_at timestamp on applications table
CREATE TRIGGER IF NOT EXISTS trg_applications_updated_at
AFTER UPDATE ON applications
BEGIN
    UPDATE applications
    SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE id = NEW.id;
END;

-- Auto-update keyword IDF when new application is inserted
CREATE TRIGGER IF NOT EXISTS trg_keyword_idf_on_insert
AFTER INSERT ON application_keywords
BEGIN
    INSERT OR IGNORE INTO keyword_idf (keyword, document_frequency, total_documents, inverse_document_frequency)
    VALUES (NEW.keyword, 1, 1, 0.0);

    UPDATE keyword_idf
    SET document_frequency = document_frequency + 1,
        updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE keyword = NEW.keyword;
END;

-- Auto-update skill co-occurrence when keywords are added to application
CREATE TRIGGER IF NOT EXISTS trg_skill_cooccurrence_on_keywords
AFTER INSERT ON application_keywords
WHEN NEW.is_matched = 1
BEGIN
    INSERT OR IGNORE INTO skill_cooccurrence (skill_a, skill_b, cooccurrence_count, support, confidence, lift)
    SELECT
        CASE WHEN NEW.keyword < kw.keyword THEN NEW.keyword ELSE kw.keyword END as skill_a,
        CASE WHEN NEW.keyword < kw.keyword THEN kw.keyword ELSE NEW.keyword END as skill_b,
        1, 0.0, 0.0, 1.0
    FROM application_keywords kw
    WHERE kw.application_id = NEW.application_id
      AND kw.keyword != NEW.keyword
      AND kw.is_matched = 1;
END;

-- ============================================================================
-- v2.0 VIEWS: Common Query Patterns
-- ============================================================================

-- View for open applications with full context
CREATE VIEW IF NOT EXISTS v_open_applications AS
SELECT
    a.*,
    json_group_array(
        json_object(
            'portal', s.portal,
            'canonical_url', s.canonical_url,
            'applied_at', s.applied_at
        )
    ) as submissions_json
FROM applications a
LEFT JOIN application_submissions s ON a.id = s.application_id
WHERE a.status IN ('Pendiente', 'Enviado', 'Entrevista Programada', 'Requiere Seguimiento')
GROUP BY a.id;

-- View for keyword market demand analysis
CREATE VIEW IF NOT EXISTS v_keyword_demand AS
SELECT
    k.keyword,
    k.document_frequency,
    k.inverse_document_frequency,
    k.total_documents,
    CAST(k.document_frequency AS REAL) / k.total_documents as market_prevalence
FROM keyword_idf k
ORDER BY k.document_frequency DESC;

-- View for company clustering analysis
CREATE VIEW IF NOT EXISTS v_company_clusters AS
SELECT
    c.company,
    c.community_id,
    c.modularity_class,
    c.degree_centrality,
    c.betweenness_centrality,
    COUNT(a.id) as application_count,
    AVG(a.match_score) as avg_match_score
FROM company_communities c
LEFT JOIN applications a ON c.company = a.company
GROUP BY c.company, c.community_id, c.modularity_class, c.degree_centrality, c.betweenness_centrality;