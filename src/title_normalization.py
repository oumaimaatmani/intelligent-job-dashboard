import re
from typing import Dict, Set

# Mapping de seniority (Senior, Sr, Lead, etc. -> standardisé)
SENIORITY_MAPPING: Dict[str, str] = {
    "senior": "senior",
    "sr": "senior",
    "sr.": "senior",
    "lead": "lead",
    "principal": "principal",
    "staff": "staff",
    "junior": "junior",
    "jr": "junior",
    "jr.": "junior",
    "intern": "intern",
    "internship": "intern",
    "entry": "entry-level",
    "entry-level": "entry-level",
    "mid": "mid-level",
    "mid-level": "mid-level",
    "experienced": "experienced",
}

# Mapping de rôles (synonymes -> forme standardisée)
ROLE_MAPPING: Dict[str, str] = {
    "data scientist": "data scientist",
    "data science": "data scientist",
    "machine learning engineer": "ml engineer",
    "ml engineer": "ml engineer",
    "mlops engineer": "mlops engineer",
    "machine learning ops": "mlops engineer",
    "backend engineer": "backend engineer",
    "backend developer": "backend engineer",
    "frontend engineer": "frontend engineer",
    "frontend developer": "frontend engineer",
    "full stack engineer": "full stack engineer",
    "full-stack engineer": "full stack engineer",
    "devops engineer": "devops engineer",
    "data engineer": "data engineer",
    "data pipeline": "data engineer",
    "analyst": "analyst",
    "data analyst": "data analyst",
    "business analyst": "business analyst",
    "analytics engineer": "analytics engineer",
}

# Mots à ignorer / suppression
STOPWORDS_TITLES: Set[str] = {
    "the", "a", "an", "and", "or", "in", "at", "on", "to", "for", "with",
    "experienced", "required", "wanted", "looking", "seek", "seeks", "hire", "hiring",
}


def normalize_seniority(title: str) -> str:
    """Extract and normalize seniority level from title.
    
    Returns the base title without seniority, and you should pair with seniority level separately.
    """
    title_lower = title.lower().strip()
    for keyword, normalized in SENIORITY_MAPPING.items():
        if keyword in title_lower:
            # Remove seniority keyword from title
            title_lower = re.sub(r'\b' + re.escape(keyword) + r'\b', '', title_lower, flags=re.IGNORECASE)
            return title_lower.strip()
    return title_lower


def normalize_role(title: str) -> str:
    """Normalize job role titles (map synonyms to standard forms)."""
    title_lower = title.lower().strip()
    
    # Try exact mapping first (longest matches first to avoid partial replacements)
    for key in sorted(ROLE_MAPPING.keys(), key=len, reverse=True):
        if key in title_lower:
            return ROLE_MAPPING[key]
    
    # Fallback: return cleaned version
    return title_lower


def clean_title(title: str) -> str:
    """Generic title cleaning: lowercase, remove extra whitespace, remove stopwords."""
    if not title or not isinstance(title, str):
        return ""
    
    title = title.lower().strip()
    # Remove extra whitespace
    title = re.sub(r'\s+', ' ', title)
    # Remove punctuation
    title = re.sub(r'[^\w\s]', '', title)
    return title


def normalize_job_title(title: str) -> str:
    """Full normalization: clean + normalize role + remove remaining seniority keywords."""
    if not title:
        return ""
    
    cleaned = clean_title(title)
    normalized = normalize_role(cleaned)
    # Final pass: remove seniority keywords from result
    normalized = normalize_seniority(normalized)
    return normalized.strip()


def add_normalized_title_column(df, input_col: str = "job_title", output_col: str = "job_title_normalized"):
    """Add normalized job title column to DataFrame."""
    df = df.copy()
    df[output_col] = df[input_col].fillna("").astype(str).apply(normalize_job_title)
    return df


if __name__ == "__main__":
    # Quick demo
    examples = [
        "Senior Data Scientist",
        "Lead ML Engineer",
        "Junior Backend Developer",
        "Data Science Engineer",
        "Sr. Full-Stack Developer",
    ]
    
    for ex in examples:
        normalized = normalize_job_title(ex)
        print(f"{ex:40} -> {normalized}")
