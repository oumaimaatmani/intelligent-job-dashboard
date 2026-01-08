# Batch Pipeline - Intelligent Job Dashboard

**Last Updated:** 2026-01-08
**Orchestrator:** Apache Airflow 2.10.4
**Executor:** LocalExecutor
**Schedule:** Daily at 00:30 UTC

---

## Overview

The batch pipeline is a 5-stage automated workflow that runs daily to collect, validate, enrich, vectorize, and insert job market data into PostgreSQL. Each stage is tracked in the `batch_runs` table for auditability and monitoring.

```
[Stage 1] COLLECT ──> [Stage 2] VALIDATE ──> [Stage 3] ENRICH ──> [Stage 4] VECTORIZE ──> [Stage 5] EXPORT
   ↓                      ↓                       ↓                     ↓                      ↓
Adzuna API          Data Quality          Clean & Skills         TF-IDF Model         PostgreSQL
New Jobs            Checks                 Extraction             Version              Insert/Update
```

---

## Stage 1: COLLECT

**Executor:** `collect_data.py`
**Input:** Adzuna API credentials + search locations
**Output:** New job records (raw)
**Duration (SLA):** < 5 minutes

### Process

1. Read API credentials from environment or settings.yaml
2. Iterate over configured search locations (Paris, Lyon, Marseille, etc.)
3. Make paginated API requests (50 results/page, max 1000 per query)
4. Parse JSON response:
   - Extract: title, company, location, description, salary, url, posted_date
   - Generate deterministic UUID from (adzuna_id, url, title, company)
5. Append to in-memory buffer (deduplication on UUID)
6. Write batch to temporary CSV

### Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| API rate limit exceeded | Too many requests | Exponential backoff, max 3 retries |
| Network timeout | Connection lost | Retry up to 3 times with 5s delay |
| Invalid response | Malformed JSON | Log error, skip record, continue |
| Missing required field | API schema change | Log warning, set default value |

### Example Output

```csv
job_id,job_title,company_name,location,posted_date,salary_range,url,search_query
550e8400-e29b-41d4-a716-446655440000,Senior Data Engineer,TechCorp,Paris,2026-01-08,"60,000 - 80,000 EUR",https://adzuna.fr/...,data engineer
550e8400-e29b-41d4-a716-446655440001,Python Developer,StartupXYZ,Lyon,2026-01-07,"45,000 - 60,000 EUR",https://adzuna.fr/...,python developer
```

### Batch Logging

```sql
INSERT INTO batch_runs (batch_id, batch_date, stage, status, jobs_collected, execution_time_seconds, created_at)
VALUES (uuid_generate_v4(), CURRENT_DATE, 'collect', 'success', 245, 87, CURRENT_TIMESTAMP);
```

### Command Reference

```bash
# Manual collect (for testing)
python src/collect_data.py \
  --query "data engineer" \
  --locations "Paris,Lyon,Marseille" \
  --limit 100 \
  --output data/raw/job_listings_raw.csv
```

---

## Stage 2: VALIDATE

**Executor:** Airflow task + custom validation rules
**Input:** Raw job records from Stage 1
**Output:** Validated job records
**Duration (SLA):** < 2 minutes

### Validation Rules

| Rule | Check | Action on Fail |
|------|-------|----------------|
| Required fields | job_title, url not null | Skip record, increment jobs_failed |
| Title length | 10 < length < 500 | Skip record |
| URL format | Valid http(s) URL | Skip record |
| Date format | Valid ISO date or null | Set to CURRENT_DATE |
| Salary range | salary_min <= salary_max | Swap or set null |
| Location format | Non-empty string | Set to 'Unknown' |

### Process

1. Read temporary CSV from Stage 1
2. For each record:
   - Apply validation rules
   - Count passes/failures
   - Write valid records to validated buffer
3. Write validated records to temporary CSV
4. Log statistics

### Example Validation Report

```
Total records: 245
Valid records: 231
Failed validation: 14
  - Missing job_title: 3
  - Invalid URL: 5
  - Invalid date: 4
  - Other: 2
Pass rate: 94.3%
```

### Batch Logging

