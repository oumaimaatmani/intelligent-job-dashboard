# Technical Decisions - Intelligent Job Dashboard

**Last Updated:** 2026-01-08
**Decision Status:** Approved for Phase 3+ Implementation
**Related Documents:** architecture.md, database_schema.md, batch_pipeline.md

---

## Overview

This document outlines the major technical decisions made during the infrastructure design phase, with clear trade-off analysis and rationale.

---

## Decision 1: PostgreSQL as Primary Database

### The Decision

**Selected:** PostgreSQL 15 (open-source relational database)
**Rejected Alternatives:** MySQL, MongoDB, Elasticsearch, SQLite, DynamoDB

### Decision Matrix

| Criterion | PostgreSQL | MySQL | MongoDB | Elasticsearch | SQLite | DynamoDB |
|-----------|-----------|-------|---------|---------------|--------|----------|
| **ACID Compliance** | Yes | Yes | No | No | Yes | Limited |
| **Complex Queries** | Yes | Yes | Limited | No | Yes | No |
| **Full-text Search** | Yes (GIN) | Limited | Limited | Yes | Limited | No |
| **Scalability** | Good (replication) | Good | Excellent | Excellent | None | Excellent |
| **Cost** | Free | Free | Free | Paid/Free | Free | Paid |
| **Learning Curve** | Moderate | Easy | Easy | Steep | Easy | Steep |
| **Production Ready** | Yes | Yes | Yes | Yes | No | Yes |
| **Multi-region** | Possible | Possible | Built-in | Built-in | No | Built-in |

### Trade-offs

#### PostgreSQL Advantages

- **ACID Guarantees:** Batch runs either complete entirely or not at all (no partial data)
- **Complex Joins:** Can query jobs + batch_runs for analytics
- **Full-text Search:** GIN indexes with trigram similarity for fuzzy matching
- **Indexes:** Advanced index types (partial, expression, GIN)
- **JSON Support:** JSONB columns for semi-structured data (future)
- **Open Source:** No vendor lock-in, active community
- **Cost:** Free to run anywhere

Example - Batch atomicity:

```sql
BEGIN TRANSACTION;
  INSERT INTO jobs (...) VALUES (...);     -- 198 new jobs
  INSERT INTO jobs (...) VALUES (...);     -- 31 updates
  INSERT INTO batch_runs (...) VALUES (...); -- Audit trail
COMMIT;  -- All succeed or all rollback if error
```

#### PostgreSQL Disadvantages

- **Not designed for billions of rows:** Partitioning required at 100M+ scale
- **Scalability complexity:** Read replicas work, but sharding requires external tools
- **Learning curve:** More complex than MySQL for simple use cases

#### Why Not MySQL?

- Lacks JSONB support
- No GIN indexes
- Less sophisticated query planner
- Smaller ecosystem of extensions

#### Why Not MongoDB?

- No ACID transactions until recent versions
- Schema flexibility not needed for job data
- Aggregation pipeline has learning curve
- Harder to track batch run audit trail

Example - Why ACID matters:

```
Without ACID (MongoDB):
├─ Insert 198 new jobs ✓
├─ Insert 31 updates... ERROR
├─ Result: Inconsistent state (some new jobs exist, audit trail missing)
└─ Manual cleanup required

With ACID (PostgreSQL):
├─ BEGIN
├─ Insert 198 new jobs ✓
├─ Insert 31 updates... ERROR
├─ ROLLBACK (all changes undone)
└─ Automatic recovery, no manual cleanup
```

#### Why Not Elasticsearch?

- Designed for full-text search, not transactional data
- No ACID guarantees
- Overkill for job description search (trigram sufficient)
- Higher operational complexity

#### Why Not SQLite?

- Single file, no concurrent access
- No replication
- Not suitable for multi-user scenarios
- Okay for desktop tools, not production systems

#### Why Not DynamoDB?

- Vendor lock-in (AWS only)
- Expensive for small-scale use
- Limited query types (KV store primarily)
- Complex pricing model

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| PostgreSQL 15 becomes obsolete | Docker image ensures reproducibility; easy to upgrade |
| ACID overhead slows performance | Not a concern at 8K-100K rows; indexes handle it |
| Need to scale beyond single instance | Plan for read replicas and partitioning (Phase 2) |

### Related Documentation

- See `docs/database_schema.md` for full schema details
- See `docs/architecture.md` for scalability strategy

---

## Decision 2: Redis for Caching Layer

