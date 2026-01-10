"""
Redis caching utilities for TF-IDF vectorizer and sparse matrix models.

This module provides functions to:
1. Cache trained vectorizer and matrix in Redis for fast access
2. Retrieve cached models with fallback to disk
3. Invalidate cache when new models are trained
"""

import logging
import pickle
from pathlib import Path
from typing import Optional, Tuple

import redis
from sklearn.feature_extraction.text import TfidfVectorizer

from config.paths import MODELS_DIR

logger = logging.getLogger(__name__)

# Redis connection parameters (from environment or defaults)
REDIS_HOST = "redis"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_TIMEOUT = 300  # 5 minutes

# Cache key prefixes
CACHE_VECTORIZER_KEY = "tfidf:vectorizer:{model_version}"
CACHE_MATRIX_KEY = "tfidf:matrix:{model_version}"
CACHE_METADATA_KEY = "tfidf:metadata:{model_version}"


def get_redis_client(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB) -> redis.Redis:
    """Get or create Redis connection."""
    try:
        client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=False,
            socket_connect_timeout=5,
        )
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
        return None


def cache_vectorizer_and_matrix(
    vectorizer: TfidfVectorizer, matrix, model_version: str, ttl_seconds: int = 86400
) -> bool:
    """
    Cache vectorizer and matrix in Redis for fast retrieval.

    Args:
        vectorizer: Trained TfidfVectorizer object
        matrix: Sparse TF-IDF matrix (scipy.sparse)
        model_version: Version string (e.g., 'tfidf_v20260108_210911')
        ttl_seconds: Time-to-live in Redis (default: 24 hours)

    Returns:
        bool: True if caching successful, False if skipped/failed
    """
    try:
        client = get_redis_client()
        if not client:
            logger.debug("Redis client not available, skipping vectorizer cache")
            return False

        # Serialize vectorizer and matrix using pickle
        vec_bytes = pickle.dumps(vectorizer, protocol=pickle.HIGHEST_PROTOCOL)
        mat_bytes = pickle.dumps(matrix, protocol=pickle.HIGHEST_PROTOCOL)

        # Store in Redis with TTL
        vec_key = CACHE_VECTORIZER_KEY.format(model_version=model_version)
        mat_key = CACHE_MATRIX_KEY.format(model_version=model_version)
        meta_key = CACHE_METADATA_KEY.format(model_version=model_version)

        pipe = client.pipeline()
        pipe.setex(vec_key, ttl_seconds, vec_bytes)
        pipe.setex(mat_key, ttl_seconds, mat_bytes)
        pipe.setex(
            meta_key,
            ttl_seconds,
            f"vocab_size:{len(vectorizer.vocabulary_)},ngram:{vectorizer.ngram_range}",
        )
        pipe.execute()

        size_mb = (len(vec_bytes) + len(mat_bytes)) / 1024 / 1024
        logger.info(
            f"Cached vectorizer and matrix for {model_version} in Redis ({size_mb:.1f}MB, TTL: {ttl_seconds}s)"
        )
        return True

    except Exception as e:
        logger.warning(f"Failed to cache models in Redis: {e}")
        return False


def load_from_redis(model_version: str) -> Optional[Tuple[TfidfVectorizer, object]]:
    """
    Load vectorizer and matrix from Redis cache.

    Args:
        model_version: Version string to retrieve

    Returns:
        Tuple of (vectorizer, matrix) or None if not found in cache
    """
    try:
        client = get_redis_client()
        if not client:
            return None

        vec_key = CACHE_VECTORIZER_KEY.format(model_version=model_version)
        mat_key = CACHE_MATRIX_KEY.format(model_version=model_version)

        vec_bytes = client.get(vec_key)
        mat_bytes = client.get(mat_key)

        if vec_bytes and mat_bytes:
            vectorizer = pickle.loads(vec_bytes)
            matrix = pickle.loads(mat_bytes)
            logger.debug(
                f"Loaded vectorizer and matrix for {model_version} from Redis cache"
            )
            return vectorizer, matrix

    except Exception as e:
        logger.warning(f"Failed to load models from Redis: {e}")

    return None


def load_vectorizer_and_matrix(
    model_version: str, model_dir: str = None
) -> Tuple[TfidfVectorizer, object]:
    """
    Load vectorizer and matrix with Redis cache fallback.

    Strategy:
    1. Try to load from Redis (fast)
    2. Fall back to disk (joblib) if not in cache
    3. Re-cache in Redis on fallback for next time

    Args:
        model_version: Version string
        model_dir: Directory containing joblib files (default: ../models/tfidf)

    Returns:
        Tuple of (vectorizer, matrix)
    """
    import joblib

    # Try Redis first
    cached = load_from_redis(model_version)
    if cached:
        return cached

    # Fall back to disk
    if model_dir is None:
        model_dir = str(MODELS_DIR)

    logger.debug(f"Loading {model_version} from disk (Redis miss)")
    p = Path(model_dir)
    vectorizer = joblib.load(p / "vectorizer.joblib")
    matrix = joblib.load(p / "matrix.joblib")

    # Re-cache in Redis for next time
    cache_vectorizer_and_matrix(vectorizer, matrix, model_version)

    return vectorizer, matrix


def invalidate_cache(model_version: str) -> bool:
    """Remove a model from Redis cache."""
    try:
        client = get_redis_client()
        if not client:
            return False

        vec_key = CACHE_VECTORIZER_KEY.format(model_version=model_version)
        mat_key = CACHE_MATRIX_KEY.format(model_version=model_version)
        meta_key = CACHE_METADATA_KEY.format(model_version=model_version)

        deleted = client.delete(vec_key, mat_key, meta_key)
        logger.info(f"Invalidated cache for {model_version} ({deleted} keys deleted)")
        return True

    except Exception as e:
        logger.warning(f"Failed to invalidate cache: {e}")
        return False


def get_cache_stats(model_version: str = None) -> dict:
    """Get caching statistics."""
    try:
        client = get_redis_client()
        if not client:
            return {}

        info = client.info("memory")
        return {
            "used_memory_mb": info.get("used_memory", 0) / 1024 / 1024,
            "max_memory_mb": info.get("maxmemory", 0) / 1024 / 1024,
            "evicted_keys": info.get("evicted_keys", 0),
        }
    except Exception as e:
        logger.warning(f"Failed to get cache stats: {e}")
        return {}


if __name__ == "__main__":
    # Test connection
    client = get_redis_client()
    if client:
        print("✓ Redis connection successful")
        info = client.info("memory")
        print(f"  Memory used: {info['used_memory'] / 1024 / 1024:.1f}MB")
        print(f"  Max memory: {info.get('maxmemory', 0) / 1024 / 1024:.1f}MB")
    else:
        print("✗ Redis connection failed")
