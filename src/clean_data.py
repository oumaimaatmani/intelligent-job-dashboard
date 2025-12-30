import os
import argparse
import re
import pandas as pd
from datetime import datetime
from typing import Optional

RAW_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "job_listings_raw.csv")
CLEAN_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "job_listings_clean.csv")


def ensure_parent_dir(path: str) -> None:
    """Create parent directory if it doesn't exist"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean text by removing extra whitespace and HTML tags"""
    if pd.isna(text) or text is None:
        return None
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', str(text))
    # Remove multiple whitespaces
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text if text else None


def extract_skills(description: Optional[str]) -> Optional[str]:
    """Extract technical skills from job description"""
    if pd.isna(description) or description is None:
        return None
    
    # List of common technical skills
    skills_keywords = [
        'Python', 'Java', 'SQL', 'R', 'Scala', 'JavaScript', 'TypeScript', 'C++', 'C#',
        'Spark', 'Hadoop', 'Kafka', 'Airflow', 'dbt', 'Snowflake', 'Databricks',
        'AWS', 'Azure', 'GCP', 'Cloud', 'Docker', 'Kubernetes',
        'Tableau', 'Power BI', 'Looker', 'Qlik', 'Excel',
        'Machine Learning', 'Deep Learning', 'IA', 'NLP', 'Computer Vision',
        'ETL', 'Data Warehouse', 'Data Lake', 'Big Data',
        'Pandas', 'NumPy', 'Scikit-learn', 'TensorFlow', 'PyTorch',
        'Git', 'CI/CD', 'Agile', 'Scrum', 'REST API',
        'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Elasticsearch',
        'Jenkins', 'Terraform', 'Ansible'
    ]
    
    found_skills = []
    description_lower = description.lower()
    
    for skill in skills_keywords:
        # Case-insensitive search with word boundaries
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, description_lower):
            found_skills.append(skill)
    
    return ', '.join(sorted(set(found_skills))) if found_skills else None


def standardize_location(location: Optional[str]) -> Optional[str]:
    """Standardize location names"""
    if pd.isna(location) or location is None:
        return None
    
    location = str(location).strip()
    
    # Remove details in parentheses
    location = re.sub(r'\([^)]*\)', '', location).strip()
    
    # Remove arrondissement numbers (e.g., "Paris 1er" -> "Paris")
    location = re.sub(r'\s+\d+(er|e|ème)?\s*', ' ', location).strip()
    
    # Proper capitalization
    location = location.title()
    
    return location if location else None


def parse_salary(salary_range: Optional[str]) -> tuple:
    """Extract min and max salary from salary_range string"""
    if pd.isna(salary_range) or salary_range is None:
        return None, None
    
    # Extract numbers
    numbers = re.findall(r'[\d\s]+', str(salary_range))
    numbers = [int(n.replace(' ', '')) for n in numbers if n.strip()]
    
    if len(numbers) >= 2:
        return min(numbers), max(numbers)
    elif len(numbers) == 1:
        return numbers[0], numbers[0]
    
    return None, None


def clean_job_data(input_path: str, output_path: str) -> None:
    """Clean job listings data"""
    
    print("=" * 70)
    print("DATA CLEANING STARTED")
    print("=" * 70)
    print(f"Input file: {input_path}")
    print(f"Output file: {output_path}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Load data
    try:
        df = pd.read_csv(input_path, encoding='utf-8')
        print(f"\n[INFO] Data loaded successfully: {len(df)} rows")
    except Exception as e:
        print(f"\n[ERROR] Failed to load data: {e}")
        return
    
    initial_count = len(df)
    
    # 1. Remove duplicates
    df = df.drop_duplicates(subset=['job_id'])
    duplicates_removed = initial_count - len(df)
    print(f"\n[STEP 1] Duplicates removed: {duplicates_removed}")
    
    # 2. Clean job title
    df['job_title'] = df['job_title'].apply(clean_text)
    df = df[df['job_title'].notna()]
    no_title_removed = initial_count - duplicates_removed - len(df)
    print(f"[STEP 2] Rows without title removed: {no_title_removed}")
    
    # 3. Clean company name
    df['company_name'] = df['company_name'].apply(clean_text)
    df['company_name'] = df['company_name'].fillna('Unknown Company')
    
    # 4. Standardize location
    df['location'] = df['location'].apply(standardize_location)
    df['location'] = df['location'].fillna('Unknown Location')
    
    # 5. Clean description
    df['job_description'] = df['job_description'].apply(clean_text)
    
    # 6. Extract skills
    print("[STEP 3] Extracting skills from descriptions...")
    df['skills_required'] = df['job_description'].apply(extract_skills)
    
    # 7. Parse salary
    print("[STEP 4] Parsing salary information...")
    df[['salary_min', 'salary_max']] = df['salary_range'].apply(
        lambda x: pd.Series(parse_salary(x))
    )
    
    # 8. Convert dates
    print("[STEP 5] Converting date formats...")
    df['posted_date'] = pd.to_datetime(df['posted_date'], errors='coerce')
    df['posted_date'] = df['posted_date'].dt.strftime('%Y-%m-%d')
    
    # 9. Add calculated columns
    df['days_since_posted'] = (
        pd.Timestamp.now() - pd.to_datetime(df['posted_date'], errors='coerce')
    ).dt.days
    
    df['has_salary'] = df['salary_range'].notna()
    df['has_skills'] = df['skills_required'].notna()
    
    # 10. Reorder columns
    column_order = [
        'job_id', 'job_title', 'company_name', 'location', 'posted_date',
        'days_since_posted', 'job_description', 'skills_required',
        'salary_range', 'salary_min', 'salary_max', 'has_salary', 'has_skills',
        'url', 'source', 'search_query'
    ]
    
    # Add missing columns
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    
    df = df[column_order]
    
    # 11. Save cleaned data
    ensure_parent_dir(output_path)
    df.to_csv(output_path, index=False, encoding='utf-8')
    
    # Final statistics
    print("\n" + "=" * 70)
    print("DATA CLEANING COMPLETED")
    print("=" * 70)
    print(f"[STATS] Final rows: {len(df)}")
    print(f"[STATS] With salary: {df['has_salary'].sum()} ({df['has_salary'].mean()*100:.1f}%)")
    print(f"[STATS] With skills: {df['has_skills'].sum()} ({df['has_skills'].mean()*100:.1f}%)")
    print(f"[STATS] Unique companies: {df['company_name'].nunique()}")
    print(f"[STATS] Unique locations: {df['location'].nunique()}")
    if 'search_query' in df.columns:
        print(f"[STATS] Search queries: {df['search_query'].nunique()}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Clean job listings data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python clean_data.py
  python clean_data.py --input data/raw/job_listings_raw.csv --output data/processed/job_listings_clean.csv
        """
    )
    
    parser.add_argument("--input", type=str, default=RAW_DEFAULT_PATH,
                       help="Input raw CSV file path")
    parser.add_argument("--output", type=str, default=CLEAN_DEFAULT_PATH,
                       help="Output cleaned CSV file path")
    
    args = parser.parse_args()
    clean_job_data(args.input, args.output)


if __name__ == "__main__":
    main()