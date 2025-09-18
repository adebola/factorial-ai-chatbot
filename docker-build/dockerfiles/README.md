# FactorialBot Dockerfiles

This directory contains all Dockerfiles for the FactorialBot services using consistent naming conventions.

## Directory Structure

```
dockerfiles/
├── chat-service.Dockerfile          # Python FastAPI chat service
├── onboarding-service.Dockerfile    # Python FastAPI onboarding service
├── authorization-server.Dockerfile  # Java Spring Authorization Server
├── gateway-service.Dockerfile       # Java Spring Cloud Gateway
└── README.md                        # This file
```

## Naming Convention

- **Service Name**: `{service-name}.Dockerfile`
- **Consistent**: All Dockerfiles follow the same pattern
- **Clear**: Service name matches the actual service directory

## Build Context

All Dockerfiles are designed to be built from the **backend root directory** with the following context:

```bash
# Build from backend root directory
cd /path/to/backend

# Build chat service
docker build --platform=linux/amd64 -f docker-build/dockerfiles/chat-service.Dockerfile -t adebola/chat-service .

# Build onboarding service
docker build --platform=linux/amd64 -f docker-build/dockerfiles/onboarding-service.Dockerfile -t adebola/onboarding-service .

# Build authorization server
docker build --platform=linux/amd64 -f docker-build/dockerfiles/authorization-service.Dockerfile -t adebola/ai-authorization-service .

# Build gateway service
docker build --platform=linux/amd64 -f docker-build/dockerfiles/gateway-service.Dockerfile -t adebola/ai-gateway-service .
```

## Automated Building

Use the build script to build all services at once:

```bash
cd docker-build
./build-all-services.sh           # Build all services
./build-all-services.sh --push    # Build and push to registry
./build-all-services.sh --push --save  # Build, push, and save tar files
```

## Service Details

### Python Services (FastAPI)

**Chat Service & Onboarding Service**:
- Base image: `python:3.11-slim`
- Non-root user: `appuser`
- Health checks: `/health` endpoint
- Port: 8000
- Workers: Configurable via environment

### Java Services (Spring Boot)

**Authorization Server & Gateway Service**:
- Multi-stage build: Maven build + JRE runtime
- Base images: `maven:3.9-eclipse-temurin-21` (build), `eclipse-temurin:21-jre-alpine` (runtime)
- Non-root user: `spring:spring`
- Health checks: `/actuator/health` endpoint
- JVM optimizations: G1GC, container support
- Authorization Server port: 9000
- Gateway Service port: 8080

## Security Features

All Dockerfiles include:
- ✅ Non-root user execution
- ✅ Multi-stage builds (where applicable)
- ✅ Health checks
- ✅ Minimal base images
- ✅ Security best practices

## Environment Variables

Each service supports these common environment variables:
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARN, ERROR)
- `ENVIRONMENT`: Environment (development, production)
- Service-specific variables (see individual service documentation)

## Maintenance

When updating Dockerfiles:
1. Maintain naming convention: `{service-name}.Dockerfile`
2. Test builds from backend root directory
3. Update this README if adding new services
4. Ensure security best practices are followed
5. Test health checks work correctly