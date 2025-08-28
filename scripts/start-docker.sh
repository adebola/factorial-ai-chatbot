#!/bin/bash

echo "Starting FactorialBot with Docker Compose..."

# Build and start all services
echo "Building and starting all services..."
docker-compose up --build -d

# Wait for services to be ready
echo "Waiting for services to initialize..."
sleep 30

# Check service status
echo ""
echo "Service Status:"
docker-compose ps

echo ""
echo "Services are starting up. You can access:"
echo "- Gateway Service: http://localhost:8080 (🎯 Main Entry Point)"
echo "- Chat Service: http://localhost:8000 (Direct access)"
echo "- Onboarding Service: http://localhost:8001 (Direct access)"
echo "- MinIO Console: http://localhost:9001"
echo "- PostgreSQL: localhost:5432"
echo "- Redis: localhost:6379"
echo ""
echo "🎯 Recommended: Use the Gateway Service (port 8080) for all API calls:"
echo "   - Documents: http://localhost:8080/api/v1/documents/"
echo "   - Tenants: http://localhost:8080/api/v1/tenants/"
echo "   - Chat: http://localhost:8080/api/v1/chat/"
echo ""
echo "To view logs: docker-compose logs -f [service-name]"
echo "To stop all services: docker-compose down"