### The Decision

**Selected:** Redis 7 (in-memory key-value store with persistence)
**Rejected Alternatives:** Memcached, Local Python cache, DynamoDB, Varnish

### Decision Matrix

| Criterion | Redis | Memcached | Local Cache | DynamoDB | Varnish |
|-----------|-------|-----------|-------------|----------|---------|
| **Speed** | < 1ms | < 1ms | < 0.1ms | 10-100ms | Variable |
| **Persistence** | Yes (AOF/RDB) | No | No | Yes | No |
| **Data Structures** | Rich (lists, sets, hashes) | Strings only | Any Python object | Limited | Limited |
| **Clustering** | Yes (Cluster mode) | No | N/A | Yes | Limited |
| **Pub/Sub** | Yes | No | N/A | No | No |
| **Cost** | Free | Free | Free | Paid | Free |
| **Use Cases** | Cache, sessions, queue | Cache only | Cache only | Full DB | HTTP cache |

### Trade-offs

#### Redis Advantages

- **Data Structures:** Supports lists, sets, hashes (not just strings)
- **Persistence:** AOF/RDB options for durability
- **Pub/Sub:** Event-driven invalidation
- **Atomic Operations:** INCR, LPUSH, etc. for counters
- **Clustering:** Redis Cluster for horizontal scaling
- **Open Source:** Widely adopted, strong community

Example - Caching recent jobs:

```python
# Set cache with 1-hour TTL
redis.setex('recent_jobs', 3600, json.dumps(jobs))

# Retrieve from cache (< 1ms)
cached = redis.get('recent_jobs')
if cached:
    return json.loads(cached)  # Cache hit

# DB query fallback (50ms)
return query_postgres('SELECT * FROM jobs WHERE posted_date > NOW() - INTERVAL 7 days')
```

#### Redis Disadvantages

- **Requires tuning:** Memory limits, eviction policies, persistence trade-offs
- **Single-threaded:** Can only use 1 CPU core (sufficient for this use case)
- **No query language:** Simple key-value access patterns only

#### Why Not Memcached?

- No persistence (lost on restart)
- Can't store complex data structures
- No pub/sub
- Dead project (less active development)

#### Why Not Local Python Cache?

- Lost on container restart
- Not distributed (multi-instance deployments problematic)
- Hard to invalidate across processes
- Debugging difficult

```python
# Problematic for scaling
cache = {}  # Local dict

# Instance A caches something
cache['jobs'] = [...]

# Instance B has different cache
cache['jobs']  # Missing! Stale data!
```

#### Why Not DynamoDB?

- 10-100ms latency (1000x slower than Redis)
- Vendor lock-in (AWS only)
- Higher cost than free Redis
- Designed for durable storage, not caching

#### Why Not Varnish?

- HTTP-only (works for web servers, not Python apps)
- Not suitable for application-level caching
- Harder to integrate with Airflow/Airflow

### Use Cases

1. **Query Result Caching**
   - Cache frequently searched jobs (< 1ms retrieval)
   - TTL: 1 hour (refresh automatically)

2. **Session Store** (Future)
   - Store user sessions when web UI built
   - TTL: 24 hours per session

3. **Model Cache** (Future)
   - Pre-load vectorizer in memory
   - Fast recommendations without disk I/O

4. **Rate Limiting** (Future)
   - Track API requests per user
   - Atomic INCR operations

5. **Airflow Metadata**
   - Airflow uses Redis internally for task state
   - Ensures distributed task tracking

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Cache data becomes stale | TTL on all keys; manual invalidation via Airflow |
| Redis crashes, cache lost | AOF persistence (every write logged) + RDB snapshots |
| Need to scale beyond single instance | Plan Redis Cluster for Phase 2 |

### Related Documentation

- See `docs/architecture.md` for caching layer diagram
- See `docs/batch_pipeline.md` for invalidation strategy

---

## Decision 3: Daily Batch vs Real-time Processing

### The Decision

**Selected:** Daily batch (scheduled at 00:30 UTC)
**Rejected Alternatives:** Real-time streaming, Hourly batch, On-demand

### Decision Matrix

| Criterion | Daily Batch | Real-time | Hourly | On-demand |
|-----------|------------|-----------|--------|-----------|
| **Data Freshness** | 24 hours | Minutes | 1 hour | Immediate |
| **Resource Cost** | Low | High | Medium | Medium |
| **Complexity** | Low | High | Medium | Medium |
| **Error Recovery** | Simple | Complex | Medium | Complex |
| **Suitable For** | Analytics | Live feeds | Alerts | Ad-hoc |
| **Scalability** | Easy | Hard | Medium | Hard |
| **Consistency** | High | Low | High | Low |

