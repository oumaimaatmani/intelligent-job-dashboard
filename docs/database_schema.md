# Database Schema - Intelligent Job Dashboard

**Last Updated:** 2026-01-08
**Database:** PostgreSQL 15
**Status:** Production-ready

---

## Overview

The Intelligent Job Dashboard uses a relational schema with 3 core tables:

1. **jobs** - All job listings from Adzuna API with enriched data
2. **model_versions** - Metadata for TF-IDF models (vectors stored as files)
3. **batch_runs** - Audit trail of automated batch processing

All tables support ACID compliance, full-text search, and batch analytics.

---

## Entity Relationship Diagram

```
┌─────────────────────────────────┐
│          batch_runs             │
├─────────────────────────────────┤
│ batch_id (PK)                   │
│ batch_date                      │
│ stage                           │
│ status                          │
│ jobs_collected                  │
│ jobs_validated                  │
│ jobs_enriched                   │
│ jobs_vectorized                 │
│ jobs_inserted/updated/failed    │
│ execution_time_seconds          │
│ created_at, updated_at          │
└─────────────────────────────────┘
         (Audit Trail)


┌─────────────────────────────────┐
│            jobs                 │
├─────────────────────────────────┤
│ job_id (PK)                     │
│ job_title                       │
│ company_name                    │
│ location                        │
│ posted_date                     │
│ job_description                 │
│ skills_required                 │
│ salary_min, salary_max          │
│ has_salary, has_skills (flags)  │
│ url, source                     │
│ search_query                    │
│ days_since_posted               │
│ data_quality_score              │
│ created_at, updated_at          │
└─────────────────────────────────┘
     (Job Listings Data)


┌─────────────────────────────────┐
│      model_versions             │
├─────────────────────────────────┤
│ model_version (PK)              │
│ model_type                      │
│ vectorizer_path                 │
│ matrix_path                     │
│ trained_on_jobs_count          │
│ feature_count                   │
│ ngram_range                     │
│ status                          │
│ created_by                      │
│ created_at, updated_at          │
└─────────────────────────────────┘
  (Model Metadata, not vectors)
```

---

## Table Definitions

### TABLE 1: jobs

Stores all job listings collected from Adzuna API with enriched data and quality metrics.

```sql
CREATE TABLE jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Core job information
    job_title VARCHAR(500) NOT NULL,
    company_name VARCHAR(500),
    location VARCHAR(200),
    posted_date DATE,
    job_description TEXT,

    -- Extracted fields
    skills_required TEXT,                -- Comma-separated skills
    salary_range VARCHAR(100),           -- Original range string (e.g., "60,000 - 80,000 EUR")
    salary_min INTEGER,                  -- Parsed minimum salary
    salary_max INTEGER,                  -- Parsed maximum salary

    -- Data quality flags
    has_salary BOOLEAN DEFAULT FALSE,    -- True if salary_min/max populated
    has_skills BOOLEAN DEFAULT FALSE,    -- True if skills_required populated

    -- Source tracking
    url VARCHAR(1000),
    source VARCHAR(50) DEFAULT 'adzuna', -- 'adzuna', 'linkedin', etc.
    search_query VARCHAR(200),           -- Query used to find this job

    -- Computed fields
    days_since_posted INTEGER,           -- Recalculated on queries

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Quality metric (0.0 to 1.0)
    data_quality_score FLOAT DEFAULT 1.0
);
```

