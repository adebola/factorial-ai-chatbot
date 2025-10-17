#!/bin/bash
# FactorialBot Production Deployment Script
# This script handles the complete deployment process

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions for colored output
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# Configuration
COMPOSE_FILE="../docker-compose.yml"
ENV_FILE="../.env"

info "🚀 Starting FactorialBot Production Deployment"

# Step 1: Check prerequisites
info "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

success "Docker and Docker Compose are installed"

# Step 2: Check environment file
if [ ! -f "$ENV_FILE" ]; then
    warning "No .env file found. Creating from template..."
    cp ../.env.example "$ENV_FILE"
    warning "Please edit .env file with your production values before continuing."
    echo "Required variables:"
    echo "  - POSTGRES_PASSWORD"
    echo "  - JWT_SECRET_KEY"
    echo "  - OPENAI_API_KEY"
    echo "  - MINIO_ACCESS_KEY"
    echo "  - MINIO_SECRET_KEY"
    echo ""
    read -p "Press Enter after updating .env file..."
fi

success "Environment file exists"

# Step 3: Check required environment variables
info "Validating environment variables..."

source "$ENV_FILE"

missing_vars=()

if [ -z "$POSTGRES_PASSWORD" ]; then missing_vars+=("POSTGRES_PASSWORD"); fi
if [ -z "$JWT_SECRET_KEY" ]; then missing_vars+=("JWT_SECRET_KEY"); fi
if [ -z "$OPENAI_API_KEY" ]; then missing_vars+=("OPENAI_API_KEY"); fi

if [ ${#missing_vars[@]} -ne 0 ]; then
    error "Missing required environment variables: ${missing_vars[*]}"
    exit 1
fi

success "All required environment variables are set"

# Step 4: Stop existing containers
info "Stopping any existing containers..."
docker-compose -f "$COMPOSE_FILE" down --remove-orphans || true
success "Existing containers stopped"

# Step 5: Pull latest images
info "Pulling latest Docker images..."
docker-compose -f "$COMPOSE_FILE" pull
success "Images pulled successfully"

# Step 6: Start infrastructure services first
info "Starting infrastructure services..."
docker-compose -f "$COMPOSE_FILE" up -d postgres redis minio
success "Infrastructure services started"

# Wait for infrastructure to be ready
info "Waiting for infrastructure services to be ready..."
sleep 10

# Step 7: Run database migrations
info "Running database migrations..."
docker-compose -f "$COMPOSE_FILE" up chat-migration onboarding-migration billing-migration
success "Database migrations completed"

# Step 8: Start application services
info "Starting application services..."
docker-compose -f "$COMPOSE_FILE" up -d chat-service onboarding-service communications-service billing-service workflow-service
success "Application services started"

# Wait for services to be ready
info "Waiting for application services to be ready..."
sleep 15

# Step 9: Start gateway service
info "Starting gateway service..."
docker-compose -f "$COMPOSE_FILE" up -d gateway-service
success "Gateway service started"

# Step 10: Health checks
info "Performing health checks..."

# Wait a bit more for all services to fully start
sleep 10

# Check each service
services_healthy=true

# Check PostgreSQL
if docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    success "PostgreSQL is healthy"
else
    error "PostgreSQL health check failed"
    services_healthy=false
fi

# Check Redis
if docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping > /dev/null 2>&1; then
    success "Redis is healthy"
else
    error "Redis health check failed"
    services_healthy=false
fi

# Check Chat Service
if curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    success "Chat Service is healthy"
else
    error "Chat Service health check failed"
    services_healthy=false
fi

# Check Onboarding Service
if curl -f -s http://localhost:8001/health > /dev/null 2>&1; then
    success "Onboarding Service is healthy"
else
    error "Onboarding Service health check failed"
    services_healthy=false
fi

# Check Communications Service
if curl -f -s http://localhost:8003/health > /dev/null 2>&1; then
    success "Communications Service is healthy"
else
    warning "Communications Service health check failed"
fi

# Check Billing Service
if curl -f -s http://localhost:8004/health > /dev/null 2>&1; then
    success "Billing Service is healthy"
else
    error "Billing Service health check failed"
    services_healthy=false
fi

# Check Workflow Service
if curl -f -s http://localhost:8002/health > /dev/null 2>&1; then
    success "Workflow Service is healthy"
else
    error "Workflow Service health check failed"
    services_healthy=false
fi

# Check Gateway Service
if curl -f -s http://localhost:8080/actuator/health > /dev/null 2>&1; then
    success "Gateway Service is healthy"
else
    warning "Gateway Service health check failed (this might take a few more seconds)"
fi

if [ "$services_healthy" = true ]; then
    success "🎉 FactorialBot deployed successfully!"
    echo ""
    info "📊 Service URLs:"
    echo "   🌐 Main Application: http://localhost:8080"
    echo "   💬 Chat Service: http://localhost:8000"
    echo "   📝 Onboarding Service: http://localhost:8001"
    echo "   🔄 Workflow Service: http://localhost:8002"
    echo "   📧 Communications Service: http://localhost:8003"
    echo "   💳 Billing Service: http://localhost:8004"
    echo "   🔐 Authorization Server: http://localhost:9000"
    echo "   📁 MinIO Console: http://localhost:9001"
    echo ""
    info "📋 Useful commands:"
    echo "   📊 Check status: docker-compose -f $COMPOSE_FILE ps"
    echo "   📝 View logs: docker-compose -f $COMPOSE_FILE logs -f"
    echo "   🔄 Restart: docker-compose -f $COMPOSE_FILE restart"
    echo "   🛑 Stop: docker-compose -f $COMPOSE_FILE down"
else
    error "Some services failed health checks. Check logs with: docker-compose -f $COMPOSE_FILE logs"
    exit 1
fi