"""
Centralized path configuration for the Intelligent Job Dashboard.

This module provides a single source of truth for all file paths used
throughout the project. It auto-detects the environment (Docker vs local)
and can be overridden via environment variables.

Usage:
    from config.paths import DATA_DIR, RAW_DIR, PROCESSED_DIR, MODELS_DIR
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """
    Get the project root directory.

    Detection order:
    1. PROJECT_ROOT environment variable (if set)
    2. Auto-detect based on this file's location
    """
    if env_path := os.getenv("PROJECT_ROOT"):
        return Path(env_path)

    # This file is at: src/config/paths.py
    # Project root is 2 levels up
    return Path(__file__).parent.parent.parent


def get_data_root() -> Path:
    """
    Get the data directory root.

    Detection order:
    1. DATA_DIR environment variable (if set)
    2. /data (if exists - running in Docker)
    3. {project_root}/data (local development)
    """
    if env_path := os.getenv("DATA_DIR"):
        return Path(env_path)

    # Check if running in Docker (data mounted at /data)
    if os.path.exists("/data") and os.path.isdir("/data"):
        return Path("/data")

    # Local development fallback
    return get_project_root() / "data"


# =============================================================================
# Core Path Constants
# =============================================================================

PROJECT_ROOT = get_project_root()
DATA_DIR = get_data_root()

# Data subdirectories
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"

# Specific file paths
RAW_CSV_PATH = RAW_DIR / "job_listings_raw.csv"
VALIDATED_CSV_PATH = PROCESSED_DIR / "job_listings_validated.csv"
CLEAN_CSV_PATH = PROCESSED_DIR / "job_listings_clean.csv"
ENRICHED_CSV_PATH = PROCESSED_DIR / "job_listings_enriched.csv"

# Model paths
TFIDF_DIR = MODELS_DIR / "tfidf" if not os.path.exists(MODELS_DIR) else MODELS_DIR
VECTORIZER_PATH = MODELS_DIR / "vectorizer.joblib"
MATRIX_PATH = MODELS_DIR / "matrix.joblib"

# Config paths
CONFIG_DIR = PROJECT_ROOT / "src" / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.yaml"
SETTINGS_EXAMPLE_PATH = CONFIG_DIR / "settings.example.yaml"


def ensure_directories() -> None:
    """Create all required directories if they don't exist."""
    for directory in [RAW_DIR, PROCESSED_DIR, MODELS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    # Debug: print all paths
    print(f"PROJECT_ROOT:       {PROJECT_ROOT}")
    print(f"DATA_DIR:           {DATA_DIR}")
    print(f"RAW_DIR:            {RAW_DIR}")
    print(f"PROCESSED_DIR:      {PROCESSED_DIR}")
    print(f"MODELS_DIR:         {MODELS_DIR}")
    print(f"RAW_CSV_PATH:       {RAW_CSV_PATH}")
    print(f"VALIDATED_CSV_PATH: {VALIDATED_CSV_PATH}")
    print(f"CLEAN_CSV_PATH:     {CLEAN_CSV_PATH}")
    print(f"VECTORIZER_PATH:    {VECTORIZER_PATH}")
    print(f"MATRIX_PATH:        {MATRIX_PATH}")
    print(f"SETTINGS_PATH:      {SETTINGS_PATH}")
