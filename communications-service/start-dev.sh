#!/bin/bash

# Development startup script for Communications Service
set -e

echo "🚀 Starting Communications Service in development mode..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip and install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Please create one with your configuration."
    echo "   You can use .env.example as a template."
    exit 1
fi

# Run database migrations
echo "🗄️  Running database migrations..."
alembic upgrade head

# Start the service
echo "🌟 Starting Communications Service on http://localhost:8003"
echo "📖 API Documentation: http://localhost:8003/api/v1/docs"
echo ""
echo "Press Ctrl+C to stop the service"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload