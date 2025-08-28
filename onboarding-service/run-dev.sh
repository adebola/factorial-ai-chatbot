#!/bin/bash

echo "Starting Onboarding Service in development mode..."
echo "Excluding venv/ directory from file watching..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# Start the service with file watching exclusions
uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8001 \
  --reload \
  --reload-exclude="venv/*" \
  --reload-exclude="*.pyc" \
  --reload-exclude="__pycache__/*" \
  --reload-exclude="*.log" \
  --reload-exclude="chroma_db/*" \
  --reload-exclude="onborading_migrations/versions/*" \
  --reload-exclude="*.sqlite3" \
  --reload-exclude=".git/*"

echo "Service stopped"