### Trade-offs

#### Daily Batch Advantages

- **Low resource cost:** Run once per day (~7-8 minutes), then idle
- **Simple recovery:** Whole batch fails or succeeds; easy to retry
- **High consistency:** All jobs from same time window
- **Auditability:** Single batch_runs entry per day
- **Operational simplicity:** Fewer monitoring/alerting rules

Example - Cost comparison:

```
Daily batch approach:
├─ 7 minutes × 24 hours per day = 7 minutes compute
├─ Cost: < $1/month (on-demand)
└─ Infra: Single container running, mostly idle

Real-time approach:
├─ Continuous processing (24/7)
├─ Cost: $30-100+ per month
└─ Infra: Multiple containers, queuing system, scaling logic
```

#### Daily Batch Disadvantages

- **Data lag:** Jobs from Adzuna older by 24 hours
- **Bursty load:** All processing compressed into 8 minutes
- **Miss updates:** If job posting updated during day, won't see until tomorrow

#### Why Not Real-time Streaming?

- Adzuna API doesn't provide webhooks
- Would need polling (defeats the purpose)
- Overkill for job market (changes every few hours, not seconds)
- Significantly more complex: Kafka/Kinesis + stream processors

Example - Why polling is inefficient:

```
Real-time approach with polling:
├─ Check Adzuna API every 5 minutes
├─ 288 API calls per day
├─ 99% of calls return "no new jobs" (wasted)
├─ Cost: $50-200/month just on API calls
└─ Result: Mostly stale data anyway

Daily batch:
├─ Check Adzuna API once per day
├─ 1 API call per day
├─ Get all new jobs in one shot
├─ Cost: < $1/month
└─ Result: Consistent, fresh data
```

#### Why Not Hourly?

- Not enough benefit over daily
- 24x increase in resource cost
- Still has same data lag issues (50-minute lag)
- Overkill for job market dynamics

#### Why Not On-demand?

- Poor user experience ("click refresh" for jobs)
- No predictability for operations team
- Same resource cost as real-time
- Hard to debug intermittent issues

### Implementation Details

**Daily Batch Schedule:**
```
Time: 00:30 UTC (chosen to avoid peak hours)
Reason: Most users in Paris are sleeping (22:30 local time)

Retry Policy: If failed
├─ Automatic retry at 06:30 UTC
├─ If still failed, manual review at 12:00 UTC
└─ Fallback: Manual trigger if needed
```

### Data Freshness Guarantee

```
Adzuna posts jobs continuously (24/7)
                    │
                    │ (up to 24 hour lag)
                    │
             00:30 UTC batch runs
                    │
          Database updated with:
          ├─ All new jobs from Adzuna
          ├─ All deleted jobs from Adzuna
          ├─ All updated jobs from Adzuna
                    │
          Client query (any time):
          └─ Gets jobs from up to 24 hours ago
               ↓
          Acceptable for: Job search, analytics, dashboards
          Not acceptable for: Live job alerts
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Batch fails, missed day of jobs | Automatic retry; manual override option; alerts |
| Users expect real-time data | Document 24-hour lag in UI/API |
| Need to switch to real-time | Modular design allows adding streaming later |

### Scalability

Easy to upgrade later:

```
Phase 1 (now): Daily batch → 1 DAG run per day
Phase 2 (6 mo): Hourly batch → 24 DAG runs per day
Phase 3 (1 year): Mini-batch (every 30 min) → 48 DAG runs per day
Phase 4 (2 years): Near real-time (every 5 min) → 288 DAG runs per day
Phase 5 (3 years): Full streaming → Kafka + Spark Streaming
```

### Related Documentation

- See `docs/batch_pipeline.md` for detailed scheduling
- See `docs/architecture.md` for scalability path

---

## Decision 4: File Storage for TF-IDF Vectors

### The Decision

**Selected:** Store vectors as joblib files in models/ directory
**Rejected Alternatives:** Store in PostgreSQL BYTEA, Store in Redis, Store in S3

### Decision Matrix

| Criterion | Joblib Files | PostgreSQL BYTEA | Redis | S3 |
|-----------|----------|-----------------|-------|-----|
| **Access Speed** | Fast (disk) | Slow (network+DB) | Very fast | Very slow |
| **Storage Size** | 9.8 MB | 9.8 MB | 9.8 MB | 9.8 MB |
| **Version Control** | Easy (git-lfs) | Hard (DB blob) | Hard (cache) | Easy (S3 versioning) |
| **Backup** | With code (git) | With DB backups | None | S3 versioning |
| **Reproducibility** | Perfect | Perfect | Lossy | Perfect |
| **Cost** | Free | Free | Free* | $0.02/month for 9.8 MB |
| **Concurrent Access** | Safe (read-only) | Safe | Fast | Safe |

### Trade-offs

#### Joblib Files Advantages

- **scikit-learn native:** Joblib is optimized for scikit-learn objects
- **Fast loading:** Direct deserialization (< 100ms)
- **Sparse matrix support:** Preserves sparsity (saves 90% space)
- **Version control:** Check into git-lfs alongside code
- **Reproducibility:** Exact same object every time
- **No database bloat:** Keeps PostgreSQL for transactional data only

Example - Why sparse matrices matter:

```
Dense storage (numpy array): 8,737 × 10,000 = 87M floats = 340 MB
Sparse storage (joblib): Only non-zero values = 9.8 MB
Savings: 97% reduction!

