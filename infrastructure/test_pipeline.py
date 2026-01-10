#!/usr/bin/env python3
"""
Test script to verify the end-to-end pipeline is working correctly.
Tests: Data loading, TF-IDF vectorization, and recommendation generation.
"""

import sys
import joblib
import pandas as pd
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity

# Add src to path
sys.path.insert(0, '/home/sora/Git/intelligent-job-dashboard/src')

def test_data_loading():
    """Test 1: Verify processed data exists and is loaded correctly"""
    print("\n" + "="*80)
    print("TEST 1: Data Loading")
    print("="*80)

    data_path = Path('/home/sora/Git/intelligent-job-dashboard/data/processed/job_listings_enriched.csv')
    if not data_path.exists():
        print(f"✗ FAILED: Data file not found at {data_path}")
        return False

    df = pd.read_csv(data_path)
    print(f"✓ Loaded enriched data: {len(df)} jobs")
    print(f"  Columns: {', '.join(df.columns.tolist())}")
    print(f"  Sample job: {df.iloc[0]['job_title']} @ {df.iloc[0]['company_name']}")
    return True

def test_vectorization():
    """Test 2: Verify TF-IDF vectorizer and matrix are loaded correctly"""
    print("\n" + "="*80)
    print("TEST 2: TF-IDF Vectorization")
    print("="*80)

    model_dir = Path('/home/sora/Git/intelligent-job-dashboard/data/models')

    # Check files exist
    vec_path = model_dir / 'vectorizer.joblib'
    mat_path = model_dir / 'matrix.joblib'

    if not vec_path.exists():
        print(f"✗ FAILED: Vectorizer not found at {vec_path}")
        return False

    if not mat_path.exists():
        print(f"✗ FAILED: Matrix not found at {mat_path}")
        return False

    print(f"✓ Found vectorizer at {vec_path}")
    print(f"✓ Found matrix at {mat_path}")

    # Load vectorizer
    vectorizer = joblib.load(vec_path)
    print(f"✓ Loaded TF-IDF vectorizer")
    print(f"  Vocabulary size: {len(vectorizer.vocabulary_)}")
    print(f"  Max features: {vectorizer.max_features}")
    print(f"  N-gram range: {vectorizer.ngram_range}")

    # Load matrix
    matrix = joblib.load(mat_path)
    print(f"✓ Loaded TF-IDF matrix")
    print(f"  Shape: {matrix.shape} (jobs x features)")
    print(f"  Sparsity: {(1 - matrix.nnz / (matrix.shape[0] * matrix.shape[1])) * 100:.2f}%")

    return True, vectorizer, matrix

def test_recommendations(vectorizer, matrix):
    """Test 3: Verify recommendations are generated correctly"""
    print("\n" + "="*80)
    print("TEST 3: Recommendation Generation")
    print("="*80)

    data_path = '/home/sora/Git/intelligent-job-dashboard/data/processed/job_listings_enriched.csv'
    df = pd.read_csv(data_path)

    # Test queries
    test_queries = [
        "Python developer machine learning",
        "Data scientist AWS cloud",
        "DevOps engineer Kubernetes Docker"
    ]

    for query in test_queries:
        print(f"\nQuery: '{query}'")

        # Preprocess query (simple lowercase for testing)
        query_lower = query.lower()

        # Transform query
        qv = vectorizer.transform([query_lower])

        # Calculate similarity
        similarities = cosine_similarity(qv, matrix).flatten()

        # Get top 3
        top_indices = similarities.argsort()[-3:][::-1]

        print(f"  Top 3 matches:")
        for i, idx in enumerate(top_indices, 1):
            score = similarities[idx]
            job = df.iloc[idx]
            print(f"    {i}. {job['job_title'][:50]:50} @ {job['company_name'][:30]:30} (score: {score:.4f})")

    return True

def test_database():
    """Test 4: Verify data is stored in PostgreSQL"""
    print("\n" + "="*80)
    print("TEST 4: Database Storage")
    print("="*80)

    try:
        import psycopg2

        conn = psycopg2.connect(
            host='localhost',
            port=5432,
            database='intelligent_jobs_db',
            user='jobadmin',
            password='jobsecure123'
        )
        cursor = conn.cursor()

        # Check jobs table
        cursor.execute("SELECT COUNT(*) FROM jobs")
        job_count = cursor.fetchone()[0]
        print(f"✓ Jobs in database: {job_count}")

        # Check skills extraction stats
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_skills = true")
        skills_count = cursor.fetchone()[0]
        print(f"✓ Jobs with extracted skills: {skills_count} ({skills_count/job_count*100:.1f}%)")

        # Check salary extraction stats
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE has_salary = true")
        salary_count = cursor.fetchone()[0]
        print(f"✓ Jobs with salary info: {salary_count} ({salary_count/job_count*100:.1f}%)")

        # Check model versions
        cursor.execute("SELECT COUNT(*) FROM model_versions WHERE status = 'active'")
        model_count = cursor.fetchone()[0]
        print(f"✓ Active TF-IDF models: {model_count}")

        cursor.execute("SELECT model_version, trained_on_jobs_count FROM model_versions WHERE status = 'active' ORDER BY created_at DESC LIMIT 1")
        model_info = cursor.fetchone()
        if model_info:
            print(f"✓ Latest model: {model_info[0]} (trained on {model_info[1]} jobs)")

        conn.close()
        return True

    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def main():
    print("\n╔════════════════════════════════════════════════════════════════════════════════╗")
    print("║                  INTELLIGENT JOB DASHBOARD - PIPELINE TEST                    ║")
    print("╚════════════════════════════════════════════════════════════════════════════════╝")

    results = {}

    # Test 1: Data Loading
    results['data_loading'] = test_data_loading()

    # Test 2: Vectorization
    results['vectorization'] = test_vectorization()
    if isinstance(results['vectorization'], tuple):
        _, vectorizer, matrix = results['vectorization']
        results['vectorization'] = True

        # Test 3: Recommendations
        results['recommendations'] = test_recommendations(vectorizer, matrix)

    # Test 4: Database
    results['database'] = test_database()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    tests_passed = sum(1 for v in results.values() if v is True)
    tests_total = len(results)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {tests_passed}/{tests_total} tests passed")

    if tests_passed == tests_total:
        print("\n✓ All tests PASSED! Pipeline is working correctly.")
        return 0
    else:
        print(f"\n✗ {tests_total - tests_passed} test(s) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
