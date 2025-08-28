#!/bin/bash

echo "Starting FactorialBot Development Environment..."

# Start infrastructure services
echo "Starting infrastructure services..."
docker-compose up -d postgres redis minio

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 10

# Start chat service
echo "Starting chat service..."
cd chat-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude="venv/*" --reload-exclude="*.pyc" --reload-exclude="__pycache__/*" --reload-exclude="*.log" &
CHAT_PID=$!

# Start onboarding service
echo "Starting onboarding service..."
cd ../onboarding-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload --reload-exclude="venv/*" --reload-exclude="*.pyc" --reload-exclude="__pycache__/*" --reload-exclude="*.log" &
ONBOARD_PID=$!

# Start gateway service
echo "Starting gateway service..."
cd ../gateway-service
./mvnw spring-boot:run &
GATEWAY_PID=$!

echo "Services started:"
echo "- Gateway Service: http://localhost:8080 (Main Entry Point)"
echo "- Chat Service: http://localhost:8000"
echo "- Onboarding Service: http://localhost:8001"
echo "- MinIO Console: http://localhost:9001"
echo "- PostgreSQL: localhost:5432"
echo "- Redis: localhost:6379"
echo ""
echo "🎯 Use the Gateway Service (port 8080) to access all APIs:"
echo "   - Documents: http://localhost:8080/api/v1/documents/"
echo "   - Tenants: http://localhost:8080/api/v1/tenants/"
echo "   - Chat: http://localhost:8080/api/v1/chat/"

# Function to cleanup on exit
cleanup() {
    echo "Shutting down services..."
    kill $CHAT_PID $ONBOARD_PID $GATEWAY_PID 2>/dev/null
    docker-compose down
    exit 0
}

# Trap SIGINT and SIGTERM
trap cleanup SIGINT SIGTERM

# Wait for background processes
wait