#### Column Definitions

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| job_id | UUID | NO | Primary key, auto-generated |
| job_title | VARCHAR(500) | NO | Required, used for search |
| company_name | VARCHAR(500) | YES | May be missing for some jobs |
| location | VARCHAR(200) | YES | Standardized to proper case |
| posted_date | DATE | YES | Used for recency filtering |
| job_description | TEXT | YES | Full HTML-cleaned description |
| skills_required | TEXT | YES | Comma-separated, extracted by NLP |
| salary_range | VARCHAR(100) | YES | Original string from API |
| salary_min | INTEGER | YES | Parsed and validated |
| salary_max | INTEGER | YES | Parsed and validated |
| has_salary | BOOLEAN | NO | Default FALSE, indexed |
| has_skills | BOOLEAN | NO | Default FALSE, indexed |
| url | VARCHAR(1000) | YES | Direct link to job |
| source | VARCHAR(50) | NO | Default 'adzuna' |
| search_query | VARCHAR(200) | YES | Tracks which query found it |
| days_since_posted | INTEGER | YES | Calculated, not stored |
| created_at | TIMESTAMP | NO | Batch run timestamp |
| updated_at | TIMESTAMP | NO | Last modification time |
| data_quality_score | FLOAT | NO | Default 1.0 (0.0 = incomplete) |

#### Indexes (9 total)

```sql
-- Filter by title/location/company
CREATE INDEX idx_jobs_job_title ON jobs(job_title);
CREATE INDEX idx_jobs_location ON jobs(location);
CREATE INDEX idx_jobs_company ON jobs(company_name);

-- Time-based queries (most recent first)
CREATE INDEX idx_jobs_posted_date ON jobs(posted_date DESC);

-- Tracking & audit
CREATE INDEX idx_jobs_source ON jobs(source);
CREATE INDEX idx_jobs_search_query ON jobs(search_query);

-- Data quality filtering (very common)
CREATE INDEX idx_jobs_has_salary ON jobs(has_salary);
CREATE INDEX idx_jobs_has_skills ON jobs(has_skills);

-- Full-text search on descriptions (trigram for fuzzy matching)
CREATE INDEX idx_jobs_description_trgm ON jobs USING gin(job_description gin_trgm_ops);
```

#### Common Query Patterns

```sql
-- Get all jobs from last 7 days
SELECT * FROM jobs
WHERE posted_date >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY posted_date DESC;

-- Find jobs with complete data (salary + skills)
SELECT job_id, job_title, company_name, salary_min, salary_max, skills_required
FROM jobs
WHERE has_salary = TRUE AND has_skills = TRUE
ORDER BY posted_date DESC
LIMIT 100;

-- Search by job title and location
SELECT job_id, job_title, company_name, location, salary_min, salary_max
FROM jobs
WHERE job_title ILIKE '%python%'
  AND location ILIKE '%Paris%'
  AND posted_date >= CURRENT_DATE - INTERVAL '14 days'
ORDER BY posted_date DESC;

-- Count jobs by source and quality
SELECT source,
       COUNT(*) as total,
       COUNT(CASE WHEN has_salary THEN 1 END) as with_salary,
       COUNT(CASE WHEN has_skills THEN 1 END) as with_skills,
       ROUND(AVG(data_quality_score), 2) as avg_quality
FROM jobs
GROUP BY source
ORDER BY total DESC;

-- Fuzzy search in job descriptions (trigram)
SELECT job_id, job_title, company_name
FROM jobs
WHERE job_description % 'machine learning'  -- Trigram similarity operator
ORDER BY similarity(job_description, 'machine learning') DESC
LIMIT 20;
```

---

### TABLE 2: model_versions

Stores metadata about trained TF-IDF models. Vectors themselves are stored as joblib files, not in the database.

```sql
CREATE TABLE model_versions (
    model_version VARCHAR(50) PRIMARY KEY,  -- e.g., "tfidf_v1", "tfidf_v2"

    -- Model type and location
    model_type VARCHAR(50) DEFAULT 'tfidf',
    vectorizer_path VARCHAR(500) NOT NULL,  -- Relative to models/ directory
    matrix_path VARCHAR(500) NOT NULL,      -- Sparse matrix path

    -- Model configuration metadata
    trained_on_jobs_count INTEGER,          -- How many jobs in training set
    feature_count INTEGER,                  -- Dimensionality (e.g., 10,000)
    ngram_range VARCHAR(20),                -- "(1, 2)" for unigrams + bigrams

    -- Lifecycle management
    status VARCHAR(50) DEFAULT 'active',    -- 'active', 'archived', 'deprecated'

    -- Audit trail
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),                -- Batch run that created this
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Column Definitions

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| model_version | VARCHAR(50) | NO | Primary key, format: tfidf_v1, tfidf_v2 |
| model_type | VARCHAR(50) | NO | Default 'tfidf' (future: 'bert', 'gpt', etc.) |
| vectorizer_path | VARCHAR(500) | NO | Path relative to models/ (e.g., tfidf/v1/vectorizer.joblib) |
| matrix_path | VARCHAR(500) | NO | Path relative to models/ (e.g., tfidf/v1/matrix.joblib) |
| trained_on_jobs_count | INTEGER | YES | Dataset size for reproducibility |
| feature_count | INTEGER | YES | Vector dimensionality (typically 10,000) |
| ngram_range | VARCHAR(20) | YES | Format "(1, 2)" to indicate unigrams + bigrams |
| status | VARCHAR(50) | NO | One of: active, archived, deprecated |
| created_at | TIMESTAMP | NO | When model was trained |
| created_by | VARCHAR(100) | YES | Batch ID or process name that created it |
| updated_at | TIMESTAMP | NO | Last status change |

#### Indexes (2 total)

```sql
-- Find active models quickly
CREATE INDEX idx_model_versions_status ON model_versions(status);

-- Audit trail, most recent first
CREATE INDEX idx_model_versions_created_at ON model_versions(created_at DESC);
```

#### Why Store Vectors as Files, Not in DB?

1. **Performance:** Sparse matrices are more efficient in joblib format than JSON/binary in DB
2. **Space:** 9.8 MB matrix vs. storing in database = slower queries
3. **Version control:** Easy to track model files separately (git-lfs, S3, etc.)
4. **Compatibility:** joblib format directly compatible with scikit-learn
5. **Simplicity:** Database stores only metadata, not large binary objects

#### Common Query Patterns

```sql
-- Get active model for use
SELECT model_version, vectorizer_path, matrix_path
FROM model_versions
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 1;

-- Find all model versions (for rollback capability)
SELECT model_version, status, created_at, trained_on_jobs_count
FROM model_versions
ORDER BY created_at DESC;

-- Archive old model when promoting new one
UPDATE model_versions
SET status = 'archived', updated_at = CURRENT_TIMESTAMP
WHERE model_version = 'tfidf_v1';

