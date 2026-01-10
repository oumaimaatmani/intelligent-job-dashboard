import logging
from pathlib import Path
from typing import Optional, Tuple

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from config.paths import CLEAN_CSV_PATH, MODELS_DIR

"""
Objectif de ce code :
 wrapper principal pour sérialiser/charger un modèle TF-IDF
 et servir des recommandations sans recalculer la matrice à chaque fois.
"""

try:
    # reuse preprocessing from `nlp.py` in the same folder
    from nlp import preprocess_text
except Exception:
    # fallback: minimal passthrough
    def preprocess_text(x):
        return x or ""


try:
    from skills import extract_skills_from_text
except Exception:

    def extract_skills_from_text(x, **kwargs):
        return []


logger = logging.getLogger(__name__)


def build_and_save(
    corpus,
    out_dir: str = None,
    max_features: int = 10000,
    ngram_range=(1, 2),
) -> Tuple[TfidfVectorizer, object]:
    if out_dir is None:
        out_dir = MODELS_DIR
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    cleaned = [preprocess_text(d or "") for d in corpus]
    vec = TfidfVectorizer(max_features=max_features, ngram_range=ngram_range)
    mat = vec.fit_transform(cleaned)

    joblib.dump(vec, out / "vectorizer.joblib")
    joblib.dump(mat, out / "matrix.joblib")
    logger.info("Saved vectorizer and matrix to %s", out)
    return vec, mat


def load_vectorizer_and_matrix(
    model_dir: str = None,
) -> Tuple[TfidfVectorizer, object]:
    if model_dir is None:
        model_dir = MODELS_DIR
    p = Path(model_dir)
    vec = joblib.load(p / "vectorizer.joblib")
    mat = joblib.load(p / "matrix.joblib")
    return vec, mat


def recommend(
    query: str,
    df: pd.DataFrame,
    vectorizer: Optional[TfidfVectorizer] = None,
    matrix=None,
    text_field: str = "job_description",
    top_n: int = 10,
    extract_skills: bool = True,
    skills_field: str = "job_description",
):
    """Recommend jobs similar to query with optional skills extraction.

    Args:
        query: search query
        df: DataFrame with job listings
        vectorizer: pre-built TfidfVectorizer (optional)
        matrix: pre-built TF-IDF matrix (optional)
        text_field: column to vectorize (default: job_description)
        top_n: number of results to return
        extract_skills: if True, extract skills from job descriptions
        skills_field: column to extract skills from (default: job_description)

    Returns:
        DataFrame with results sorted by _similarity_score, optionally enriched with _extracted_skills
    """
    if text_field not in df.columns:
        raise ValueError(f"Field '{text_field}' not found in dataframe")

    corpus = df[text_field].fillna("").astype(str).tolist()

    if vectorizer is None or matrix is None:
        vectorizer = TfidfVectorizer()
        cleaned = [preprocess_text(d or "") for d in corpus]
        matrix = vectorizer.fit_transform(cleaned)

    qv = vectorizer.transform([preprocess_text(query)])
    sims = cosine_similarity(qv, matrix).flatten()

    dfc = df.copy()
    dfc["_similarity_score"] = sims

    # Optional: extract and add skills
    if extract_skills and skills_field in dfc.columns:
        try:
            dfc["_extracted_skills"] = (
                dfc[skills_field]
                .fillna("")
                .astype(str)
                .apply(lambda t: extract_skills_from_text(t, use_spacy=False))
            )
        except Exception as e:
            logger.debug("Skills extraction failed: %s", e)

    return (
        dfc.sort_values("_similarity_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Build/load TF-IDF model and recommend jobs for a query"
    )
    parser.add_argument("--data", type=str, default=str(CLEAN_CSV_PATH))
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build and save vectorizer/matrix from data",
    )
    parser.add_argument("--model-dir", type=str, default=str(MODELS_DIR))
    parser.add_argument("--query", type=str, help="Query for recommendation")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    df = pd.read_csv(args.data)

    if args.build:
        logger.info("Building TF-IDF from %d documents", len(df))
        build_and_save(
            df.get("job_description", "").fillna("").astype(str).tolist(),
            out_dir=args.model_dir,
        )
        logger.info("Build complete")
        raise SystemExit(0)

    if not args.query:
        logger.error("Provide --query or run with --build first")
        raise SystemExit(1)

    vec, mat = load_vectorizer_and_matrix(args.model_dir)
    res = recommend(args.query, df, vectorizer=vec, matrix=mat, top_n=args.top)
    print(
        res[["job_title", "company_name", "location", "_similarity_score"]].to_string(
            index=False
        )
    )