```sql
INSERT INTO batch_runs (batch_id, batch_date, stage, status, jobs_validated, execution_time_seconds)
VALUES (uuid_generate_v4(), CURRENT_DATE, 'validate', 'success', 231, 45);
```

---

## Stage 3: ENRICH

**Executor:** `clean_data.py`
**Input:** Validated job records
**Output:** Enriched and cleaned records
**Duration (SLA):** < 3 minutes

### Enrichment Steps

1. **Text Cleaning**
   - Remove HTML tags
   - Normalize whitespace
   - Lowercase for processing
   - Convert special characters (accents, etc.)

2. **Skills Extraction**
   - Regex-based keyword matching against 30+ tech skills
   - Match patterns like "Python", "python", "PYTHON", "python/django"
   - Fallback to spaCy for noun chunks if available
   - Output: comma-separated list of matched skills

3. **Salary Parsing**
   - Extract from patterns like "60,000 - 80,000 EUR"
   - Handle currency symbols (EUR, USD, etc.)
   - Validate: salary_min > 0, salary_max >= salary_min
   - Set has_salary flag = TRUE if successful

4. **Location Standardization**
   - Normalize French city names (remove arrondissements)
   - Convert to proper case (Paris, not PARIS)
   - Remove extra whitespace
   - Fallback: 'Remote' or 'Unknown' if unrecognized

5. **Computed Fields**
   - days_since_posted = today - posted_date
   - data_quality_score = ratio of non-null fields / total fields

### Skills Extraction Example

Input description:
```
"We seek experienced Python and SQL developer with AWS and Docker experience"
```

Output:
```
skills_required = "Python, SQL, AWS, Docker"
has_skills = TRUE
```

### Batch Logging

```sql
INSERT INTO batch_runs (batch_id, batch_date, stage, status, jobs_enriched, execution_time_seconds)
VALUES (uuid_generate_v4(), CURRENT_DATE, 'enrich', 'success', 229, 156);
```

### Code Reference

```python
# From clean_data.py
from src.clean_data import clean_jobs, extract_skills

cleaned_df = clean_jobs(validated_df)
enriched_df = extract_skills(cleaned_df)
enriched_df.to_csv('data/processed/enriched.csv', index=False)
```

---

## Stage 4: VECTORIZE

**Executor:** `nlp.py`
**Input:** Enriched job records
**Output:** TF-IDF model version + serialized vectors
**Duration (SLA):** < 4 minutes

### Process

1. **Text Preprocessing**
   - Lowercase all text
   - Remove URLs and email addresses
   - Remove punctuation (keep alphanumeric + spaces)
   - Lemmatization using NLTK WordNetLemmatizer
   - Remove stopwords (a, the, is, etc.)

2. **TF-IDF Vectorization**
   - Build TfidfVectorizer from all job descriptions
   - Configuration:
     - Max features: 10,000
     - N-gram range: (1, 2) - unigrams + bigrams
     - Min document frequency: 2
     - Max document frequency: 0.8
   - Fit to corpus of cleaned descriptions

3. **Sparse Matrix Creation**
   - Transform descriptions to sparse matrix (8,737 x 10,000)
   - Preserve memory efficiency (only non-zero values stored)

4. **Model Serialization**
   - Save vectorizer to `models/tfidf/vectorizer.joblib` (400 KB)
   - Save matrix to `models/tfidf/matrix.joblib` (9.8 MB)
   - Create version identifier: tfidf_v{timestamp}

5. **Model Metadata Logging**
   - Insert into `model_versions` table with:
     - model_version: "tfidf_v20260108_003000"
     - vectorizer_path: "tfidf/v20260108_003000/vectorizer.joblib"
     - matrix_path: "tfidf/v20260108_003000/matrix.joblib"
     - trained_on_jobs_count: 229
     - feature_count: 10,000
     - ngram_range: "(1, 2)"
     - status: "active"

### Example Model Version

```sql
SELECT * FROM model_versions WHERE status = 'active';

model_version        | tfidf_v20260108_003000
model_type           | tfidf
vectorizer_path      | tfidf/v20260108_003000/vectorizer.joblib
matrix_path          | tfidf/v20260108_003000/matrix.joblib
trained_on_jobs_count| 229
feature_count        | 10000
ngram_range          | (1, 2)
status               | active
created_by           | batch_run_20260108_000000
```

