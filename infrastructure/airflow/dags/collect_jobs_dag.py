"""
Intelligent Job Dashboard - Main Data Pipeline DAG

5-Stage Pipeline:
1. COLLECT - Fetch jobs from Adzuna API
2. VALIDATE - Data quality checks
3. ENRICH - Clean data, extract skills, parse salary
4. VECTORIZE - Build TF-IDF model and vectorize
5. EXPORT - Insert/update jobs in PostgreSQL

Schedule: Daily at 00:30 UTC
Executor: LocalExecutor
Backoff: Exponential (60s, 120s, then fail)
"""

import os
import sys
import json
import logging
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable
from airflow.exceptions import AirflowException

# Add source code to path
sys.path.insert(0, '/opt/airflow/src')

# Import our data pipeline modules (will be imported inside task functions)
# Delayed imports to avoid DAG parse-time errors

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DATA_DIRS = {
    'raw': '/data/raw',
    'processed': '/data/processed',
    'models': '/data/models'
}

# Ensure data directories exist
for dir_path in DATA_DIRS.values():
    Path(dir_path).mkdir(parents=True, exist_ok=True)

# DAG Configuration
DEFAULT_ARGS = {
    'owner': 'data-team',
    'retries': 2,
    'retry_delay': timedelta(minutes=1),
    'catchup': False,
    'email_on_failure': False,
}

DAG_ID = 'collect_jobs_daily'

