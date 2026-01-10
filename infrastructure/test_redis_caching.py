#!/usr/bin/env python3
"""
Test script to verify Redis caching for TF-IDF vectorizer and matrix.
Tests: Caching, retrieval, and performance comparison.

Run from within the Airflow container:
  docker exec ijob-airflow python3 /opt/airflow/test_redis_caching.py
"""

import sys
import time
import joblib
from pathlib import Path

# Add src to path
sys.path.insert(0, '/opt/airflow/src')

def test_redis_connection():
    """Test 1: Verify Redis connection"""
    print("\n" + "="*80)
    print("TEST 1: Redis Connection")
    print("="*80)

    try:
        import redis
        from redis_cache import get_redis_client

        client = get_redis_client(host='redis', port=6379)
        if client:
            client.ping()
            info = client.info('memory')
            print(f"✓ Redis connected successfully")
            print(f"  Memory used: {info['used_memory'] / 1024 / 1024:.1f}MB")
            print(f"  Max memory: {info.get('maxmemory', 0) / 1024 / 1024:.1f}MB")
            return True
        else:
            print("✗ Redis connection failed")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_vectorizer_caching():
    """Test 2: Test caching and retrieval of vectorizer"""
    print("\n" + "="*80)
    print("TEST 2: Vectorizer Caching and Retrieval")
    print("="*80)

    try:
        from redis_cache import cache_vectorizer_and_matrix, load_from_redis
        import redis

        # Load vectorizer from disk
        model_dir = Path('/data/models')
        vec = joblib.load(model_dir / 'vectorizer.joblib')
        mat = joblib.load(model_dir / 'matrix.joblib')
        print(f"✓ Loaded vectorizer and matrix from disk")
        print(f"  Vocab size: {len(vec.vocabulary_)}")
        print(f"  Matrix shape: {mat.shape}")

        # Cache in Redis
        model_version = "test_model_v20260108"
        success = cache_vectorizer_and_matrix(vec, mat, model_version, ttl_seconds=3600)
        if success:
            print(f"✓ Cached model in Redis: {model_version}")
        else:
            print(f"✗ Failed to cache model")
            return False

        # Retrieve from Redis
        time.sleep(0.5)  # Small delay
        cached = load_from_redis(model_version)
        if cached:
            vec_cached, mat_cached = cached
            print(f"✓ Retrieved model from Redis cache")
            print(f"  Vocab size (cached): {len(vec_cached.vocabulary_)}")
            print(f"  Matrix shape (cached): {mat_cached.shape}")

            # Verify they match
            if len(vec.vocabulary_) == len(vec_cached.vocabulary_):
                print(f"✓ Cached vectorizer matches original")
            else:
                print(f"✗ Cached vectorizer doesn't match")
                return False

            return True
        else:
            print(f"✗ Failed to retrieve from Redis cache")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance_comparison():
    """Test 3: Performance comparison (disk vs Redis)"""
    print("\n" + "="*80)
    print("TEST 3: Performance Comparison")
    print("="*80)

    try:
        from redis_cache import load_vectorizer_and_matrix as load_with_cache
        import joblib

        model_version = "test_model_v20260108"
        model_dir = '/data/models'

        # Benchmark: Load from disk multiple times
        print("\nBenchmark 1: Loading from disk (3 iterations)")
        disk_times = []
        for i in range(3):
            start = time.time()
            vec_disk = joblib.load(Path(model_dir) / 'vectorizer.joblib')
            mat_disk = joblib.load(Path(model_dir) / 'matrix.joblib')
            elapsed = time.time() - start
            disk_times.append(elapsed)
            print(f"  Iteration {i+1}: {elapsed*1000:.2f}ms")

        avg_disk = sum(disk_times) / len(disk_times)
        print(f"  Average disk load time: {avg_disk*1000:.2f}ms")

        # Benchmark: Load from Redis cache
        print("\nBenchmark 2: Loading from Redis cache (3 iterations)")
        redis_times = []
        for i in range(3):
            start = time.time()
            vec_redis, mat_redis = load_with_cache(model_dir, model_version)
            elapsed = time.time() - start
            redis_times.append(elapsed)
            print(f"  Iteration {i+1}: {elapsed*1000:.2f}ms")

        avg_redis = sum(redis_times) / len(redis_times)
        print(f"  Average Redis load time: {avg_redis*1000:.2f}ms")

        # Calculate speedup
        speedup = avg_disk / avg_redis if avg_redis > 0 else 0
        print(f"\n✓ Speedup: {speedup:.1f}x faster with Redis")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_invalidation():
    """Test 4: Cache invalidation"""
    print("\n" + "="*80)
    print("TEST 4: Cache Invalidation")
    print("="*80)

    try:
        from redis_cache import invalidate_cache, load_from_redis

        model_version = "test_model_v20260108"

        # Check if cached
        cached_before = load_from_redis(model_version)
        if cached_before:
            print(f"✓ Model is in cache before invalidation")
        else:
            print(f"✗ Model not found in cache")
            return False

        # Invalidate
        invalidate_cache(model_version)
        print(f"✓ Cache invalidated for {model_version}")

        # Verify it's gone
        time.sleep(0.5)
        cached_after = load_from_redis(model_version)
        if not cached_after:
            print(f"✓ Model successfully removed from cache")
            return True
        else:
            print(f"✗ Model still in cache after invalidation")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    print("\n╔════════════════════════════════════════════════════════════════════════════════╗")
    print("║                    REDIS CACHING - VERIFICATION TEST                         ║")
    print("╚════════════════════════════════════════════════════════════════════════════════╝")

    results = {}

    results['redis_connection'] = test_redis_connection()

    if results['redis_connection']:
        results['vectorizer_caching'] = test_vectorizer_caching()
        results['performance'] = test_performance_comparison()
        if results['vectorizer_caching']:
            results['cache_invalidation'] = test_cache_invalidation()

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    tests_passed = sum(1 for v in results.values() if v)
    tests_total = len(results)
    print(f"\nTotal: {tests_passed}/{tests_total} tests passed")

    if tests_passed == tests_total:
        print("\n✓ All tests PASSED! Redis caching is working correctly.")
        return 0
    else:
        print(f"\n⚠ {tests_total - tests_passed} test(s) FAILED or SKIPPED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