### Batch Logging

```sql
INSERT INTO batch_runs (batch_id, batch_date, stage, status, jobs_vectorized, execution_time_seconds)
VALUES (uuid_generate_v4(), CURRENT_DATE, 'vectorize', 'success', 229, 234);
```

### Code Reference

```python
# From nlp.py
from src.nlp import build_tfidf_model

vectorizer, matrix = build_tfidf_model(enriched_df['job_description'])
vectorizer_path = f"models/tfidf/v{timestamp}/vectorizer.joblib"
matrix_path = f"models/tfidf/v{timestamp}/matrix.joblib"

import joblib
joblib.dump(vectorizer, vectorizer_path)
joblib.dump(matrix, matrix_path)
```

---

## Stage 5: EXPORT

**Executor:** Custom export task
**Input:** Enriched records + model metadata
**Output:** Records inserted/updated in PostgreSQL
**Duration (SLA):** < 2 minutes

### Process

1. **Deduplication**
   - Check if job_id already exists in `jobs` table
   - Prepare INSERT for new jobs
   - Prepare UPDATE for existing jobs (update content only)

2. **Batch Insert**
   - Use COPY command for efficiency (1000 records/s vs 100 with INSERT)
   - Or use INSERT ... ON CONFLICT for idempotency

3. **Statistics Calculation**
   - Count jobs_inserted (new records)
   - Count jobs_updated (existing records updated)
   - Count jobs_failed (failed to insert/update)

4. **Finalize Batch Run**
   - Update `batch_runs` with final counts and status='success'
   - Calculate execution_time_seconds for entire pipeline

### SQL Example

```sql
-- Efficient bulk insert
COPY jobs (job_id, job_title, company_name, location, posted_date,
           job_description, skills_required, salary_min, salary_max,
           has_salary, has_skills, url, source, search_query,
           data_quality_score, created_at, updated_at)
FROM STDIN
WITH (FORMAT csv, DELIMITER ',');

-- Or with conflict handling
INSERT INTO jobs (job_id, job_title, ...)
VALUES (...)
ON CONFLICT (job_id) DO UPDATE SET
  job_title = EXCLUDED.job_title,
  job_description = EXCLUDED.job_description,
  updated_at = CURRENT_TIMESTAMP;
```

### Batch Logging

```sql
UPDATE batch_runs SET
  status = 'success',
  jobs_inserted = 198,
  jobs_updated = 31,
  jobs_failed = 0,
  execution_time_seconds = 512,
  updated_at = CURRENT_TIMESTAMP
WHERE batch_id = 'xxx-xxx-xxx-xxx' AND stage = 'export';
```

---

## Complete Pipeline Flow

### Happy Path (Success Scenario)

```
Time: 2026-01-08 00:30:00 UTC

[00:30] Stage 1 COLLECT
  - Fetch from Adzuna API: 245 jobs
  - Duration: 87 seconds
  - Status: SUCCESS
  - Log: batch_runs (jobs_collected=245)

[01:57] Stage 2 VALIDATE
  - Valid records: 231 jobs (94.3%)
  - Failed: 14 jobs (invalid format)
  - Duration: 45 seconds
  - Status: SUCCESS
  - Log: batch_runs (jobs_validated=231)

[02:42] Stage 3 ENRICH
  - Cleaned and enriched: 229 jobs
  - Skills extracted from 215 jobs
  - Salaries parsed from 118 jobs
  - Duration: 156 seconds
  - Status: SUCCESS
  - Log: batch_runs (jobs_enriched=229)

[04:38] Stage 4 VECTORIZE
  - Built TF-IDF matrix: 229 x 10,000
  - Model version: tfidf_v20260108_003000
  - Duration: 234 seconds
  - Status: SUCCESS
  - Log: batch_runs (jobs_vectorized=229)

[07:32] Stage 5 EXPORT
  - Inserted new jobs: 198
  - Updated existing: 31
  - Duration: 89 seconds
  - Status: SUCCESS
  - Log: batch_runs (jobs_inserted=198, jobs_updated=31)

[07:33] PIPELINE COMPLETE
  - Total time: 7 minutes 3 seconds
  - Total jobs processed: 229
  - Success rate: 100%
```

