import os
import argparse
import time
import uuid
from typing import List, Dict, Any
from datetime import datetime

import requests
import pandas as pd
import yaml
from urllib.parse import quote_plus

CONFIG_PATH_PRIMARY = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
CONFIG_PATH_EXAMPLE = os.path.join(os.path.dirname(__file__), "config", "settings.example.yaml")
RAW_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "job_listings_raw.csv")


def load_config() -> Dict[str, Any]:
    path = CONFIG_PATH_PRIMARY if os.path.exists(CONFIG_PATH_PRIMARY) else CONFIG_PATH_EXAMPLE
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_parent_dir(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def uuid_from(*parts: str) -> str:
    base = "||".join([p for p in parts if p])
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def unify_schema(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    columns = [
        "job_id", "job_title", "company_name", "location", "posted_date",
        "job_description", "skills_required", "salary_range", "url", "source", "search_query"
    ]
    for c in columns:
        if c not in df.columns:
            df[c] = None
    return df[columns]


def fetch_adzuna_jobs(query: str, locations: List[str], limit: int, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    app_id = os.getenv("ADZUNA_APP_ID") or cfg.get("apis", {}).get("adzuna", {}).get("app_id")
    app_key = os.getenv("ADZUNA_APP_KEY") or cfg.get("apis", {}).get("adzuna", {}).get("app_key")
    country = cfg.get("apis", {}).get("adzuna", {}).get("country", "fr")

    if not app_id or not app_key:
        print("[ERROR] missing ADZUNA_APP_ID/ADZUNA_APP_KEY")
        return results

    per_page = 50
    total_fetched = 0
    
    for loc in locations:
        print(f"\n[INFO] Collecting for location: {loc}")
        fetched = 0
        page = 1
        
        while fetched < limit:
            url = (
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
                f"?app_id={quote_plus(app_id)}&app_key={quote_plus(app_key)}"
                f"&results_per_page={per_page}"
                f"&what={quote_plus(query)}"
                f"&where={quote_plus(loc)}"
                f"&content-type=application/json"
            )
            
            try:
                r = requests.get(url, timeout=30)
                if r.status_code != 200:
                    print(f"[WARNING] HTTP {r.status_code} page {page} loc '{loc}'")
                    break
                    
                data = r.json()
                hits = data.get("results", [])
                
                if not hits:
                    print(f"[INFO] End of pagination for '{loc}' at page {page}")
                    break
                
                for it in hits:
                    title = it.get("title")
                    company = (it.get("company") or {}).get("display_name")
                    location = (it.get("location") or {}).get("display_name")
                    created = it.get("created")
                    description = it.get("description")
                    url_job = it.get("redirect_url")
                    salary_min = it.get("salary_min")
                    salary_max = it.get("salary_max")
                    currency = it.get("salary_currency") or "EUR"
                    
                    salary_range = None
                    if salary_min and salary_max:
                        try:
                            salary_range = f"{int(salary_min):,} - {int(salary_max):,} {currency}".replace(",", " ")
                        except Exception:
                            salary_range = f"{salary_min} - {salary_max} {currency}"

                    job_id = uuid_from("adzuna", str(it.get("id") or ""), url_job or "", title or "", company or "")

                    results.append({
                        "job_id": job_id,
                        "job_title": title,
                        "company_name": company,
                        "location": location,
                        "posted_date": created,
                        "job_description": description,
                        "skills_required": None,
                        "salary_range": salary_range,
                        "url": url_job,
                        "source": "adzuna",
                        "search_query": query,
                    })
                    
                    fetched += 1
                    total_fetched += 1
                    
                    if fetched >= limit:
                        break
                
                print(f"[INFO] Page {page}: {len(hits)} jobs collected ({fetched}/{limit})")
                page += 1
                time.sleep(0.5)
                
            except Exception as e:
                print(f"[ERROR] Error during collection: {e}")
                break
    
    print(f"[INFO] Total collected: {total_fetched} jobs")
    return results


def parse_locations(arg: str) -> List[str]:
    if not arg:
        return ["France"]
    return [p.strip() for p in arg.replace(";", ",").split(",") if p.strip()]


def append_to_csv(new_data: pd.DataFrame, output_path: str) -> None:
    """
    Append new data to existing CSV file with automatic deduplication
    """
    ensure_parent_dir(output_path)
    
    if os.path.exists(output_path):
        try:
            existing_data = pd.read_csv(output_path, encoding='utf-8')
            print(f"\n[INFO] Existing file detected: {len(existing_data)} rows")
            
            # Combine old and new data
            combined_data = pd.concat([existing_data, new_data], ignore_index=True)
            
            # Remove duplicates based on job_id
            before_dedup = len(combined_data)
            combined_data = combined_data.drop_duplicates(subset=['job_id'], keep='first')
            after_dedup = len(combined_data)
            
            duplicates_removed = before_dedup - after_dedup
            new_entries = after_dedup - len(existing_data)
            
            print(f"[INFO] {duplicates_removed} duplicates removed")
            print(f"[INFO] {new_entries} new jobs added")
            print(f"[INFO] Total in file: {after_dedup} jobs")
            
            # Save
            combined_data.to_csv(output_path, index=False, encoding='utf-8')
            
        except Exception as e:
            print(f"[WARNING] Error reading existing file: {e}")
            print("[INFO] Creating new file...")
            new_data.to_csv(output_path, index=False, encoding='utf-8')
    else:
        print(f"\n[INFO] Creating new file: {output_path}")
        new_data.to_csv(output_path, index=False, encoding='utf-8')
        print(f"[INFO] {len(new_data)} jobs saved")


def main():
    parser = argparse.ArgumentParser(
        description="Collect job listings via Adzuna API with automatic append mode.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python collect_data.py --query "data engineer" --locations "Paris,Lyon,Marseille" --limit 500
  python collect_data.py --query "data scientist" --locations "France" --limit 1000
  python collect_data.py --query "data analyst" --locations "Ile-de-France,Rhone,PACA" --limit 300
  
APPEND MODE: New data is automatically added to existing file without overwriting!
        """
    )
    
    parser.add_argument("--query", type=str, required=True, 
                       help="Search keyword (e.g. 'data scientist', 'data engineer')")
    parser.add_argument("--locations", type=str, default="France", 
                       help="Comma-separated locations (e.g. 'Paris,Lyon,Marseille')")
    parser.add_argument("--limit", type=int, default=500, 
                       help="Maximum results per location (default: 500)")
    parser.add_argument("--output", type=str, default=RAW_DEFAULT_PATH, 
                       help="Output CSV file path")
    
    args = parser.parse_args()

    print("=" * 70)
    print("JOB COLLECTION STARTED")
    print("=" * 70)
    print(f"Query: {args.query}")
    print(f"Locations: {args.locations}")
    print(f"Limit per location: {args.limit}")
    print(f"Output file: {args.output}")
    print(f"Mode: APPEND (automatic)")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    cfg = load_config()
    locations = parse_locations(args.locations)

    rows = fetch_adzuna_jobs(args.query, locations, args.limit, cfg)
    
    if not rows:
        print("\n[ERROR] No data collected. Check API keys or query.")
        return

    df = unify_schema(rows)
    
    # Use append mode instead of overwriting
    append_to_csv(df, args.output)
    
    print("\n" + "=" * 70)
    print(f"COLLECTION COMPLETED: {args.output}")
    print("=" * 70)


if __name__ == "__main__":
    main()