# Gateway Service Docker Integration

## 🚀 Changes Made

### **Files Created:**

1. **Gateway Service Docker Files:**
   - `gateway-service/Dockerfile` - Multi-stage Docker build for Spring Boot app
   - `gateway-service/.dockerignore` - Optimized Docker context
   - `gateway-service/src/main/resources/application-docker.yml` - Docker-specific configuration

2. **Startup Scripts:**
   - `scripts/start-docker.sh` - Complete Docker Compose deployment script

3. **Configuration Files:**
   - `gateway-service/src/main/java/io/factorialsystems/gatewayservice/config/CorsConfig.java` - CORS configuration

### **Files Modified:**

1. **docker-compose.yml** - Added gateway service definition
2. **scripts/start-dev.sh** - Updated to include gateway service
3. **gateway-service/src/main/resources/application.yml** - Cleaned up configuration

## 📋 Docker Setup

### **Service Architecture:**
```
┌─────────────────┐
│  Gateway:8080   │ ← Main Entry Point
└─────────────────┘
        │
        ├─────────────────────┐
        │                     │
┌───────▼─────────┐   ┌──────▼──────────┐
│ Chat Service    │   │ Onboarding      │
│ :8000           │   │ Service :8001   │
└─────────────────┘   └─────────────────┘
        │                     │
        └─────────┬───────────┘
                  │
    ┌─────────────▼─────────────┐
    │  Infrastructure Services  │
    │ PostgreSQL, Redis, MinIO  │
    └───────────────────────────┘
```

### **Docker Services:**

**Gateway Service:**
- **Port**: 8080 (exposed)
- **Internal Communication**: Uses Docker service names
- **Dependencies**: chat-service, onboarding-service
- **Profile**: Uses `docker` profile for container-specific configuration

**Service URLs in Docker:**
- Gateway: `gateway-service:8080`
- Chat: `chat-service:8000`
- Onboarding: `onboarding-service:8000`

## 🛠️ Usage

### **Option 1: Docker Compose (Recommended for Production-like testing)**
```bash
# Start all services in Docker
./scripts/start-docker.sh

# Or manually:
docker-compose up --build -d

# View logs
docker-compose logs -f gateway-service
docker-compose logs -f chat-service
docker-compose logs -f onboarding-service

# Stop all services
docker-compose down
```

### **Option 2: Development Mode (Local services + Docker infrastructure)**
```bash
# Start infrastructure + local services + gateway
./scripts/start-dev.sh
```

## 🔧 Configuration Details

### **Environment Variables (Docker):**
```yaml
gateway-service:
  environment:
    - SPRING_PROFILES_ACTIVE=docker
    - CHAT_SERVICE_URL=http://chat-service:8000
    - ONBOARDING_SERVICE_URL=http://onboarding-service:8000
```

### **Service Discovery:**
- **Development**: Uses `localhost:port` URLs
- **Docker**: Uses Docker service names (`chat-service:8000`, `onboarding-service:8000`)

### **Port Mappings:**
- **Gateway**: `8080:8080`
- **Chat**: `8000:8000` 
- **Onboarding**: `8001:8000` (External 8001 → Internal 8000)

## 🌐 API Access

### **Through Gateway (Recommended):**
```bash
# Document operations
curl http://localhost:8080/api/v1/documents/

# Tenant operations
curl http://localhost:8080/api/v1/tenants/

# Chat operations
curl http://localhost:8080/api/v1/chat/

# Health checks
curl http://localhost:8080/health/chat
curl http://localhost:8080/health/onboarding
```

### **Direct Service Access (Still available):**
```bash
# Direct to services (bypass gateway)
curl http://localhost:8000/api/v1/chat/      # Chat service
curl http://localhost:8001/api/v1/tenants/   # Onboarding service
```

## 🔍 Monitoring

### **Health Checks:**
```bash
# Gateway health
curl http://localhost:8080/actuator/health

# Service health through gateway
curl http://localhost:8080/health/chat
curl http://localhost:8080/health/onboarding

# Direct service health
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### **Docker Logs:**
```bash
# View all services
docker-compose logs -f

# View specific service
docker-compose logs -f gateway-service
docker-compose logs -f chat-service
docker-compose logs -f onboarding-service

# View recent logs
docker-compose logs --tail=100 gateway-service
```

## 🚦 Startup Order

Docker Compose ensures proper startup order:

1. **Infrastructure**: postgres, redis, minio
2. **Backend Services**: chat-service, onboarding-service
3. **Gateway**: gateway-service (depends on backend services)

## 🔧 Troubleshooting

### **Common Issues:**

1. **Gateway can't reach services:**
   - Check Docker network: `docker network ls`
   - Verify service names in `application-docker.yml`

2. **Services not starting:**
   - Check logs: `docker-compose logs [service-name]`
   - Verify Dockerfile builds: `docker-compose build [service-name]`

3. **Port conflicts:**
   - Stop local services before Docker: `pkill -f uvicorn`
   - Check port usage: `lsof -i :8080`

### **Development Tips:**

1. **Rebuild after changes:**
   ```bash
   docker-compose build gateway-service
   docker-compose up -d gateway-service
   ```

2. **Debug gateway routing:**
   ```bash
   # Check gateway logs
   docker-compose logs -f gateway-service
   
   # Test specific routes
   curl -v http://localhost:8080/api/v1/documents/
   ```

## 🎯 Next Steps

1. **Frontend Integration**: Update frontend to use `http://localhost:8080` as base URL
2. **Load Testing**: Test gateway performance under load
3. **Security**: Add OAuth2.0 integration to gateway
4. **Monitoring**: Add metrics and tracing
5. **Production**: Configure for production deployment with proper secrets management