### Failure Scenario (Stage 3 Error)

```
Time: 2026-01-08 00:30:00 UTC

[00:30] Stage 1 COLLECT - SUCCESS (245 jobs)
[01:57] Stage 2 VALIDATE - SUCCESS (231 jobs)
[02:42] Stage 3 ENRICH - ERROR

ERROR LOG:
  stage: enrich
  status: failed
  error_message: "KeyError: 'job_description' in clean_jobs() - schema mismatch"
  jobs_enriched: 0 (failed at line 112)
  execution_time_seconds: 42
  created_at: 2026-01-08 00:34:24

ACTION:
  - Airflow retries automatically (max 3 retries with 60s backoff)
  - If all retries fail:
    - Send alert to ops team (Slack/email)
    - Rollback to previous batch_runs record
    - Do NOT proceed to Stage 4 (vectorize)
    - Do NOT update PostgreSQL
```

---

## Error Handling & Recovery

### Retry Strategy

Each stage has automatic retry logic:

```
First attempt fails
  ↓
Wait 60 seconds
  ↓
Retry attempt 2 (if transient error)
  ↓
Success → Continue
OR
Fail → Wait 120 seconds
  ↓
Retry attempt 3
  ↓
Success → Continue
OR
Fail → Alert + Stop pipeline
```

### Transient vs Permanent Errors

| Error Type | Example | Retryable | Action |
|------------|---------|-----------|--------|
| Transient | Network timeout, rate limit | Yes (3x) | Retry with backoff |
| Permanent | Schema mismatch, validation fail | No | Alert, require manual fix |
| Data | Invalid JSON from API | No | Log, skip record, continue |

### Manual Recovery

If pipeline fails:

