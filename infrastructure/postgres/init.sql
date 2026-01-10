-- ============================================================================
-- Intelligent Job Dashboard - PostgreSQL Schema Initialization
-- ============================================================================
-- This script runs automatically when PostgreSQL container starts
-- Creates tables for:
--   1. jobs (job listings from Adzuna)
--   2. job_scores (TF-IDF vectors and recommendation scores)
--   3. batch_runs (audit trail of data collection/processing)
-- ============================================================================

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search optimization

-- ============================================================================
-- TABLE 1: JOBS
-- Stores all job listings collected from Adzuna API
-- ============================================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_title VARCHAR(500) NOT NULL,
    company_name VARCHAR(500),
    location VARCHAR(200),
    posted_date DATE,
    job_description TEXT,
    skills_required TEXT,  -- Stored as comma-separated for now (can be JSON later)
    salary_range VARCHAR(100),
    salary_min INTEGER,
    salary_max INTEGER,
    has_salary BOOLEAN DEFAULT FALSE,
    has_skills BOOLEAN DEFAULT FALSE,
    url VARCHAR(1000),
    source VARCHAR(50) DEFAULT 'adzuna',  -- enum-like: 'adzuna', 'linkedin', etc.
    search_query VARCHAR(200),
    days_since_posted INTEGER,

    -- Metadata columns
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Data quality flag
    data_quality_score FLOAT DEFAULT 1.0
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_jobs_job_title ON jobs(job_title);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_name);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_search_query ON jobs(search_query);
CREATE INDEX IF NOT EXISTS idx_jobs_has_salary ON jobs(has_salary);
CREATE INDEX IF NOT EXISTS idx_jobs_has_skills ON jobs(has_skills);

-- Full-text search index for job descriptions
CREATE INDEX IF NOT EXISTS idx_jobs_description_trgm ON jobs USING gin(job_description gin_trgm_ops);

-- ============================================================================
-- TABLE 2: MODEL_VERSIONS
-- Tracks TF-IDF models (metadata only, vectors stored as files)
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_versions (
    model_version VARCHAR(50) PRIMARY KEY,  -- e.g., "tfidf_v1", "tfidf_v2"
    model_type VARCHAR(50) DEFAULT 'tfidf',  -- type of model

    -- File paths (relative to models/ directory)
    vectorizer_path VARCHAR(500) NOT NULL,  -- e.g., "tfidf/v1/vectorizer.joblib"
    matrix_path VARCHAR(500) NOT NULL,      -- e.g., "tfidf/v1/matrix.joblib"

    -- Model metadata
    trained_on_jobs_count INTEGER,  -- how many jobs used to train this
    feature_count INTEGER,  -- dimensionality of vectors (e.g., 10000)
    ngram_range VARCHAR(20),  -- e.g., "(1, 2)" for unigrams and bigrams

    -- Status
    status VARCHAR(50) DEFAULT 'active',  -- 'active', 'archived', 'deprecated'

    -- Audit trail
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),  -- which batch/process created this
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for model_versions
CREATE INDEX IF NOT EXISTS idx_model_versions_status ON model_versions(status);
CREATE INDEX IF NOT EXISTS idx_model_versions_created_at ON model_versions(created_at DESC);

-- ============================================================================
-- TABLE 3: BATCH_RUNS
-- Audit trail for automated batch processing
-- ============================================================================
CREATE TABLE IF NOT EXISTS batch_runs (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_date DATE NOT NULL,

    -- Pipeline stage information
    stage VARCHAR(50),  -- 'collect', 'validate', 'enrich', 'vectorize', 'export'
    status VARCHAR(50) NOT NULL,  -- 'pending', 'in_progress', 'success', 'failed'

    -- Processing statistics
    jobs_collected INTEGER DEFAULT 0,
    jobs_validated INTEGER DEFAULT 0,
    jobs_enriched INTEGER DEFAULT 0,
    jobs_vectorized INTEGER DEFAULT 0,
    jobs_inserted INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,

    -- Error handling
    error_message TEXT,

    -- Performance metrics
    execution_time_seconds INTEGER,  -- Total time for this stage

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Additional context
    notes TEXT
);

-- Indexes for batch_runs
CREATE INDEX IF NOT EXISTS idx_batch_runs_batch_date ON batch_runs(batch_date DESC);
CREATE INDEX IF NOT EXISTS idx_batch_runs_status ON batch_runs(status);
CREATE INDEX IF NOT EXISTS idx_batch_runs_stage ON batch_runs(stage);
CREATE INDEX IF NOT EXISTS idx_batch_runs_created_at ON batch_runs(created_at DESC);


-- ============================================================================
-- VIEWS (for easier querying)
-- ============================================================================

-- View: Recent jobs (last 7 days)
CREATE OR REPLACE VIEW recent_jobs AS
SELECT
    job_id,
    job_title,
    company_name,
    location,
    posted_date,
    salary_min,
    salary_max,
    skills_required,
    days_since_posted
FROM jobs
WHERE posted_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY posted_date DESC;

-- View: Jobs with complete data (has title, description, salary, skills)
CREATE OR REPLACE VIEW complete_jobs AS
SELECT
    job_id,
    job_title,
    company_name,
    location,
    job_description,
    skills_required,
    salary_min,
    salary_max
FROM jobs
WHERE job_title IS NOT NULL
  AND job_description IS NOT NULL
  AND has_salary = TRUE
  AND has_skills = TRUE;

-- View: Latest batch run status
CREATE OR REPLACE VIEW latest_batch_status AS
SELECT
    batch_id,
    batch_date,
    stage,
    status,
    jobs_inserted,
    jobs_updated,
    jobs_failed,
    execution_time_seconds,
    created_at
FROM batch_runs
ORDER BY created_at DESC
LIMIT 1;

-- ============================================================================
-- COMMENTS (for documentation)
-- ============================================================================
COMMENT ON TABLE jobs IS 'Core table storing all job listings from Adzuna API and cleaned data';
COMMENT ON TABLE model_versions IS 'Metadata for TF-IDF models (vectors stored as files, not in DB)';
COMMENT ON TABLE batch_runs IS 'Audit trail for batch processing pipeline runs';

COMMENT ON COLUMN jobs.data_quality_score IS 'Score from 0.0 to 1.0 indicating data completeness and quality';
COMMENT ON COLUMN model_versions.model_version IS 'Version identifier (e.g., tfidf_v1, tfidf_v2)';
COMMENT ON COLUMN model_versions.status IS 'active, archived, or deprecated';
COMMENT ON COLUMN batch_runs.stage IS 'Pipeline stage: collect, validate, enrich, vectorize, export';
COMMENT ON COLUMN batch_runs.status IS 'Current status: pending, in_progress, success, failed';

-- ============================================================================
-- SAMPLE DATA (for testing, uncomment if needed)
-- ============================================================================
-- INSERT INTO jobs (job_title, company_name, location, posted_date, job_description, salary_min, salary_max)
-- VALUES (
--     'Senior Data Engineer',
--     'Tech Company',
--     'Paris',
--     CURRENT_DATE,
--     'We are looking for a senior data engineer with experience in Python, SQL, and AWS',
--     60000,
--     80000
-- );

-- INSERT INTO model_versions (model_version, vectorizer_path, matrix_path, trained_on_jobs_count, feature_count, status)
-- VALUES (
--     'tfidf_v1',
--     'tfidf/v1/vectorizer.joblib',
--     'tfidf/v1/matrix.joblib',
--     8737,
--     10000,
--     'active'
-- );
