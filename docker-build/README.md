# 🐳 FactorialBot Docker Deployment

This directory contains all the necessary files to deploy FactorialBot to a production Docker environment.

## 📋 Prerequisites

- Docker (20.10+)
- Docker Compose (2.0+)
- OpenAI API Key
- Access to Docker Hub (for pulling images)

**🍎 M1 Mac Users**: All Docker images are built for Intel/AMD64 platform using the `--platform=linux/amd64` build flag for maximum compatibility. This avoids Dockerfile warnings while ensuring cross-platform builds work correctly on M1 Macs.

## 🏗️ Architecture Overview

The deployment includes:
- **PostgreSQL** (single instance with 3 databases: `vector_db`, `chatbot_db`, `onboard_db`)
- **Redis** (caching and sessions)
- **MinIO** (file storage)
- **Gateway Service** (Spring Cloud Gateway on port 8080)
- **Chat Service** (FastAPI on port 8000)
- **Onboarding Service** (FastAPI on port 8001)

## 🚀 Quick Deployment

### 1. Download this directory
Copy the entire `docker-build` directory to your production server.

### 2. Configure environment variables
```bash
cp .env.example .env
nano .env  # Edit with your production values
```

Required environment variables:
- `POSTGRES_PASSWORD` - Database password
- `JWT_SECRET_KEY` - JWT signing key (use a long, random string)
- `OPENAI_API_KEY` - Your OpenAI API key
- `MINIO_ACCESS_KEY` & `MINIO_SECRET_KEY` - MinIO credentials

### 3. Start the services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 4. Verify deployment
- Gateway: http://localhost:8080
- Chat Service: http://localhost:8000/health
- Onboarding Service: http://localhost:8001/health
- MinIO Console: http://localhost:9001

## 🔧 Building Images (for developers)

If you need to build and push custom images:

```bash
# Login to Docker Hub
docker login

# Build and push all images
cd scripts
./build-and-push.sh v1.0.0 adebola

# Or build individual services (Intel/AMD64 compatible for M1 Macs)
docker build --platform=linux/amd64 -f Dockerfile.gateway-service -t adebola/gateway-service:latest ../
docker build --platform=linux/amd64 -f Dockerfile.chat-service -t adebola/chat-service:latest ../
docker build --platform=linux/amd64 -f Dockerfile.onboarding-service -t adebola/onboarding-service:latest ../
docker push adebola/chat-service:latest
```

## 💾 Database Setup

The deployment automatically:
1. Creates PostgreSQL with pgvector extension
2. Initializes 3 databases: `vector_db`, `chatbot_db`, `onboard_db`
3. Runs Alembic migrations for both services
4. Sets up proper schemas and permissions

### Database Access
```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres

# List databases
\l

# Connect to specific database
\c chatbot_db
```

## 🔄 Database Migrations

Migrations run automatically during startup via dedicated migration containers:
- `chat-migration`: Runs chat service migrations
- `onboarding-migration`: Runs onboarding service migrations

### Manual Migration (if needed)
```bash
# Run chat service migrations
docker-compose run --rm chat-service alembic upgrade head

# Run onboarding service migrations
docker-compose run --rm onboarding-service bash -c "PYTHONPATH=/app alembic upgrade head"
```

## 🔍 Service Details

### Gateway Service (Port 8080)
- Spring Cloud Gateway with reactive routing
- CORS handling for frontend applications
- Routes requests to appropriate backend services
- Health check: `/actuator/health`

### Chat Service (Port 8000)
- FastAPI with WebSocket support
- Real-time chat with AI responses
- Vector search capabilities
- Admin endpoints for chat management
- Health check: `/health`

### Onboarding Service (Port 8001)
- FastAPI for tenant management
- Document upload and processing
- Website scraping
- JWT authentication
- Plans and subscription management
- Health check: `/health`

## 📊 Monitoring and Logs

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f chat-service
docker-compose logs -f onboarding-service
docker-compose logs -f gateway-service

# Database logs
docker-compose logs -f postgres
```

### Health checks
```bash
# Check all service status
docker-compose ps

# Gateway health
curl http://localhost:8080/actuator/health

# Chat service health
curl http://localhost:8000/health

# Onboarding service health
curl http://localhost:8001/health
```

## 🛠️ Maintenance

### Update services
```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose up -d
```

### Backup data
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dumpall -U postgres > backup.sql

# Backup volumes
docker run --rm -v factorialbot_postgres_data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres_backup.tar.gz /data
```

### Scale services
```bash
# Scale chat service
docker-compose up -d --scale chat-service=3

# Scale onboarding service  
docker-compose up -d --scale onboarding-service=2
```

## 🔧 Troubleshooting

### Service won't start
1. Check logs: `docker-compose logs service-name`
2. Verify environment variables in `.env`
3. Ensure all required ports are available
4. Check disk space and memory

### Database connection issues
1. Verify PostgreSQL is running: `docker-compose ps postgres`
2. Check database initialization logs: `docker-compose logs postgres`
3. Test connection: `docker-compose exec postgres psql -U postgres -c "SELECT version();"`

### Migration failures
1. Check migration logs: `docker-compose logs chat-migration onboarding-migration`
2. Verify database exists: `docker-compose exec postgres psql -U postgres -c "\l"`
3. Run migrations manually if needed

### High memory usage
1. Reduce worker count in services
2. Add memory limits to docker-compose.yml
3. Monitor with: `docker stats`

## 🔐 Security Notes

- Change default passwords in `.env`
- Use strong JWT secret keys
- Restrict database access in production
- Enable firewall rules for ports 8000, 8001, 8080
- Consider using HTTPS with a reverse proxy
- Regularly update Docker images

## 📁 File Structure

```
docker-build/
├── docker-compose.yml          # Main deployment configuration
├── .env.example               # Environment variables template
├── Dockerfile.gateway-service # Gateway service Docker build
├── Dockerfile.chat-service    # Chat service Docker build  
├── Dockerfile.onboarding-service # Onboarding service Docker build
├── db-init/                   # Database initialization scripts
│   ├── 01-init-databases.sql
│   └── 02-init-pgvector-schemas.sql
├── scripts/                   # Deployment scripts
│   ├── build-and-push.sh      # Build and push Docker images
│   └── wait-for-migrations.sh # Migration wait script
└── README.md                  # This file
```

## 🆘 Support

For issues or questions:
1. Check the logs first: `docker-compose logs -f`
2. Verify environment variables are correct
3. Ensure Docker and Docker Compose are up to date
4. Check system resources (CPU, memory, disk space)

## 🎉 Success!

Once deployed, your FactorialBot instance will be available at:
- **Main Application**: http://localhost:8080
- **API Documentation**: http://localhost:8080/api/v1/openapi.json
- **MinIO Console**: http://localhost:9001 (for file management)

The system is now ready for production use! 🚀