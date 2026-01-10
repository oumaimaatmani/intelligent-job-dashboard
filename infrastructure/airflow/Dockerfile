FROM apache/airflow:2.10.4-python3.11

# Install system dependencies for data processing and database libraries
USER root
RUN apt-get update && apt-get install -y \
    build-essential \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user for pip installations
USER airflow

# Install Python dependencies from requirements
RUN pip install --no-cache-dir \
    requests \
    pandas \
    beautifulsoup4 \
    numpy \
    pyyaml \
    scikit-learn \
    matplotlib \
    nltk \
    python-dateutil \
    joblib \
    spacy \
    psycopg2-binary \
    sqlalchemy \
    redis

# Download spacy model
RUN python -m spacy download en_core_web_sm || true
