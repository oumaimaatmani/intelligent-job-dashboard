# Intelligent Job Dashboard

## Overview
The Intelligent Job Dashboard is a Power BI project designed to visualize job listings data collected from the Adzuna API. This project provides insights into the French job market for data-related positions.

## Features
- Automated data collection with append mode (no file overwriting)
- Automatic deduplication based on unique job IDs
- Skills extraction from job descriptions
- Salary parsing and standardization
- Location standardization
- Search query tracking
- Clean and structured dataset ready for Power BI visualization

## Project Structure
```
intelligent-job-dashboard
├── src
│   ├── collect_data.py        # Data collection with append mode
│   ├── clean_data.py          # Data cleaning and transformation
│   └── config
│       ├── settings.yaml      # Configuration (API keys, locations, queries)
│       └── settings.example.yaml # Example configuration
├── data
│   ├── raw
│   │   ├── job_listings_raw.csv  # Raw collected data (append mode)
│   │   └── README.md          # Documentation about raw data
│   └── processed
│       └── job_listings_clean.csv # Cleaned dataset for Power BI
├── powerbi
│   └── IntelligentJobDashboard.pbix # Power BI dashboard file
├── docs
│   └── data_pipeline.md        # Documentation of the data pipeline
├── requirements.txt            # Python dependencies
├── .gitignore                  
└── README.md                   # This file
```

## Setup Instructions

### 1. Clone the repository
```bash
git clone https://github.com/oumaimaatmani/intelligent-job-dashboard.git
cd intelligent-job-dashboard
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure API credentials
Edit `src/config/settings.yaml` with your Adzuna API credentials:
```yaml
apis:
  adzuna:
    app_id: "YOUR_APP_ID"
    app_key: "YOUR_APP_KEY"
    country: "fr"
```

## Usage

### Data Collection (Append Mode)
All collections are automatically appended to the same file:

```bash
# Collect Data Engineer jobs
python src/collect_data.py --query "data engineer" --locations "Paris,Lyon,Marseille" --limit 1000

# Collect Data Scientist jobs (appends to existing file)
python src/collect_data.py --query "data scientist" --locations "Paris,Lyon,Marseille" --limit 1000

# Collect Data Analyst jobs (appends to existing file)
python src/collect_data.py --query "data analyst" --locations "Paris,Lyon,Marseille" --limit 1000
```

All data will be stored in: `data/raw/job_listings_raw.csv`

### Data Cleaning
```bash
python src/clean_data.py
```

Output: `data/processed/job_listings_clean.csv`

### Power BI Visualization
Open `powerbi/IntelligentJobDashboard.pbix` and refresh the data source to load the cleaned dataset.

## Search Queries Supported
- Data Engineer
- Data Scientist
- Data Analyst
- Machine Learning Engineer
- Business Intelligence
- Data Architect

## Locations Covered
- Paris
- Lyon
- Marseille
- Toulouse
- Bordeaux
- Lille
- Nantes
- Strasbourg
- Rennes
- Nice
- Montpellier

## Documentation
- **Data Pipeline**: See `docs/data_pipeline.md` for detailed pipeline documentation
- **Raw Data**: See `data/raw/README.md` for raw data structure information

## Key Features

### Append Mode
- All collections are added to the same file
- No data overwriting
- Automatic deduplication based on `job_id`

### Data Quality
- Automatic text cleaning (HTML removal, whitespace normalization)
- Skills extraction from descriptions
- Salary parsing (min/max)
- Location standardization
- Date format conversion

### Analytics Ready
- Days since posted calculation
- Salary availability indicator
- Skills availability indicator
- Search query tracking

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for enhancements or bug fixes.

## License
This project is licensed under the MIT License.