1. **Check Airflow UI** (http://localhost:8080)
   - View DAG run history
   - Check task logs
   - Identify failed stage

2. **Check batch_runs table**
   ```sql
   SELECT * FROM batch_runs
   WHERE status = 'failed'
   ORDER BY created_at DESC
   LIMIT 1;
   ```

3. **Fix root cause**
   - Schema mismatch: Update data
   - Missing API key: Update credentials
   - Temporary service outage: Wait and retry

4. **Retry in Airflow UI**
   - Click failed task
   - Click "Clear task" (reset state)
   - Re-run DAG

---

## SLAs (Service Level Agreements)

### Individual Stage SLAs

| Stage | Normal Time | SLA | Alert Threshold |
|-------|-------------|-----|-----------------|
| collect | 90 sec | < 5 min | > 4 min |
| validate | 45 sec | < 2 min | > 1.5 min |
| enrich | 156 sec | < 5 min | > 4 min |
| vectorize | 234 sec | < 6 min | > 5 min |
| export | 89 sec | < 3 min | > 2.5 min |
| **Total** | **614 sec** | **< 15 min** | **> 12 min** |

### Success Criteria

- All 5 stages complete with status='success'
- Total records processed > 0
- jobs_failed == 0 (or < 5% of jobs_enriched)
- execution_time_seconds < SLA

### Monitoring Alerts

Alert triggers:

1. **Slow stage** (exceeds threshold)
   ```
   Alert: "Stage ENRICH exceeded SLA (7m > 5m)"
   Action: Monitor, may retry if still in window
   ```

2. **Stage failed** (status='failed')
   ```
   Alert: "Stage EXPORT failed with error: connection timeout"
   Action: Immediate notification, require manual intervention
   ```

3. **High error rate** (jobs_failed > threshold)
   ```
   Alert: "Stage ENRICH: 15% records failed validation"
   Action: Investigate data quality issue
   ```

4. **Pipeline timeout** (total > 15 min)
   ```
   Alert: "Batch pipeline exceeded 15-minute SLA"
   Action: Kill pipeline, alert ops team, investigate bottleneck
   ```

---

## Monitoring & Observability

### Real-time Dashboard Queries

```sql
-- Current batch status
SELECT stage, status, jobs_collected, jobs_enriched,
       jobs_failed, execution_time_seconds
FROM latest_batch_status();

-- Last 7 days success rate
SELECT
  batch_date,
  COUNT(*) as total_runs,
  COUNT(CASE WHEN status='success' THEN 1 END) as successful,
  ROUND(100.0 * COUNT(CASE WHEN status='success' THEN 1 END) / COUNT(*), 1) as success_rate
FROM batch_runs
WHERE batch_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY batch_date
ORDER BY batch_date DESC;

-- Average time per stage (last 30 days)
SELECT stage,
  COUNT(*) as runs,
  ROUND(AVG(execution_time_seconds), 2) as avg_sec,
  MAX(execution_time_seconds) as max_sec
FROM batch_runs
WHERE status='success' AND batch_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY stage
ORDER BY avg_sec DESC;

-- Recent errors
SELECT batch_id, batch_date, stage, error_message, created_at
FROM batch_runs
WHERE status='failed'
ORDER BY created_at DESC
LIMIT 10;
```

### Airflow Monitoring

Access Airflow UI: http://localhost:8080

Key screens:

1. **DAG Runs** - History of all pipeline executions
2. **Task Logs** - Detailed logs per stage
3. **Tree View** - Visual representation of DAG structure
4. **Gantt Chart** - Timeline showing duration of each stage

### Logging

All stages log to:
- **Airflow logs** - `/opt/airflow/logs/intelligent_job_dashboard/collect_jobs_dag/`
- **PostgreSQL batch_runs** - Complete metrics and errors
- **Application logs** - Stage-specific details (stdout/stderr)

Example log entry:
```
[2026-01-08 00:34:42] STAGE=collect | STATUS=in_progress | jobs_collected=0
[2026-01-08 00:35:10] STAGE=collect | STATUS=success | jobs_collected=245 | duration=88s
[2026-01-08 00:35:11] STAGE=validate | STATUS=in_progress | jobs_validated=0
[2026-01-08 00:35:56] STAGE=validate | STATUS=success | jobs_validated=231 | duration=45s
...
[2026-01-08 00:38:01] PIPELINE | STATUS=complete | total_duration=511s | success_rate=100%
```

---

## Configuration & Scheduling

### Airflow DAG Schedule

```python
# From infrastructure/airflow/dags/collect_jobs_dag.py

from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'retries': 1,
    'retry_delay': timedelta(minutes=1),
}

dag = DAG(
    'collect_jobs_daily',
    default_args=default_args,
    schedule_interval='30 0 * * *',  # 00:30 UTC daily
    start_date=datetime(2026, 1, 1),
    catchup=False,
)

# Task definitions here
```

### Manual Trigger

Run pipeline manually:

```bash
# Trigger via Airflow CLI
airflow dags trigger collect_jobs_daily --exec-date 2026-01-08

# Or via API
curl -X POST http://localhost:8080/api/v1/dags/collect_jobs_daily/dagRuns
```

---

## Disaster Recovery

### Data Rollback (Reverse Yesterday's Batch)

If bad data was inserted:

```sql
-- Delete records from today's batch run
DELETE FROM jobs
WHERE job_id IN (
  SELECT job_id FROM jobs
  WHERE created_at >= '2026-01-08 00:00:00'
);

-- Restore from backup
COPY jobs FROM 'backup_2026-01-07.csv' WITH (FORMAT csv);
```

### Model Rollback (Use Previous Model)

If new model performs poorly:

```sql
-- Archive new model
UPDATE model_versions SET status='archived'
WHERE model_version='tfidf_v20260108_003000';

-- Reactivate previous model
UPDATE model_versions SET status='active'
WHERE model_version='tfidf_v20260107_003000';
```

---

## Summary

The batch pipeline provides:

- **Reliability:** Automatic retries, error handling, transaction safety
- **Auditability:** Complete trace in `batch_runs` table
- **Observability:** Real-time monitoring via Airflow UI and SQL queries
- **Scalability:** Efficient bulk operations, handles 1000+ records
- **Safety:** Rollback capability, conflict resolution, data validation

Next stages will build Airflow DAGs to implement each stage as production-ready tasks.

