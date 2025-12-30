# Data Pipeline Documentation for Intelligent Job Dashboard

## Overview
The data pipeline for the Intelligent Job Dashboard consists of several key steps that transform raw job listing data into a clean and structured dataset suitable for analysis and visualization in Power BI.

## Steps in the Data Pipeline

### 1. Data Collection (APPEND MODE)
- **Source**: Job listings 
are collected from Adzuna API
- **Method**: The `collect_data.py` script collects job listings using the Adzuna API
- **Append Mode**: 
  - All queries are automatically appended to: `data/raw/job_listings_raw.csv`
  - Automatic deduplication based on `job_id`
  - No manual file merging required
  - Search query tracked in `search_query` column
- **Output**: Single raw CSV file with all collected job listings

### 2. Automated Collection
- **Queries Covered**:
  - Data Engineer (1000 per location)
  - Data Scientist (1000 per location)
  - Data Analyst (1000 per location)
  - Machine Learning Engineer (1000 per location)
  - Business Intelligence (1000 per location)
  - Data Architect (500 per location)
- **Locations**: Major French cities (Paris, Lyon, Marseille, Toulouse, Bordeaux)
- **Estimated Total**: ~5500 unique job listings

### 3. Data Storage
- **Raw Data**: `data/raw/job_listings_raw.csv`
- **Structure**: Single unified file with automatic deduplication
- **Benefits**: 
  - No file management overhead
  - Immediate availability for cleaning
  - Historical data preserved
  - Search query tracking

### 4. Data Cleaning
- **Script**: `clean_data.py`
- **Process**:
  - Remove duplicates based on job_id
  - Clean and standardize text fields
  - Extract skills from job descriptions
  - Parse salary information
  - Standardize location names
  - Convert date formats
  - Add calculated columns (days_since_posted, has_salary, has_skills)
- **Libraries**: pandas, re (regex)
- **Output**: `data/processed/job_listings_clean.csv`

### 5. Final Dataset Structure
- **Format**: Clean CSV ready for Power BI import
- **Columns**:
  - `job_id`: Unique identifier (UUID)
  - `job_title`: Cleaned job title
  - `company_name`: Company name
  - `location`: Standardized location
  - `posted_date`: Date in YYYY-MM-DD format
  - `days_since_posted`: Days since posting
  - `job_description`: Cleaned description
  - `skills_required`: Extracted technical skills
  - `salary_range`: Original salary string
  - `salary_min`: Minimum salary (numeric)
  - `salary_max`: Maximum salary (numeric)
  - `has_salary`: Boolean indicator
  - `has_skills`: Boolean indicator
  - `url`: Job listing URL
  - `source`: Data source (adzuna)
  - `search_query`: Original search query

### 6. Power BI Integration
- **Import**: Load `job_listings_clean.csv` into Power BI
- **Visualizations**: Create dashboards for job market insights

## Workflow Summary

```bash
# Step 1: Collect all data (append mode - all in one file)
python src/collect_data.py --query "data engineer" --locations "Paris,Lyon,Marseille,Toulouse,Bordeaux" --limit 1000
python src/collect_data.py --query "data scientist" --locations "Paris,Lyon,Marseille,Toulouse,Bordeaux" --limit 1000
python src/collect_data.py --query "data analyst" --locations "Paris,Lyon,Marseille,Toulouse,Bordeaux" --limit 1000
python src/collect_data.py --query "machine learning engineer" --locations "Paris,Lyon,Marseille,Toulouse" --limit 1000
python src/collect_data.py --query "business intelligence" --locations "Paris,Lyon,Marseille,Toulouse" --limit 1000
python src/collect_data.py --query "data architect" --locations "Paris,Lyon,Marseille" --limit 500

# Step 2: Clean the collected data
python src/clean_data.py

# Step 3: Import into Power BI
# File: data/processed/job_listings_clean.csv
```

## Key Features

1. **Single File Storage**: All data centralized in one place
2. **Automatic Deduplication**: No duplicate job listings
3. **Append Mode**: New collections add to existing data
4. **Query Tracking**: `search_query` column tracks the original search term
5. **Skills Extraction**: Automated extraction of technical skills
6. **Salary Parsing**: Automated parsing of salary ranges
7. **Simplified Workflow**: No manual file merging required

## Data Quality Metrics

The cleaning process provides statistics on:
- Total number of job listings
- Percentage with salary information
- Percentage with extracted skills
- Number of unique companies
- Number of unique locations
- Number of search queries used