-- Audit: who created what and when
SELECT model_version, created_by, created_at, status
FROM model_versions
ORDER BY created_at DESC;
```

---

### TABLE 3: batch_runs

Audit trail for all batch processing pipeline runs. Tracks each stage and provides operational metrics.

```sql
CREATE TABLE batch_runs (
    batch_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_date DATE NOT NULL,

    -- Pipeline stage information
    stage VARCHAR(50),                  -- 'collect', 'validate', 'enrich', 'vectorize', 'export'
    status VARCHAR(50) NOT NULL,        -- 'pending', 'in_progress', 'success', 'failed'

    -- Processing statistics (count of records at each stage)
    jobs_collected INTEGER DEFAULT 0,   -- Stage 1: new jobs from API
    jobs_validated INTEGER DEFAULT 0,   -- Stage 2: passed quality checks
    jobs_enriched INTEGER DEFAULT 0,    -- Stage 3: cleaned and skills extracted
    jobs_vectorized INTEGER DEFAULT 0,  -- Stage 4: TF-IDF vectors created
    jobs_inserted INTEGER DEFAULT 0,    -- Stage 5: inserted into jobs table
    jobs_updated INTEGER DEFAULT 0,     -- Stage 5: updated existing records
    jobs_failed INTEGER DEFAULT 0,      -- Failed at any stage

    -- Error handling
    error_message TEXT,                 -- Exception details if failed

    -- Performance tracking
    execution_time_seconds INTEGER,     -- Total seconds for this stage

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT                          -- Additional context or warnings
);
```

#### Column Definitions

| Column | Type | Nullable | Notes |
|--------|------|----------|-------|
| batch_id | UUID | NO | Primary key, auto-generated per run |
| batch_date | DATE | NO | Date the batch was scheduled |
| stage | VARCHAR(50) | YES | One of: collect, validate, enrich, vectorize, export |
| status | VARCHAR(50) | NO | One of: pending, in_progress, success, failed |
| jobs_collected | INTEGER | NO | Default 0 |
| jobs_validated | INTEGER | NO | Default 0 |
| jobs_enriched | INTEGER | NO | Default 0 |
| jobs_vectorized | INTEGER | NO | Default 0 |
| jobs_inserted | INTEGER | NO | Default 0 |
| jobs_updated | INTEGER | NO | Default 0 |
| jobs_failed | INTEGER | NO | Default 0 |
| error_message | TEXT | YES | Stack trace or error details |
| execution_time_seconds | INTEGER | YES | Duration of this pipeline stage |
| created_at | TIMESTAMP | NO | When batch started |
| updated_at | TIMESTAMP | NO | When batch completed or failed |
| notes | TEXT | YES | Warnings, manual notes, or context |

#### Pipeline Stages

| Stage | Description | Input | Output | Success Criteria |
|-------|-------------|-------|--------|------------------|
| collect | Fetch from Adzuna API | Query, locations | New job records | jobs_collected > 0 |
| validate | Quality checks | Raw jobs | Validated count | jobs_validated >= jobs_collected * 0.9 |
| enrich | Clean, extract skills | Validated jobs | Enriched data | jobs_enriched == jobs_validated |
| vectorize | Build TF-IDF model | Cleaned jobs | Model version | jobs_vectorized == jobs_enriched |
| export | Insert to PostgreSQL | All above | DB records | jobs_inserted + jobs_updated == jobs_enriched |

#### Status Values

- **pending** - Batch scheduled but not started
- **in_progress** - Currently executing
- **success** - Completed without errors
- **failed** - Error occurred, manual review needed

#### Indexes (4 total)

```sql
-- Find batch by date (most recent first)
CREATE INDEX idx_batch_runs_batch_date ON batch_runs(batch_date DESC);

-- Monitor failed batches
CREATE INDEX idx_batch_runs_status ON batch_runs(status);

-- Track stage progress
CREATE INDEX idx_batch_runs_stage ON batch_runs(stage);

-- Audit trail (most recent first)
CREATE INDEX idx_batch_runs_created_at ON batch_runs(created_at DESC);
```

#### Common Query Patterns

```sql
-- Monitor latest batch run
SELECT batch_id, batch_date, stage, status,
       jobs_collected, jobs_enriched, jobs_inserted,
       execution_time_seconds, created_at
FROM batch_runs
ORDER BY created_at DESC
LIMIT 1;

-- Find failed batches for investigation
SELECT batch_id, batch_date, stage, status, error_message, updated_at
FROM batch_runs
WHERE status = 'failed'
ORDER BY updated_at DESC
LIMIT 10;

-- Daily statistics
SELECT batch_date,
       COUNT(*) as total_stages,
       COUNT(CASE WHEN status = 'success' THEN 1 END) as successful,
       COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
       SUM(jobs_inserted) + SUM(jobs_updated) as total_processed
FROM batch_runs
WHERE batch_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY batch_date
ORDER BY batch_date DESC;

-- Performance analysis (average execution time by stage)
SELECT stage,
       COUNT(*) as runs,
       ROUND(AVG(execution_time_seconds), 2) as avg_seconds,
       MIN(execution_time_seconds) as min_seconds,
       MAX(execution_time_seconds) as max_seconds
FROM batch_runs
WHERE status = 'success'
  AND batch_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY stage
ORDER BY avg_seconds DESC;