Loading time:
- From disk (joblib): 50ms
- From PostgreSQL: 500ms (network + parsing)
- From Redis: 100ms (network)
```

#### Joblib Files Disadvantages

- **Not queryable:** Can't SQL "SELECT * FROM vectorizer WHERE feature = 'python'"
- **Requires file system:** Not cloud-database compatible (can be mitigated with S3)
- **Manual version management:** Need code to track model versions

#### Why Not PostgreSQL BYTEA?

- Large BLOBs slow down DB queries
- Database bloat (9.8 MB per model version)
- Harder to version control
- Network overhead (query DB → deserialize → load)

Example - Why this is slow:

```sql
-- Retrieve vectorizer from DB
SELECT vectorizer FROM model_versions WHERE model_version='tfidf_v1';

-- Takes 500ms:
-- 1. Query PostgreSQL (50ms)
-- 2. Network transfer (50ms)
-- 3. Deserialize BYTEA format (100ms)
-- 4. Reconstruct object (300ms)
-- Total: 500ms

-- vs joblib file (50ms):
-- 1. Load from disk (30ms)
-- 2. Joblib deserialize (20ms)
-- Total: 50ms ← 10x faster!
```

#### Why Not Redis?

- Cache should not be primary storage
- Loses models on restart (even with persistence)
- Models don't fit in memory alongside other cache
- Defeats purpose of caching (models are large, but not frequently updated)

#### Why Not S3?

- Good for backups and archiving
- Not suitable as primary storage
- Slower than local disk (100ms → 500ms+)
- Cost: $0.02/month (negligible, but adds complexity)
- Future option: Keep hot model locally, archive old versions to S3

### Model Versioning Strategy

**Current (Phase 1):**
```
models/tfidf/vectorizer.joblib
models/tfidf/matrix.joblib
```

**Better (Phase 2):**
```
models/tfidf/v1/vectorizer.joblib
models/tfidf/v1/matrix.joblib
models/tfidf/v2/vectorizer.joblib
models/tfidf/v2/matrix.joblib
models/tfidf/active  # symlink to v2/
```

**Production (Phase 3+):**
```
git-lfs: Store large files in external storage
s3://models/tfidf/v1/
s3://models/tfidf/v2/
model_versions table: Tracks which is active
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Models lost if disk fails | Backup to S3 automatically |
| Version conflicts | Semantic versioning (tfidf_v1, tfidf_v2) + git-lfs |
| Need to query models | model_versions table has metadata (feature_count, etc.) |

### Related Documentation

- See `docs/database_schema.md` for model_versions table design
- See `docs/batch_pipeline.md` for Stage 4 (vectorize)

---

## Decision 5: Model Versioning Strategy

### The Decision

**Selected:** Semantic versioning (tfidf_v1, tfidf_v2, etc.) + metadata in database
**Rejected Alternatives:** Timestamps, Git hash, Immutable model

### Decision Matrix

