# Multi-Platform Docker Build Guide

This guide explains how to build FactorialBot services for multiple architectures (AMD64 and ARM64) to solve platform compatibility issues.

## Problem Statement

When building Docker images on ARM64 machines (Apple Silicon) and deploying to AMD64 servers, you may encounter:

```
The requested image's platform (linux/arm64) does not match the detected host platform (linux/amd64/v4) and no specific platform was requested
```

## Solution

Use Docker Buildx for multi-platform builds that create images compatible with both ARM64 and AMD64 architectures.

## Prerequisites

1. **Docker Buildx** (included in Docker Desktop 19.03+ and Docker CE 19.03+)
2. **QEMU** for cross-platform emulation (usually included with Docker Desktop)

### Verify Buildx Installation

```bash
# Check if buildx is available
docker buildx version

# List available builders
docker buildx ls

# Check supported platforms
docker buildx inspect --bootstrap
```

## Quick Start

### 1. Build All Services (Multi-Platform)

```bash
cd docker-build

# Build for both AMD64 and ARM64 (default)
./build-all-services.sh --push

# Build and push to registry
./build-all-services.sh --push

# Build, push, and save tar files
./build-all-services.sh --push --save
```

### 2. Build for Specific Platform

```bash
# Build only for AMD64 (production servers)
./build-all-services.sh --platform linux/amd64 --push

# Build only for ARM64 (Apple Silicon)
./build-all-services.sh --platform linux/arm64 --push

# Build for multiple specific platforms
./build-all-services.sh --platform linux/amd64,linux/arm64,linux/arm/v7 --push
```

### 3. Traditional Single-Platform Build

```bash
# Disable buildx for traditional builds
./build-all-services.sh --no-buildx --push
```

## Manual Build Commands

### Individual Service Builds

```bash
# Navigate to backend directory
cd /path/to/backend

# Create and use buildx builder
docker buildx create --name multiplatform-builder --use

# Build chat service for multiple platforms
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker-build/dockerfiles/chat-service.Dockerfile \
  -t adebola/chat-service:latest \
  --push \
  .

# Build onboarding service
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker-build/dockerfiles/onboarding-service.Dockerfile \
  -t adebola/onboarding-service:latest \
  --push \
  .

# Build authorization server
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker-build/dockerfiles/authorization-service.Dockerfile \
  -t adebola/ai-authorization-server:latest \
  --push \
  .
```

### Load vs Push

```bash
# For local testing (loads to local Docker)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker-build/dockerfiles/chat-service.Dockerfile \
  -t adebola/chat-service:latest \
  --load \
  .

# For registry deployment (pushes to Docker Hub)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker-build/dockerfiles/chat-service.Dockerfile \
  -t adebola/chat-service:latest \
  --push \
  .
```

**Note**: You cannot use `--load` with multiple platforms. Use `--push` to registry instead.

## Build Script Options

The `build-all-services.sh` script supports these options:

| Option | Description | Example |
|--------|-------------|---------|
| `--push` | Push images to registry | `./build-all-services.sh --push` |
| `--platform` | Specify platforms | `./build-all-services.sh --platform linux/amd64` |
| `--no-buildx` | Use traditional docker build | `./build-all-services.sh --no-buildx` |
| `--save` | Save images to tar files | `./build-all-services.sh --save` |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_REGISTRY` | `adebola` | Docker registry/username |
| `VERSION` | `latest` | Image tag version |
| `PLATFORMS` | `linux/amd64,linux/arm64` | Target platforms |

```bash
# Custom registry and version
DOCKER_REGISTRY=myregistry VERSION=v1.0.0 ./build-all-services.sh --push

# Custom platforms
PLATFORMS=linux/amd64,linux/arm/v7 ./build-all-services.sh --push
```

## Deployment Scenarios

### Scenario 1: Development on Apple Silicon → Deploy to AMD64 Server

```bash
# Build on Mac (ARM64) for deployment to Linux server (AMD64)
./build-all-services.sh --platform linux/amd64 --push

# Or build for both platforms
./build-all-services.sh --push
```

### Scenario 2: CI/CD Pipeline

```bash
# In GitHub Actions or similar CI/CD
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v2

- name: Build and push
  run: |
    cd docker-build
    ./build-all-services.sh --push
```

### Scenario 3: Air-Gapped Deployment

```bash
# Build and save images locally
./build-all-services.sh --platform linux/amd64 --save

# Transfer tar files to target server
scp docker-images/*.tar user@server:/tmp/

# On target server, load images
docker load -i /tmp/chat-service.tar
docker load -i /tmp/onboarding-service.tar
docker load -i /tmp/authorization-server.tar
```

## Troubleshooting

### 1. Buildx Not Available

```bash
# Install buildx plugin
docker buildx install

# Or update Docker to latest version
```

### 2. QEMU Missing

```bash
# Install QEMU for cross-platform emulation
docker run --privileged --rm tonistiigi/binfmt --install all

# Verify emulation
docker buildx inspect --bootstrap
```

### 3. Registry Authentication

```bash
# Login to Docker Hub
docker login

# Login to private registry
docker login myregistry.com
```

### 4. Platform Validation

```bash
# Check image manifest
docker buildx imagetools inspect adebola/chat-service:latest

# Should show multiple platforms:
# - linux/amd64
# - linux/arm64
```

### 5. Clear Buildx Cache

```bash
# Clear build cache
docker buildx prune

# Remove and recreate builder
docker buildx rm multiplatform-builder
docker buildx create --name multiplatform-builder --use
```

## Best Practices

1. **Always specify platforms explicitly** for production builds
2. **Use --push for multi-platform builds** (--load doesn't work with multiple platforms)
3. **Test images on target architecture** before deployment
4. **Use specific version tags** instead of 'latest' for production
5. **Cache build layers** by ordering Dockerfile commands efficiently
6. **Use .dockerignore** to reduce build context size

## Verification

After building, verify your images support the correct platforms:

```bash
# Check image manifest
docker buildx imagetools inspect adebola/chat-service:latest

# Pull and run on target platform
docker pull adebola/chat-service:latest
docker run --rm adebola/chat-service:latest uname -m
```

## Performance Notes

- **Cross-platform builds are slower** due to emulation
- **Native platform builds are fastest** (ARM64 on Apple Silicon, AMD64 on Intel/AMD)
- **Use Docker layer caching** to speed up subsequent builds
- **Consider separate build pipelines** for different architectures if build time is critical

## Integration with Production

Update your production deployment to use the multi-platform images:

```yaml
# docker-compose-production-optimized.yml
services:
  chat-service:
    image: adebola/chat-service:latest  # Now supports both AMD64 and ARM64

  onboarding-service:
    image: adebola/onboarding-service:latest  # Multi-platform ready

  authorization-server:
    image: adebola/ai-authorization-server:latest  # Cross-platform compatible
```

The Docker runtime will automatically select the correct image variant for the host platform.