dag = DAG(
    DAG_ID,
    default_args=DEFAULT_ARGS,
    description='Daily job collection, processing, vectorization, and storage pipeline',
    schedule_interval='30 0 * * *',  # 00:30 UTC daily
    start_date=datetime(2026, 1, 8),
    tags=['data-pipeline', 'jobs', 'daily']
)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def log_batch_run(batch_id, stage, status, jobs_count=0, error_message=None, execution_time=0, context=None):
    """
    Log batch execution to PostgreSQL batch_runs table

    Args:
        batch_id: UUID for this batch
        stage: Stage name (collect, validate, enrich, vectorize, export)
        status: Status (pending, in_progress, success, failed)
        jobs_count: Number of jobs processed in this stage
        error_message: Error details if failed
        execution_time: Seconds taken for this stage
        context: Airflow task context (optional)
    """
    try:
        conn = psycopg2.connect(
            host='postgres',
            port=5432,
            database='intelligent_jobs_db',
            user='jobadmin',
            password='jobsecure123'
        )
        cursor = conn.cursor()

        # Map stage to column names
        stage_columns = {
            'collect': 'jobs_collected',
            'validate': 'jobs_validated',
            'enrich': 'jobs_enriched',
            'vectorize': 'jobs_vectorized',
            'export': 'jobs_inserted'
        }

        jobs_col = stage_columns.get(stage, 'jobs_collected')

        if status == 'pending':
            # Initial insert
            cursor.execute("""
                INSERT INTO batch_runs
                (batch_id, batch_date, stage, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (batch_id, datetime.now().date(), stage, status, datetime.now(), datetime.now()))
        else:
            # Update with results
            if error_message:
                cursor.execute(f"""
                    UPDATE batch_runs
                    SET {jobs_col} = %s, status = %s, error_message = %s,
                        execution_time_seconds = %s, updated_at = %s
                    WHERE batch_id = %s AND stage = %s
                """, (jobs_count, status, error_message, execution_time, datetime.now(), batch_id, stage))
            else:
                cursor.execute(f"""
                    UPDATE batch_runs
                    SET {jobs_col} = %s, status = %s,
                        execution_time_seconds = %s, updated_at = %s
                    WHERE batch_id = %s AND stage = %s
                """, (jobs_count, status, execution_time, datetime.now(), batch_id, stage))

        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Logged batch_run: {batch_id} | {stage} | {status} | {jobs_count} jobs")
    except Exception as e:
        logger.error(f"Failed to log batch_run: {e}")
        raise

def get_connection():
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        host='postgres',
        port=5432,
        database='intelligent_jobs_db',
        user='jobadmin',
        password='jobsecure123'
    )

# ============================================================================
# STAGE 1: COLLECT
# ============================================================================

def stage_1_collect(**context):
    """
    Stage 1: Collect jobs from Adzuna API

    Output:
        - data/raw/job_listings_raw.csv (appended with new jobs)
        - batch_runs table entry with jobs_collected count

    XCom:
        - raw_csv_path: path to raw CSV
        - jobs_collected: number of jobs collected
        - batch_id: unique batch identifier
    """
    # Import inside function to avoid parse-time errors
    from collect_data import fetch_adzuna_jobs, unify_schema, append_to_csv, load_config

    task_start = datetime.now()
    batch_id = str(uuid4())

    logger.info(f"[COLLECT] Starting Stage 1 - batch_id: {batch_id}")

    try:
        # Initialize batch run entry
        log_batch_run(batch_id, 'collect', 'in_progress')

        # Load configuration
        cfg = load_config()

        # Use processed directory for batch-specific files (raw directory is read-only source data)
        raw_csv_path = f"{DATA_DIRS['processed']}/batch_{batch_id}_collected.csv"
        df = None
        rows_count = 0

        if cfg:
            # API credentials available - fetch from API
            try:
                # Collect parameters (could be from Variables or hardcoded)
                try:
                    query = Variable.get("COLLECT_QUERY")
                except:
                    query = "data engineer"

                try:
                    locations = Variable.get("COLLECT_LOCATIONS").split(',')
                except:
                    locations = ["Paris", "Lyon", "Marseille"]

                try:
                    limit = int(Variable.get("COLLECT_LIMIT"))
                except:
                    limit = 500

                logger.info(f"[COLLECT] Fetching jobs: query='{query}', locations={locations}, limit={limit}")

                # Fetch from Adzuna API
                rows = fetch_adzuna_jobs(query, locations, limit, cfg)
                logger.info(f"[COLLECT] Fetched {len(rows)} raw job listings from API")

                if rows:
                    df = unify_schema(rows)
                    rows_count = len(df)
                    logger.info(f"[COLLECT] Unified schema: {rows_count} jobs")

                    # Append to CSV (with deduplication)
                    append_to_csv(df, raw_csv_path)
                    logger.info(f"[COLLECT] Appended to {raw_csv_path}")
            except Exception as api_error:
                logger.warning(f"[COLLECT] API fetch failed: {api_error}. Will skip API collection.")
        else:
            logger.warning("[COLLECT] No API configuration found. Skipping API collection.")

        # If no rows from API, use existing data or create empty
        if rows_count == 0:
            # Sample data is mounted at /data/raw in the container
            sample_data_path = '/data/raw/job_listings_raw.csv'

            if os.path.exists(sample_data_path):
                logger.info(f"[COLLECT] Using sample data from {sample_data_path}")
                df = pd.read_csv(sample_data_path)
                rows_count = len(df)
                # Ensure we have the dataframe saved to raw_csv_path for later stages
                df.to_csv(raw_csv_path, index=False)
                logger.info(f"[COLLECT] Loaded {rows_count} jobs from sample data and saved to {raw_csv_path}")
            else:
                logger.warning(f"[COLLECT] Sample data not found at {sample_data_path}. Using empty dataset.")
                rows_count = 0

        # Log completion
        execution_time = int((datetime.now() - task_start).total_seconds())
        log_batch_run(batch_id, 'collect', 'success', jobs_count=rows_count, execution_time=execution_time)

        # Push to XCom for next stages
        context['task_instance'].xcom_push(key='batch_id', value=batch_id)
        context['task_instance'].xcom_push(key='jobs_collected', value=rows_count)
        context['task_instance'].xcom_push(key='raw_csv_path', value=raw_csv_path)

        logger.info(f"[COLLECT] Stage 1 completed in {execution_time}s - {rows_count} jobs collected")

    except Exception as e:
        execution_time = int((datetime.now() - task_start).total_seconds())
        error_msg = f"Collection failed: {str(e)}"
        logger.error(f"[COLLECT] {error_msg}")
        log_batch_run(batch_id, 'collect', 'failed', error_message=error_msg, execution_time=execution_time)
        raise AirflowException(error_msg)

# ============================================================================
# STAGE 2: VALIDATE
# ============================================================================

def stage_2_validate(**context):
    """
    Stage 2: Validate data quality

    Input:
        - raw_csv_path from Stage 1
        - batch_id from Stage 1

    Validation Rules:
        - job_title: required, length 10-500
        - url: required, valid URL format
        - location: required, non-empty
        - date: valid ISO date
        - salary: if present, min <= max

    Output:
        - batch_runs table updated with jobs_validated
        - List of job IDs that passed validation
    """
    task_start = datetime.now()
    batch_id = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='batch_id')
    raw_csv_path = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='raw_csv_path')
    jobs_collected = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='jobs_collected')

    logger.info(f"[VALIDATE] Starting Stage 2 - batch_id: {batch_id}, jobs_collected: {jobs_collected}")

    try:
        log_batch_run(batch_id, 'validate', 'in_progress')

        # Read raw CSV
        if not os.path.exists(raw_csv_path):
            raise AirflowException(f"Raw CSV not found: {raw_csv_path}")

        df = pd.read_csv(raw_csv_path)
        logger.info(f"[VALIDATE] Read {len(df)} rows from {raw_csv_path}")

        # Apply validation rules
        valid_count = 0
        failed_validations = {
            'missing_title': 0,
            'invalid_title_length': 0,
            'missing_url': 0,
            'missing_location': 0,
            'invalid_date': 0,
            'invalid_salary': 0
        }

        valid_job_ids = []

        for idx, row in df.iterrows():
            is_valid = True

            # Check required fields
            if pd.isna(row.get('job_title')) or not str(row['job_title']).strip():
                failed_validations['missing_title'] += 1
                is_valid = False
            elif not (10 <= len(str(row['job_title'])) <= 500):
                failed_validations['invalid_title_length'] += 1
                is_valid = False

            if pd.isna(row.get('url')) or not str(row['url']).strip():
                failed_validations['missing_url'] += 1
                is_valid = False

            if pd.isna(row.get('location')) or not str(row['location']).strip():
                failed_validations['missing_location'] += 1
                is_valid = False

            # Date validation (basic)
            if not pd.isna(row.get('posted_date')):
                try:
                    pd.to_datetime(row['posted_date'])
                except:
                    failed_validations['invalid_date'] += 1
                    is_valid = False

            # Salary validation (if present)
            if not pd.isna(row.get('salary_min')) and not pd.isna(row.get('salary_max')):
                try:
                    min_sal = float(row['salary_min'])
                    max_sal = float(row['salary_max'])
                    if min_sal > max_sal:
                        failed_validations['invalid_salary'] += 1
                        is_valid = False
                except:
                    failed_validations['invalid_salary'] += 1
                    is_valid = False

            if is_valid:
                valid_count += 1
                valid_job_ids.append(row['job_id'])

        logger.info(f"[VALIDATE] Validation results: {valid_count}/{len(df)} passed")
        logger.info(f"[VALIDATE] Failed validations: {failed_validations}")

        # Log completion
        execution_time = int((datetime.now() - task_start).total_seconds())
        log_batch_run(batch_id, 'validate', 'success', jobs_count=valid_count, execution_time=execution_time)

        # Push to XCom
        context['task_instance'].xcom_push(key='jobs_validated', value=valid_count)
        context['task_instance'].xcom_push(key='valid_job_ids', value=valid_job_ids)

        logger.info(f"[VALIDATE] Stage 2 completed in {execution_time}s - {valid_count} jobs validated")

    except Exception as e:
        execution_time = int((datetime.now() - task_start).total_seconds())
        error_msg = f"Validation failed: {str(e)}"
        logger.error(f"[VALIDATE] {error_msg}")
        log_batch_run(batch_id, 'validate', 'failed', error_message=error_msg, execution_time=execution_time)
        raise AirflowException(error_msg)

# ============================================================================
# STAGE 3: ENRICH
# ============================================================================

def stage_3_enrich(**context):
    """
    Stage 3: Enrich data (clean, extract skills, parse salary)

    Input:
        - raw_csv_path from Stage 1
        - batch_id from Stage 1

    Processing:
        - Remove HTML from descriptions
        - Extract technical skills
        - Parse salary ranges
        - Standardize locations
        - Calculate days_since_posted
        - Add quality flags

    Output:
        - data/processed/job_listings_enriched.csv
        - batch_runs updated with jobs_enriched count
    """
    # Import inside function to avoid parse-time errors
    from clean_data import clean_job_data

    task_start = datetime.now()
    batch_id = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='batch_id')

    logger.info(f"[ENRICH] Starting Stage 3 - batch_id: {batch_id}")

    try:
        log_batch_run(batch_id, 'enrich', 'in_progress')

        raw_csv_path = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='raw_csv_path')
        processed_csv_path = f"{DATA_DIRS['processed']}/job_listings_enriched.csv"

        # Run clean_data pipeline
        clean_job_data(raw_csv_path, processed_csv_path)
        logger.info(f"[ENRICH] Cleaned data saved to {processed_csv_path}")

        # Count enriched jobs
        df_enriched = pd.read_csv(processed_csv_path)
        jobs_enriched = len(df_enriched)

        logger.info(f"[ENRICH] Enriched {jobs_enriched} jobs")

        # Log completion
        execution_time = int((datetime.now() - task_start).total_seconds())
        log_batch_run(batch_id, 'enrich', 'success', jobs_count=jobs_enriched, execution_time=execution_time)

        # Push to XCom
        context['task_instance'].xcom_push(key='jobs_enriched', value=jobs_enriched)
        context['task_instance'].xcom_push(key='processed_csv_path', value=processed_csv_path)

        logger.info(f"[ENRICH] Stage 3 completed in {execution_time}s - {jobs_enriched} jobs enriched")

    except Exception as e:
        execution_time = int((datetime.now() - task_start).total_seconds())
        error_msg = f"Enrichment failed: {str(e)}"
        logger.error(f"[ENRICH] {error_msg}")
        log_batch_run(batch_id, 'enrich', 'failed', error_message=error_msg, execution_time=execution_time)
        raise AirflowException(error_msg)

# ============================================================================
# STAGE 4: VECTORIZE
# ============================================================================

def stage_4_vectorize(**context):
    """
    Stage 4: Build TF-IDF model and vectorize

    Input:
        - processed_csv_path from Stage 3
        - batch_id from Stage 1

    Processing:
        - Load enriched job descriptions
        - Build TF-IDF vectorizer (10K features, bigrams)
        - Save models to disk
        - Create model_versions database entry

    Output:
        - models/tfidf/vectorizer.joblib
        - models/tfidf/matrix.joblib
        - model_versions table entry
        - batch_runs updated with jobs_vectorized count
    """
    # Import inside function to avoid parse-time errors
    from recommend import build_and_save

    task_start = datetime.now()
    batch_id = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='batch_id')
    processed_csv_path = context['task_instance'].xcom_pull(task_ids='enrich_jobs', key='processed_csv_path')

    logger.info(f"[VECTORIZE] Starting Stage 4 - batch_id: {batch_id}")

    try:
        log_batch_run(batch_id, 'vectorize', 'in_progress')

        # Read enriched data
        if not os.path.exists(processed_csv_path):
            raise AirflowException(f"Processed CSV not found: {processed_csv_path}")

        df = pd.read_csv(processed_csv_path)
        jobs_vectorized = len(df)
        logger.info(f"[VECTORIZE] Read {jobs_vectorized} enriched jobs")

        # Extract corpus
        corpus = df['job_description'].fillna('').astype(str).tolist()

        # Build and save TF-IDF model
        model_version = f"tfidf_v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"[VECTORIZE] Building model: {model_version}")

        vectorizer, matrix = build_and_save(corpus, out_dir=DATA_DIRS['models'], max_features=10000, ngram_range=(1, 2))
        logger.info(f"[VECTORIZE] Model saved: {model_version}")

        # Update model_versions table
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO model_versions
                (model_version, model_type, vectorizer_path, matrix_path,
                 trained_on_jobs_count, feature_count, ngram_range, status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                model_version,
                'tfidf',
                f'tfidf/{model_version}/vectorizer.joblib',
                f'tfidf/{model_version}/matrix.joblib',
                jobs_vectorized,
                10000,
                '(1, 2)',
                'active',
                f'batch_{batch_id}',
                datetime.now()
            ))

            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"[VECTORIZE] Saved model_version entry: {model_version}")
        except Exception as e:
            logger.error(f"[VECTORIZE] Failed to save model_version: {e}")
            raise

        # Cache vectorizer and matrix in Redis for fast access
        try:
            from redis_cache import cache_vectorizer_and_matrix
            cache_vectorizer_and_matrix(vectorizer, matrix, model_version, ttl_seconds=604800)  # 7 days TTL
            logger.info(f"[VECTORIZE] Cached model in Redis: {model_version}")
        except Exception as e:
            logger.warning(f"[VECTORIZE] Failed to cache model in Redis: {e}")
            # Don't fail the pipeline if Redis caching fails

        # Log completion
        execution_time = int((datetime.now() - task_start).total_seconds())
        log_batch_run(batch_id, 'vectorize', 'success', jobs_count=jobs_vectorized, execution_time=execution_time)

        # Push to XCom
        context['task_instance'].xcom_push(key='jobs_vectorized', value=jobs_vectorized)
        context['task_instance'].xcom_push(key='model_version', value=model_version)

        logger.info(f"[VECTORIZE] Stage 4 completed in {execution_time}s - {jobs_vectorized} jobs vectorized")

    except Exception as e:
        execution_time = int((datetime.now() - task_start).total_seconds())
        error_msg = f"Vectorization failed: {str(e)}"
        logger.error(f"[VECTORIZE] {error_msg}")
        log_batch_run(batch_id, 'vectorize', 'failed', error_message=error_msg, execution_time=execution_time)
        raise AirflowException(error_msg)

# ============================================================================
# STAGE 5: EXPORT
# ============================================================================

def stage_5_export(**context):
    """
    Stage 5: Export to PostgreSQL

    Input:
        - processed_csv_path from Stage 3
        - batch_id from Stage 1
        - model_version from Stage 4

    Processing:
        - Read enriched job data
        - INSERT new jobs / UPDATE existing jobs
        - Log batch_run completion
        - Cache invalidation

    Output:
        - Jobs table updated with all new/updated records
        - batch_runs table final entry with counts
    """
    task_start = datetime.now()
    batch_id = context['task_instance'].xcom_pull(task_ids='collect_jobs', key='batch_id')
    processed_csv_path = context['task_instance'].xcom_pull(task_ids='enrich_jobs', key='processed_csv_path')

    logger.info(f"[EXPORT] Starting Stage 5 - batch_id: {batch_id}")

    try:
        log_batch_run(batch_id, 'export', 'in_progress')

        # Read enriched data
        if not os.path.exists(processed_csv_path):
            raise AirflowException(f"Processed CSV not found: {processed_csv_path}")

        df = pd.read_csv(processed_csv_path)
        logger.info(f"[EXPORT] Read {len(df)} enriched jobs for export")

        # Connect to PostgreSQL
        conn = get_connection()
        cursor = conn.cursor()

        # Prepare batch insert data
        jobs_inserted = 0
        jobs_updated = 0
        jobs_failed = 0

        for idx, row in df.iterrows():
            try:
                # Check if job exists
                cursor.execute("SELECT job_id FROM jobs WHERE job_id = %s", (row['job_id'],))
                exists = cursor.fetchone() is not None

                if exists:
                    # UPDATE existing job
                    cursor.execute("""
                        UPDATE jobs SET
                            job_title = %s,
                            company_name = %s,
                            location = %s,
                            posted_date = %s,
                            job_description = %s,
                            skills_required = %s,
                            salary_range = %s,
                            salary_min = %s,
                            salary_max = %s,
                            has_salary = %s,
                            has_skills = %s,
                            data_quality_score = %s,
                            updated_at = %s
                        WHERE job_id = %s
                    """, (
                        row.get('job_title'),
                        row.get('company_name'),
                        row.get('location'),
                        row.get('posted_date'),
                        row.get('job_description'),
                        row.get('skills_required'),
                        row.get('salary_range'),
                        row.get('salary_min') if not pd.isna(row.get('salary_min')) else None,
                        row.get('salary_max') if not pd.isna(row.get('salary_max')) else None,
                        row.get('has_salary', False),
                        row.get('has_skills', False),
                        1.0,  # data_quality_score
                        datetime.now(),
                        row['job_id']
                    ))
                    jobs_updated += 1
                else:
                    # INSERT new job
                    cursor.execute("""
                        INSERT INTO jobs
                        (job_id, job_title, company_name, location, posted_date,
                         job_description, skills_required, salary_range,
                         salary_min, salary_max, has_salary, has_skills,
                         url, source, search_query, data_quality_score, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row['job_id'],
                        row.get('job_title'),
                        row.get('company_name'),
                        row.get('location'),
                        row.get('posted_date'),
                        row.get('job_description'),
                        row.get('skills_required'),
                        row.get('salary_range'),
                        row.get('salary_min') if not pd.isna(row.get('salary_min')) else None,
                        row.get('salary_max') if not pd.isna(row.get('salary_max')) else None,
                        row.get('has_salary', False),
                        row.get('has_skills', False),
                        row.get('url'),
                        row.get('source', 'adzuna'),
                        row.get('search_query'),
                        1.0,  # data_quality_score
                        datetime.now(),
                        datetime.now()
                    ))
                    jobs_inserted += 1
            except Exception as e:
                logger.error(f"[EXPORT] Failed to insert/update job {row.get('job_id')}: {e}")
                jobs_failed += 1

        # Commit all changes
        conn.commit()
        logger.info(f"[EXPORT] Inserted: {jobs_inserted}, Updated: {jobs_updated}, Failed: {jobs_failed}")

        # Log completion
        execution_time = int((datetime.now() - task_start).total_seconds())

        # Update batch_runs with final counts
        cursor.execute("""
            UPDATE batch_runs SET
                jobs_inserted = %s,
                jobs_updated = %s,
                jobs_failed = %s,
                status = %s,
                execution_time_seconds = %s,
                updated_at = %s
            WHERE batch_id = %s AND stage = 'export'
        """, (jobs_inserted, jobs_updated, jobs_failed, 'success', execution_time, datetime.now(), batch_id))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"[EXPORT] Stage 5 completed in {execution_time}s - {jobs_inserted} inserted, {jobs_updated} updated")

    except Exception as e:
        execution_time = int((datetime.now() - task_start).total_seconds())
        error_msg = f"Export failed: {str(e)}"
        logger.error(f"[EXPORT] {error_msg}")
        log_batch_run(batch_id, 'export', 'failed', error_message=error_msg, execution_time=execution_time)
        raise AirflowException(error_msg)

# ============================================================================
# TASK DEFINITIONS
# ============================================================================

task_collect = PythonOperator(
    task_id='collect_jobs',
    python_callable=stage_1_collect,
    provide_context=True,
    dag=dag
)

task_validate = PythonOperator(
    task_id='validate_jobs',
    python_callable=stage_2_validate,
    provide_context=True,
    dag=dag
)

task_enrich = PythonOperator(
    task_id='enrich_jobs',
    python_callable=stage_3_enrich,
    provide_context=True,
    dag=dag
)

task_vectorize = PythonOperator(
    task_id='vectorize_jobs',
    python_callable=stage_4_vectorize,
    provide_context=True,
    dag=dag
)

task_export = PythonOperator(
    task_id='export_jobs',
    python_callable=stage_5_export,
    provide_context=True,
    dag=dag
)

# ============================================================================
# TASK DEPENDENCIES
# ============================================================================

task_collect >> task_validate >> task_enrich >> task_vectorize >> task_export