| Criterion | Semantic | Timestamp | Git Hash | Immutable |
|-----------|----------|-----------|----------|-----------|
| **Human readable** | Yes | Yes | No | N/A |
| **Sortable** | Yes | Yes | Yes | N/A |
| **Rollback easy** | Yes | Yes | Yes | No |
| **A/B testing** | Yes | Yes | Yes | No |
| **Audit trail** | Good | Excellent | Good | Poor |
| **Implementation** | Simple | Simple | Complex | Complex |

### Trade-offs

#### Semantic Versioning Advantages

- **Human readable:** "tfidf_v1" vs "20260108_003000_abc123"
- **Rollback capability:** "Switch from v2 back to v1"
- **A/B testing:** "Model v1 vs v2 comparison queries"
- **Simplicity:** Easy to implement and understand

Example - Easy rollback:

```sql
-- Current (underperforming)
UPDATE model_versions SET status='archived' WHERE model_version='tfidf_v2';
UPDATE model_versions SET status='active' WHERE model_version='tfidf_v1';

-- All clients now use v1 automatically
```

#### Semantic Versioning Disadvantages

- **Manual version management:** Need code to increment
- **Not timestamp-based:** Can't tell which is newer just from name

#### Why Not Timestamps?

- Harder to reference in conversation ("that model from 20260108_003000")
- More error-prone in commands
- Same complexity as semantic, less human-friendly

#### Why Not Git Hash?

- Requires integrating git into model pipeline
- Not human-readable (commit hash is random-looking)
- Doesn't indicate evolution/ordering without lookup

#### Why Not Immutable Model?

- No rollback capability (models can regress)
- Can't do A/B testing
- Forces deletion of bad models (no history)

### Model Metadata Storage

```sql
INSERT INTO model_versions (
  model_version,
  model_type,
  vectorizer_path,
  matrix_path,
  trained_on_jobs_count,
  feature_count,
  ngram_range,
  status,
  created_by,
  created_at
)
VALUES (
  'tfidf_v20260108',
  'tfidf',
  'tfidf/v20260108/vectorizer.joblib',
  'tfidf/v20260108/matrix.joblib',
  229,          -- Reproducibility
  10000,        -- Performance tracking
  '(1,2)',      -- Hyperparameters
  'active',     -- Lifecycle
  'batch_20260108_003000', -- Auditability
  CURRENT_TIMESTAMP
);
```

### Status Lifecycle

```
Active ──> Deprecated ──> Archived
 │
 └─────────> Rollback to Active (if needed)

States:
- active: Current model in use
- deprecated: Keep available but not used (30-day grace period)
- archived: Old model, kept for audit trail only (1-year retention)
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Version number conflicts | Sequential numbering + database constraint |
| Model regression undetected | A/B testing framework to compare models |
| Old models removed accidentally | Archive status + retention policy |

### Related Documentation

- See `docs/database_schema.md` for model_versions table
- See `docs/batch_pipeline.md` for Stage 4 (vectorize)

---

## Decision 6: Apache Airflow for Orchestration

### The Decision

**Selected:** Apache Airflow 2.10.4 with LocalExecutor
**Rejected Alternatives:** Cron + shell scripts, Luigi, dbt, Kubernetes CronJobs, Prefect

### Decision Matrix

| Criterion | Airflow | Cron | Luigi | dbt | K8s CronJob | Prefect |
|-----------|---------|------|-------|-----|-----------|---------|
| **DAG visualization** | Yes | No | Yes | No | No | Yes |
| **Error handling** | Excellent | Minimal | Good | Limited | Good | Excellent |
| **Monitoring UI** | Yes | No | Basic | No | No | Yes |
| **Community** | Large | N/A | Small | Large | Large | Growing |
| **Learning curve** | Moderate | Easy | Steep | Moderate | Steep | Steep |
| **Cost** | Free | Free | Free | Free/Paid | Free (with K8s) | Free/Paid |
| **Production ready** | Yes | Yes | Yes | Yes | Yes | Yes |

### Trade-offs

#### Airflow Advantages

- **DAG-based thinking:** Visual representation of pipeline
- **Comprehensive monitoring:** Web UI shows all runs, logs, metrics
- **Error handling:** Retry logic, backoff strategies, alerting
- **Large ecosystem:** 200+ provider integrations (AWS, GCS, Slack, etc.)
- **Community:** Widely adopted, mature project (Airbnb originated)

Example - Airflow DAG definition:

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

dag = DAG(
    'collect_jobs_daily',
    schedule_interval='30 0 * * *',  # 00:30 UTC daily
    default_args={
        'retries': 2,
        'retry_delay': timedelta(minutes=1),
    }
)

task_collect = PythonOperator(
    task_id='collect',
    python_callable=collect_jobs,
    dag=dag
)

task_validate = PythonOperator(
    task_id='validate',
    python_callable=validate_jobs,
    dag=dag,
    depends_on_past=False
)

task_collect >> task_validate  # Dependency
```