-- Error rate by stage
SELECT stage,
       COUNT(*) as total_runs,
       COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_runs,
       ROUND(100.0 * COUNT(CASE WHEN status = 'failed' THEN 1 END) / COUNT(*), 2) as failure_rate
FROM batch_runs
WHERE batch_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY stage
ORDER BY failure_rate DESC;
```

---

## Views (Pre-built Queries)

Simplify common queries with these views:

### VIEW 1: recent_jobs

```sql
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
```

**Use case:** Dashboard showing latest job postings

**Query:**
```sql
SELECT * FROM recent_jobs LIMIT 50;
```

### VIEW 2: complete_jobs

```sql
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
```

**Use case:** Training data for ML models (fully populated records only)

**Query:**
```sql
SELECT COUNT(*) FROM complete_jobs;  -- 80%+ of records typically
```

### VIEW 3: latest_batch_status

```sql
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
```

**Use case:** Monitoring dashboard to verify latest batch succeeded

**Query:**
```sql
SELECT * FROM latest_batch_status;
```

---

## Extensions Used

```sql
-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trigram similarity for fuzzy full-text search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
```

These enable:
- `uuid_generate_v4()` for automatic ID generation
- GIN indexes on TEXT columns for efficient fuzzy matching
- Trigram similarity operators (`%` for approximate match)

---

## Data Lifecycle

### Data Flow Through Tables

1. **collect_data.py** creates new job records
   - INSERT into `jobs` table with all fields
   - Log stage info in `batch_runs` (jobs_collected)

2. **Validation stage** applies quality checks
   - Mark records as validated
   - Log `batch_runs` (jobs_validated)

3. **clean_data.py** enriches records
   - UPDATE `jobs` with cleaned data, skills, salary parsing
   - Log `batch_runs` (jobs_enriched)

4. **nlp.py** creates TF-IDF model
   - INSERT into `model_versions` metadata
   - Save vectorizer.joblib and matrix.joblib to disk
   - Log `batch_runs` (jobs_vectorized)

5. **export stage** finalizes
   - INSERT new jobs or UPDATE existing ones in `jobs`
   - Log final `batch_runs` with jobs_inserted, jobs_updated

---

## Performance Considerations

### Current Capacity

- Jobs table: 8,737 rows (baseline)
- Average query response: < 50ms with indexes
- Full-text search: < 200ms

### Scaling (100K+ jobs)

If dataset grows 10x:

1. **Partitioning:** Partition `jobs` by `posted_date` (monthly)
   ```sql
   CREATE TABLE jobs_2026_01 PARTITION OF jobs FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
   ```

2. **Archiving:** Move old jobs to archive table
   ```sql
   CREATE TABLE jobs_archive AS SELECT * FROM jobs WHERE posted_date < CURRENT_DATE - INTERVAL '1 year';
   DELETE FROM jobs WHERE posted_date < CURRENT_DATE - INTERVAL '1 year';
   ```

3. **Column statistics:** Run ANALYZE regularly
   ```sql
   ANALYZE jobs;
   ```

---

## Backup & Recovery

### Regular Backups

```bash
# Backup entire database
docker exec ijob-postgres pg_dump -U jobadmin intelligent_jobs_db > backup.sql

# Restore from backup
docker exec ijob-postgres psql -U jobadmin intelligent_jobs_db < backup.sql

# Backup single table
docker exec ijob-postgres pg_dump -U jobadmin -t jobs intelligent_jobs_db > jobs_backup.sql
```

### Point-in-Time Recovery

Enabled by PostgreSQL WAL (Write-Ahead Logging):
- All changes logged to disk before applied
- Can recover to any point in time
- Requires WAL archiving setup in production

---

## Summary

This three-table schema provides:

- **Normalization:** Clear separation of concerns (jobs data, model metadata, batch audit)
- **Auditability:** Complete trace of all batch operations
- **Queryability:** Comprehensive indexes and views for common operations
- **Scalability:** Ready for 100K+ jobs with partitioning strategy
- **Reliability:** ACID transactions, backup strategy, recovery options

