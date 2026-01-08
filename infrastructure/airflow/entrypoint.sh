#!/bin/bash
set -e

echo "Initializing Airflow database..."
airflow db migrate

echo "Checking existing users..."
airflow users list || true

echo "Creating admin user..."
airflow users create \
  --username admin \
  --password admin123 \
  --firstname Admin \
  --lastname User \
  --role Admin \
  --email admin@example.com 2>&1 || echo "User creation failed - user may already exist"

echo "Starting Airflow services..."
airflow webserver -p 8080 &
exec airflow scheduler