#### Airflow Disadvantages

- **Learning curve:** Concepts like DAGs, operators, providers
- **Operational overhead:** Need to monitor Airflow itself
- **Complexity:** Overkill for simple cron job
- **Resource usage:** Scheduler + webserver add overhead

#### Why Not Cron + Shell Scripts?

- No monitoring (run silently)
- No retry logic (fails silently)
- Hard to debug (output lost)
- No alerting (manual log checking)
- Spaghetti dependencies (hard to track)

```bash
# Cron approach (fragile)
0 0 * * * /home/data/collect.sh > /tmp/collect.log 2>&1
0 1 * * * /home/data/validate.sh > /tmp/validate.log 2>&1

# If collect.sh fails, validate.sh still runs (wrong!)
# If both fail, no one knows until next morning
```

#### Why Not Luigi?

- Small community
- Less mature than Airflow
- Limited monitoring compared to Airflow
- Documentation not as extensive

#### Why Not dbt?

- Designed for analytics + transformation (SQL-focused)
- Not suitable for external API integration
- No Python operator (our collect stage is Python)
- Opinionated for DBT-specific workflows

#### Why Not Kubernetes CronJobs?

- Requires Kubernetes (not available in local Docker Compose)
- More complexity than needed for this project
- Monitoring spread across multiple tools (kubectl, logs, etc.)
- Better suited for larger infrastructures

#### Why Not Prefect?

- Newer project (less battle-tested)
- Requires Prefect Cloud or self-hosted
- Overkill for current project scale
- Similar features to Airflow but less community support

### Airflow Configuration

```yaml
# Key settings for intelligent_jobs_db
Executor: LocalExecutor  # Single machine (scale later with CeleryExecutor)
Database: PostgreSQL     # Stores DAG state and metadata
Scheduler interval: 10s  # Check for tasks every 10 seconds
Parallelism: 1          # Run 1 task at a time locally
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Airflow itself crashes | Restart container (data persisted in PostgreSQL) |
| DAG has circular dependency | Validation at parse time, caught immediately |
| Task succeeds but produces bad data | Downstream validation catches it |

### Upgrade Path

```
Phase 1 (now): LocalExecutor + 1 machine
Phase 2 (1 year): CeleryExecutor + worker nodes (parallel tasks)
Phase 3 (2 years): Kubernetes Executor + pod-per-task
```

### Related Documentation

- See `docs/batch_pipeline.md` for DAG structure
- See `docs/architecture.md` for orchestration layer

---

## Decision 7: Python for ETL Pipeline

### The Decision

**Selected:** Python 3.11 with Pandas, Regex, NLTK
**Rejected Alternatives:** Scala (Spark), SQL procedures, Node.js, Go

### Decision Matrix

| Criterion | Python | Scala | SQL | Node.js | Go |
|-----------|--------|-------|-----|---------|-----|
| **Data wrangling** | Excellent | Good | Excellent | Fair | Fair |
| **NLP support** | Excellent | Fair | None | Fair | Fair |
| **API integration** | Excellent | Good | Limited | Excellent | Excellent |
| **Team expertise** | High | Low | Medium | Low | Low |
| **ML ecosystem** | Best | Good | None | Fair | Fair |
| **Development speed** | Fast | Medium | Medium | Fast | Medium |
| **Performance** | Medium | High | High | Medium | High |

### Trade-offs

#### Python Advantages

- **Pandas:** Industry standard for tabular data, 100x faster than loops
- **NLP libraries:** NLTK, spaCy, scikit-learn all mature
- **API integration:** requests library, simple HTTP handling
- **Team fit:** Data engineers know Python
- **ML ecosystem:** scikit-learn, TensorFlow, PyTorch all Python
- **Development speed:** Write 50 lines Python vs 500 lines Scala

Example - Pandas efficiency:

```python
# Python (10ms)
df['salary_min'] = df['salary_range'].str.extract(r'(\d+)')[0]

# SQL (100ms+)
UPDATE jobs SET salary_min = CAST(SUBSTRING_INDEX(salary_range, '-', 1) AS INT);

