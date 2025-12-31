import re
import logging
from typing import List, Set, Optional, Dict

logger = logging.getLogger(__name__)
SPACY_AVAILABLE = False

# Small default skills vocabulary — extend this with your project-specific list
DEFAULT_SKILLS_VOCAB: Set[str] = {
    "python", "sql", "spark", "aws", "docker", "kubernetes", "pandas", "numpy",
    "scikit-learn", "tensorflow", "pytorch", "excel", "hadoop", "scala", "r",
}

# simple normalization mapping
NORMALIZATION_MAP: Dict[str, str] = {
    "scikit": "scikit-learn",
    "sklearn": "scikit-learn",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "py": "python",
}


def normalize_skill(token: str) -> str:
    t = token.lower().strip()
    return NORMALIZATION_MAP.get(t, t)


def extract_skills_from_text(text: str, skills_vocab: Optional[Set[str]] = None, use_spacy: bool = True, spacy_model: str = "en_core_web_sm") -> List[str]:
    """Extracts and normalizes skills from free text.

    Strategy:
    - If spaCy is available and requested, extract noun chunks and tokens and match against `skills_vocab`.
    - Otherwise, fallback to regex token matching.
    """
    if not text or not isinstance(text, str):
        return []

    vocab = skills_vocab or DEFAULT_SKILLS_VOCAB
    found: Set[str] = set()

    txt = text.lower()

    if use_spacy:
        try:
            import importlib
            spacy = importlib.import_module("spacy")
            try:
                nlp = spacy.load(spacy_model)
            except Exception as e:
                logger.debug("spaCy model load failed (%s). Falling back to regex.", e)
                nlp = None

            if nlp:
                doc = nlp(txt)
                # check noun chunks and tokens
                candidates = set([chunk.text.strip() for chunk in doc.noun_chunks])
                candidates.update([token.text for token in doc if not token.is_stop and token.is_alpha])
                for c in candidates:
                    c_norm = normalize_skill(re.sub(r"[^a-z0-9\-\+\.# ]", " ", c))
                    if c_norm in vocab:
                        found.add(c_norm)
        except Exception as e:
            logger.debug("spaCy not available or failed to import (%s). Falling back to regex.", e)

    # fallback / additional regex matching: find tokens and match against vocab
    tokens = re.findall(r"\b[a-z0-9\+\-\.\#]{2,}\b", txt)
    for t in tokens:
        t_norm = normalize_skill(t)
        if t_norm in vocab:
            found.add(t_norm)

    return sorted(found)


def add_skills_column(df, text_field: str = "job_description", out_field: str = "skills_required", skills_vocab: Optional[Set[str]] = None, use_spacy: bool = False, spacy_model: str = "en_core_web_sm"):
    df = df.copy()
    df[out_field] = df[text_field].fillna("").astype(str).apply(lambda t: extract_skills_from_text(t, skills_vocab=skills_vocab, use_spacy=use_spacy, spacy_model=spacy_model))
    return df


if __name__ == "__main__":
    # simple demo
    demo = "Looking for senior data scientist with Python, SQL, AWS and experience with TensorFlow or PyTorch."
    print(extract_skills_from_text(demo))
