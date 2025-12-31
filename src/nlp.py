import re
import logging
from typing import List, Tuple, Optional

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import nltk
from nltk.stem import WordNetLemmatizer

logger = logging.getLogger(__name__)


def ensure_nltk_resources() -> None:
    try:
        nltk.data.find("corpora/wordnet")
    except Exception:
        nltk.download("wordnet")
    try:
        nltk.data.find("corpora/omw-1.4")
    except Exception:
        nltk.download("omw-1.4")


def preprocess_text(text: str, lemmatize: bool = True) -> str:
    """Basic text cleanup: lowercase, remove urls, punctuation, digits, and lemmatize.

    Returns a cleaned string suitable for vectorization.
    """
    if not text or not isinstance(text, str):
        return ""

    # Lowercase
    text = text.lower()

    # Remove URLs and emails
    text = re.sub(r"https?://\S+|www\.\S+|\S+@\S+", " ", text)

    # Keep letters and spaces
    text = re.sub(r"[^a-z\s]", " ", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if lemmatize:
        ensure_nltk_resources()
        lemmatizer = WordNetLemmatizer()
        # Use a simple regex tokenizer to avoid heavy NLTK punkt requirements
        tokens = re.findall(r"\b[a-z]{2,}\b", text)
        lemmas = [lemmatizer.lemmatize(t) for t in tokens]
        return " ".join(lemmas)

    return text


def build_tfidf_matrix(corpus: List[str], max_features: int = 10000, ngram_range: Tuple[int, int] = (1, 2)) -> Tuple[TfidfVectorizer, 'sparse_matrix']:
    """Build a TF-IDF vectorizer and transform corpus into matrix.

    Returns (vectorizer, matrix)
    """
    vectorizer = TfidfVectorizer(max_features=max_features, ngram_range=ngram_range)
    cleaned = [preprocess_text(doc or "") for doc in corpus]
    matrix = vectorizer.fit_transform(cleaned)
    return vectorizer, matrix



#transformer la query, calcule la similarité cosinus entre la query et toutes les descriptions, ajoute _similarity_score et renvoier les top N offres triées.
def recommend_by_tfidf(
    query: str,
    docs: pd.DataFrame,
    text_field: str = "job_description",
    top_n: int = 10,
    vectorizer: Optional[TfidfVectorizer] = None,
    matrix=None,
) -> pd.DataFrame:
    """Return top_n most similar documents to query using TF-IDF cosine similarity.

    If `vectorizer` and `matrix` are provided, they will be reused (faster for repeated queries).
    """
    if text_field not in docs.columns:
        raise ValueError(f"Field '{text_field}' not found in docs")

    corpus = docs[text_field].fillna("").astype(str).tolist()

    if vectorizer is None or matrix is None:
        vectorizer, matrix = build_tfidf_matrix(corpus)

    query_vec = vectorizer.transform([preprocess_text(query)])
    sims = cosine_similarity(query_vec, matrix).flatten()

    docs_copy = docs.copy()
    docs_copy["_similarity_score"] = sims
    top = docs_copy.sort_values("_similarity_score", ascending=False).head(top_n)
    return top.reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Simple TF-IDF recommender for job descriptions")
    parser.add_argument("--data", type=str, default="../data/processed/job_listings_clean.csv", help="CSV file with job listings")
    parser.add_argument("--query", type=str, required=False, help="Search query (e.g. 'data scientist')")
    parser.add_argument("--top", type=int, default=10, help="Number of results to show")
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        raise SystemExit(1)

    df = pd.read_csv(data_path)
    q = args.query or "data scientist"
    logger.info("Building TF-IDF matrix on %d documents", len(df))
    vec, mat = build_tfidf_matrix(df.get("job_description", "").fillna("").astype(str).tolist())
    logger.info("Query: %s", q)
    res = recommend_by_tfidf(q, df, text_field="job_description", top_n=args.top, vectorizer=vec, matrix=mat)
    print(res[["job_title", "company_name", "location", "_similarity_score"]].to_string(index=False))