# Scala (200ms)
df.withColumn("salary_min", split(col("salary_range"), "-").getItem(0).cast("int"))
```

#### Python Disadvantages

- **Performance:** Slower than compiled languages (Scala, Go)
- **Multi-threading:** GIL limits parallelism (not an issue for our sequential pipeline)
- **Memory usage:** More than Go or Scala
- **Startup time:** 100ms vs 10ms for compiled languages

Not a concern for our use case (runs once per day for 8 minutes).

#### Why Not Scala (Spark)?

- Overkill for 8K rows
- Requires Spark cluster or local mode
- Higher operational complexity
- Steeper learning curve
- Setup time > execution time for our data size

```
Spark startup: 5 seconds
Spark processing: 5 seconds
Spark shutdown: 3 seconds
Total: 13 seconds

Python Pandas:
Python startup: 0.5 seconds
Pandas processing: 2 seconds
Total: 2.5 seconds ← 5x faster!
```

#### Why Not SQL Procedures?

- SQL not designed for external API integration
- Complex text preprocessing logic is hard in SQL
- Maintenance burden (SQL in database, Python in code)
- Less readable than Python for ETL

#### Why Not Node.js?

- Designed for async I/O (web servers)
- Data wrangling libraries not as mature as Python
- Less ML ecosystem
- Team expertise in Python, not JavaScript

#### Why Not Go?

- Strong performance, but not needed for our use case
- Smaller ecosystem for data work
- Team doesn't know Go
- No advantage over Python for this project

### Technology Choices Within Python

```python
# Imports used in current pipeline
import pandas as pd          # Data manipulation
import re                    # Skill extraction (regex)
import nltk                  # Lemmatization
import scikit-learn          # TF-IDF
import requests              # Adzuna API
from joblib import dump      # Model serialization

# All open-source, battle-tested, widely adopted
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Performance bottleneck | Profile code; optimize hot paths; scale to Spark later if needed |
| Python version compatibility | Docker pins version (3.11); easy to upgrade |
| Library compatibility | requirements.txt locks versions; test upgrades in staging |

### Scalability

If Python becomes bottleneck (100K+ jobs):

```
Option 1: More parallelism (Python 3.13+ removes GIL)
Option 2: Migrate to PySpark (distributed Python)
Option 3: Rewrite bottleneck in Cython/Go (10% of code)
Option 4: Keep Python, add more workers (CeleryExecutor)
```

### Related Documentation

- See `docs/batch_pipeline.md` for pipeline implementation
- See `docs/architecture.md` for technology stack

---

## Decision 8: scikit-learn TF-IDF for Vectorization

### The Decision

**Selected:** scikit-learn TfidfVectorizer (10K features, bigrams)
**Rejected Alternatives:** Word2Vec, BERT embeddings, FastText, Custom n-gram

### Decision Matrix

| Criterion | TF-IDF | Word2Vec | BERT | FastText | Custom |
|-----------|--------|----------|------|----------|--------|
| **Memory** | 10 MB | 500+ MB | 1 GB+ | 100 MB | Varies |
| **Speed (inference)** | < 1ms | 10ms | 100ms+ | 5ms | Varies |
| **Training** | Fast | Medium | Slow | Fast | Varies |
| **Interpretability** | High | Medium | Low | Medium | Varies |
| **Sparsity** | 99% sparse | Dense | Dense | Dense | Varies |
| **Task fit** | Best | Good | Excellent | Good | Varies |
| **Production ready** | Yes | Yes | Yes | Yes | Maybe |

### Trade-offs

#### TF-IDF Advantages

- **Sparse representation:** Only non-zero values stored (10 MB vs 500+ MB)
- **Interpretable:** Can see which words matter (feature importance)
- **Fast inference:** < 1ms per recommendation (real-time capable)
- **No training needed:** Pre-built on corpus
- **Proven:** Used in production at scale for 20+ years

Example - Why sparsity matters:

```
TF-IDF (sparse):
├─ 8,737 documents × 10,000 features
├─ 99% zeros (sparse matrix)
├─ Stored size: 9.8 MB
└─ Dot product: < 1ms

BERT (dense):
├─ 8,737 documents × 768 dimensions
├─ All values stored (dense matrix)
├─ Stored size: 30 MB+
├─ GPU inference: 50-100ms
└─ CPU inference: 500ms+
```

#### TF-IDF Disadvantages

- **Not semantic:** Only word frequency, not meaning
- **No context:** "Python" and "snake" different despite similar domains
- **Bag-of-words limitation:** Order not considered
- **Domain-specific:** Need to retrain for new domains

