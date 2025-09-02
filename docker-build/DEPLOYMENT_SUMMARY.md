# 🚀 FactorialBot Docker Deployment - Complete Setup

## 📁 Directory Structure

```
docker-build/
├── docker-compose.yml                  # Main orchestration file
├── .env.example                       # Environment variables template
├── README.md                          # Comprehensive documentation
├── DEPLOYMENT_SUMMARY.md              # This summary
├── Dockerfile.gateway-service         # Gateway service image build
├── Dockerfile.chat-service            # Chat service image build  
├── Dockerfile.onboarding-service      # Onboarding service image build
├── db-init/                           # Database initialization
│   ├── 01-init-databases.sql         # Creates 3 databases + extensions
│   └── 02-init-pgvector-schemas.sql  # Sets up pgvector schemas
├── scripts/                           # Deployment automation
│   ├── deploy.sh                      # Full deployment script
│   ├── build-and-push.sh             # Build & push images to Docker Hub
│   └── wait-for-migrations.sh        # Migration coordination
└── config/                            # Service configurations
    └── application-production.yml     # Spring Gateway production config
```

## 🎯 Key Features

### ✅ **Production-Ready Architecture**
- Single PostgreSQL instance with 3 databases (`vector_db`, `chatbot_db`, `onboard_db`)
- Automatic database initialization with pgvector extension
- Health checks for all services
- Proper dependency ordering with wait conditions

### ✅ **Automated Migrations** 
- Dedicated migration containers (`chat-migration`, `onboarding-migration`)
- Services wait for migrations to complete before starting
- No race conditions or startup issues

### ✅ **Docker Hub Ready**
- Pre-configured for `adebola/*` Docker Hub repositories
- Production-optimized Dockerfiles
- Multi-stage builds for smaller images
- Non-root users for security

### ✅ **Infrastructure Services**
- **PostgreSQL**: Single instance with pgvector extension
- **Redis**: Caching and session storage
- **MinIO**: File storage with web console

### ✅ **Application Services**
- **Gateway Service** (port 8080): Spring Cloud Gateway with CORS
- **Chat Service** (port 8000): FastAPI with WebSocket support
- **Onboarding Service** (port 8001): FastAPI with file upload & processing

## 🚀 Quick Start (3 Commands)

```bash
# 1. Copy docker-build directory to your server
# 2. Configure environment
cp .env.example .env
nano .env  # Add your OPENAI_API_KEY, passwords, etc.

# 3. Deploy everything
./scripts/deploy.sh
```

## 📋 Manual Deployment Steps

### 1. **Environment Setup**
```bash
# Required variables in .env
POSTGRES_PASSWORD=your-secure-password
JWT_SECRET_KEY=your-long-random-jwt-secret
OPENAI_API_KEY=sk-your-openai-key
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=your-secure-minio-password
```

### 2. **Build & Push Images** (if needed)
```bash
cd scripts
./build-and-push.sh v1.0.0 adebola
```

### 3. **Deploy Services**
```bash
# Option A: Use automated script
./scripts/deploy.sh

# Option B: Manual deployment
docker-compose up -d postgres redis minio  # Infrastructure
sleep 10
docker-compose up chat-migration onboarding-migration  # Migrations
docker-compose up -d chat-service onboarding-service gateway-service  # Services
```

## 🔧 Image Configuration

The deployment uses these Docker Hub images:
- `adebola/gateway-service:latest`
- `adebola/chat-service:latest`  
- `adebola/onboarding-service:latest`

### Build Command Examples:
```bash
# From the docker-build directory:
docker build -f Dockerfile.gateway-service -t adebola/gateway-service:latest ../
docker build -f Dockerfile -t adebola/chat-service:latest ../
docker build -f Dockerfile -t adebola/onboarding-service:latest ../
```

## 📊 Service Health Checks

All services include health checks:
- **PostgreSQL**: `pg_isready`
- **Redis**: `redis-cli ping`
- **Chat Service**: `GET /health`
- **Onboarding Service**: `GET /health`  
- **Gateway Service**: `GET /actuator/health`

## 🌐 Access Points

Once deployed:
- **Main Application**: http://localhost:8080
- **Chat Service Direct**: http://localhost:8000
- **Onboarding Service Direct**: http://localhost:8001
- **MinIO Console**: http://localhost:9001

## 🔄 Database Migration Strategy

1. **Infrastructure starts first**: PostgreSQL, Redis, MinIO
2. **Database initialization**: Runs SQL scripts in `db-init/`
3. **Migration containers run**: Apply Alembic migrations
4. **Services start**: Only after migrations complete successfully
5. **Health checks verify**: All services are ready

## 🛠️ Maintenance Commands

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs -f service-name

# Update services  
docker-compose pull && docker-compose up -d

# Restart specific service
docker-compose restart chat-service

# Scale services
docker-compose up -d --scale chat-service=3

# Backup database
docker-compose exec postgres pg_dumpall -U postgres > backup.sql

# Stop everything
docker-compose down
```

## 🔐 Security Considerations

- Change all default passwords in `.env`
- Use strong JWT secrets (50+ character random strings)
- Restrict external access to ports 8000, 8001 (use 8080 as main entry)
- Consider adding HTTPS with nginx reverse proxy
- Regularly update Docker images
- Monitor logs for security issues

## 🎉 Success Indicators

Deployment is successful when:
- ✅ All containers show "healthy" status
- ✅ Gateway responds at http://localhost:8080
- ✅ Services respond to health checks
- ✅ Database migrations completed without errors
- ✅ No error messages in logs

## 📞 Troubleshooting

Common issues and solutions:
- **Services won't start**: Check `.env` file variables
- **Database connection errors**: Verify PostgreSQL health and passwords
- **Migration failures**: Check database exists and permissions
- **Port conflicts**: Ensure ports 8000, 8001, 8080 are available
- **Memory issues**: Increase Docker memory limits or reduce workers

## 🎯 Next Steps

After successful deployment:
1. Configure your frontend to use http://localhost:8080
2. Create your first tenant via the onboarding API
3. Upload documents and test the chat functionality
4. Set up monitoring and log aggregation
5. Configure automated backups
6. Add SSL/HTTPS for production use

The system is now production-ready! 🚀