Not critical for job matching (word presence is strong signal).

#### Why Not Word2Vec?

- Semantic similarity (good) but:
- Dense vectors (inefficient)
- Slower inference (10ms vs < 1ms)
- Requires training on large corpus
- Larger memory footprint (500 MB)
- Overkill for job matching

#### Why Not BERT?

- State-of-the-art but:
- Massive model (1 GB+)
- Slow inference (100ms+ per recommendation)
- Requires GPU for speed
- Overkill for job market (not complex language tasks)
- Expensive to deploy

Example - Why BERT overkill:

```
Job A: "Python developer with 5 years experience"
Job B: "Senior Python engineer with 5 years background"

TF-IDF says: Very similar (same words, same domain) ✓
BERT says: Very similar (semantic meaning) ✓

For this task, TF-IDF is 10x faster and 100x smaller
```

#### Why Not FastText?

- Faster than Word2Vec but still slower than TF-IDF
- Dense vectors (inefficient)
- Doesn't offer advantage over TF-IDF for this use case

#### Why Not Custom n-gram?

- Reinventing the wheel
- Bug-prone
- Harder to maintain
- scikit-learn battle-tested (millions of users)

### Hyperparameter Choices

```python
TfidfVectorizer(
    max_features=10_000,      # Why 10K?
                              # - Covers 95% of vocabulary
                              # - Keeps matrix manageable (9.8 MB)
                              # - Reduces overfitting vs 50K

    ngram_range=(1, 2),       # Why unigrams + bigrams?
                              # - Unigrams: single words (Python, engineer)
                              # - Bigrams: two-word phrases (machine learning)
                              # - Trigrams overkill for job descriptions

    min_df=2,                 # Why 2?
                              # - Skip ultra-rare words (typos, URLs)
                              # - Helps generalization

    max_df=0.8,               # Why 80%?
                              # - Skip extremely common words (the, a, is)
                              # - But keep job-common words (company, role)

    sublinear_tf=True,        # Why?
                              # - Reduces impact of extremely frequent words
                              # - Prevents long documents from dominating
)
```

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| TF-IDF performs poorly | A/B test vs Word2Vec; data-driven comparison |
| New job types require different model | Retrain monthly; version management |
| Inference speed too slow | Cache results; TF-IDF still sub-1ms |

### Upgrade Path

```
Phase 1 (now): TF-IDF (baseline)
Phase 2 (6 mo): Word2Vec ensemble (TF-IDF + Word2Vec)
Phase 3 (1 year): Fine-tuned BERT (if budget allows)
Phase 4 (2 years): LLM-based embeddings (if needed)
```

### Related Documentation

- See `docs/batch_pipeline.md` for Stage 4 (vectorize)
- See `docs/architecture.md` for NLP layer

---

## Decision Summary

| Decision | Choice | Status | Phase 1 | Phase 2+ |
|----------|--------|--------|---------|----------|
| Database | PostgreSQL 15 | Approved | ✓ | Replication |
| Cache | Redis 7 | Approved | ✓ | Cluster |
| Batch Schedule | Daily | Approved | ✓ | Hourly |
| Vector Storage | Joblib files | Approved | ✓ | S3 archive |
| Model Versioning | Semantic | Approved | ✓ | git-lfs |
| Orchestration | Airflow 2.10.4 | Approved | ✓ | CeleryExecutor |
| ETL Language | Python 3.11 | Approved | ✓ | Optional Spark |
| NLP Model | TF-IDF | Approved | ✓ | Ensemble |

---

## Approval & Sign-off

**Decision Type:** Architecture Design
**Status:** Ready for Phase 3 Implementation
**Review Date:** 2026-01-08
**Next Review:** 2026-06-08 (mid-year assessment)

### Implementation Checklist

- [x] All decisions documented with trade-off analysis
- [x] Risk mitigation strategies identified
- [x] Upgrade paths planned for future phases
- [x] Related documentation cross-linked
- [ ] Team feedback collected (pending)
- [ ] Infrastructure deployed (in progress)
- [ ] Monitoring and alerting configured (pending Phase 3)

### Related Documents

- `docs/architecture.md` - System architecture and data flow
- `docs/database_schema.md` - PostgreSQL schema details
- `docs/batch_pipeline.md` - Orchestration and workflow
- `PROGRESS.md` - Phase tracking and next steps

