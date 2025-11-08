# Docker Playwright Setup Guide

## Overview

The onboarding service Docker image includes support for JavaScript-based website scraping using Playwright. This guide explains the setup, how it works, and troubleshooting steps.

## Architecture

### Two-Stage Approach

**Build Time (Dockerfile)**:
- Install Playwright Python package
- Install system dependencies (Chromium dependencies)
- Create cache directory with proper permissions
- Keep image size ~600MB (vs 2GB if browsers included)

**Runtime (Entrypoint Script)**:
- Install Chromium browser binaries on first container start
- Installation runs in background (30-60 seconds)
- Service starts immediately, scraping waits if needed
- Browsers persist if volume is mounted

## Key Changes Made

### 1. Dockerfile Improvements

#### Added System Dependencies
Playwright Chromium requires several system libraries that must be installed at build time:

```dockerfile
RUN apt-get update && apt-get install -y \
    curl \
    postgresql-client \
    # Playwright Chromium dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    && rm -rf /var/lib/apt/lists/*
```

**Why these are needed**: These libraries provide the graphics, audio, and system integration capabilities that Chromium browser needs to run in headless mode.

#### Set Playwright Cache Location
```dockerfile
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright
```

**Why this matters**:
- Default location is `~/.cache/ms-playwright` (in user's home directory)
- Container's appuser may not have permissions to default location
- Setting explicit path allows us to control permissions
- Makes it easy to mount a volume for persistence

#### Create Cache Directory with Proper Permissions
```dockerfile
RUN adduser --disabled-password --gecos '' appuser && \
    mkdir -p /app/.cache/ms-playwright && \
    chown -R appuser:appuser /app
```

**Fixed the permission error**: `EACCES: permission denied, mkdir '/home/appuser/.cache/ms-playwright/__dirlock'`

This was failing because:
- Directory didn't exist
- appuser didn't have write permissions
- Playwright couldn't create lock files for concurrent installations

### 2. Entrypoint Script Enhancements

#### Permission Checks
```bash
# Ensure the cache directory exists and has proper permissions
if [ ! -d "$PLAYWRIGHT_BROWSERS_PATH" ]; then
    echo "Creating Playwright cache directory: $PLAYWRIGHT_BROWSERS_PATH"
    mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
fi

# Check if we have write permissions
if [ ! -w "$PLAYWRIGHT_BROWSERS_PATH" ]; then
    echo "ERROR: No write permission for $PLAYWRIGHT_BROWSERS_PATH"
    echo "This will prevent Playwright browser installation"
    echo "Continuing anyway - Playwright installation may fail"
fi
```

#### Better Detection of Installed Browsers
```bash
# Check if Chromium browser is already installed
# Look for the chromium directory in the cache path
if [ -d "$PLAYWRIGHT_BROWSERS_PATH/chromium-"* ] 2>/dev/null; then
    echo "✓ Playwright Chromium already installed"
fi
```

**Why this works**: Playwright installs browsers in directories like `chromium-1187/`, so we check for any matching directory.

#### Enhanced Logging
```bash
echo "[Playwright Installer] Starting installation at $(date)"
echo "[Playwright Installer] Cache directory: $PLAYWRIGHT_BROWSERS_PATH"
echo "[Playwright Installer] User: $(whoami)"
echo "[Playwright Installer] Permissions: $(ls -ld $PLAYWRIGHT_BROWSERS_PATH)"
```

This helps debug permission issues in production environments.

## Building the Docker Image

### From Project Root
```bash
# Build the image
docker build \
  --platform linux/amd64 \
  -f onboarding-service/Dockerfile \
  -t factorialbot/onboarding-service:latest \
  .

# Note: Build from project root, not onboarding-service directory
# This is because Dockerfile copies from ../docker-build/entrypoints/
```

### Build Context Requirements
The build expects the following structure:
```
backend/
├── onboarding-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   ├── alembic.ini
│   └── ...
└── docker-build/
    └── entrypoints/
        └── onboarding-entrypoint.sh
```

## Running the Container

### Basic Run
```bash
docker run -d \
  --name onboarding-service \
  -p 8000:8000 \
  -e INSTALL_PLAYWRIGHT=true \
  factorialbot/onboarding-service:latest
```

### With Persistent Browser Cache (Recommended for Production)
```bash
docker run -d \
  --name onboarding-service \
  -p 8000:8000 \
  -e INSTALL_PLAYWRIGHT=true \
  -v playwright-cache:/app/.cache/ms-playwright \
  factorialbot/onboarding-service:latest
```

**Benefits of volume mount**:
- Browser installation only happens once
- Faster container restarts (no re-download)
- Survives container recreation
- Reduces bandwidth usage

### Without Playwright (Faster Startup)
```bash
docker run -d \
  --name onboarding-service \
  -p 8000:8000 \
  -e INSTALL_PLAYWRIGHT=false \
  factorialbot/onboarding-service:latest
```

**Use case**: Development environments where you don't need JavaScript scraping.

## Environment Variables

### INSTALL_PLAYWRIGHT
- **Values**: `true` | `false`
- **Default**: `true`
- **Description**: Whether to install Playwright browsers on container start

### PLAYWRIGHT_BROWSERS_PATH
- **Default**: `/app/.cache/ms-playwright`
- **Description**: Directory where Playwright browsers are stored
- **Note**: Should match Dockerfile ENV setting

## Troubleshooting

### Issue 1: Permission Denied Errors

**Symptom**:
```
Error: EACCES: permission denied, mkdir '/home/appuser/.cache/ms-playwright/__dirlock'
```

**Cause**: Cache directory doesn't exist or appuser lacks permissions

**Solution**: Already fixed in updated Dockerfile
- Cache directory created at build time
- Proper ownership set to appuser
- Path set to `/app/.cache/ms-playwright` (not home directory)

**Verify Fix**:
```bash
# Check permissions inside container
docker exec onboarding-service ls -la /app/.cache/
# Should show: drwxr-xr-x appuser appuser ms-playwright
```

### Issue 2: Playwright Installation Fails

**Symptom**:
```
Failed to install browsers
Error downloading browsers
```

**Possible Causes**:
1. Network issues (CDN unreachable)
2. Insufficient disk space
3. Missing system dependencies

**Debug Steps**:
```bash
# Check installation log
docker exec onboarding-service cat /tmp/playwright-install.log

# Check disk space
docker exec onboarding-service df -h /app/.cache

# Manually trigger installation
docker exec onboarding-service playwright install chromium

# Check system dependencies
docker exec onboarding-service playwright install-deps --dry-run chromium
```

### Issue 3: Browsers Not Persisting

**Symptom**: Browsers download on every container restart

**Cause**: No volume mounted for cache directory

**Solution**:
```bash
# Create named volume
docker volume create playwright-cache

# Run with volume mount
docker run -d \
  -v playwright-cache:/app/.cache/ms-playwright \
  factorialbot/onboarding-service:latest

# Verify persistence
docker exec onboarding-service ls -lh /app/.cache/ms-playwright/
```

### Issue 4: Chromium Fails to Launch

**Symptom**:
```
BrowserType.launch: Executable doesn't exist
```

**Causes**:
1. Installation still in progress (background job)
2. Installation failed silently
3. Wrong architecture (ARM vs AMD64)

**Debug Steps**:
```bash
# Check if chromium directory exists
docker exec onboarding-service ls -la /app/.cache/ms-playwright/

# Check installation process
docker exec onboarding-service ps aux | grep playwright

# Check entrypoint logs
docker logs onboarding-service | grep Playwright

# Manually verify browser
docker exec onboarding-service playwright --version
```

## Monitoring and Health Checks

### Check Playwright Status
```bash
# From inside container
playwright show-browsers

# From outside container
docker exec onboarding-service playwright show-browsers
```

### Check Service Health
```bash
# Health check endpoint
curl http://localhost:8000/health

# Check if Playwright is functional (will fail if not installed)
curl -X POST http://localhost:8000/api/v1/websites/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "website_url=https://www.brookehowseestate.com/"
```

### Monitor Installation Progress
```bash
# Watch installation in real-time
docker logs -f onboarding-service | grep "Playwright Installer"

# Check background process
docker exec onboarding-service ps aux | grep "playwright install"
```

## Performance Considerations

### Image Size
- **With system deps only**: ~600MB
- **With browsers pre-installed**: ~2GB
- **Savings**: 70% smaller image

### Startup Time
- **Service availability**: Immediate (<5 seconds)
- **Full Playwright ready**: 30-60 seconds (background)
- **With cached browsers**: Immediate (<5 seconds)

### Runtime Resources
- **Base service**: ~200MB RAM
- **With Playwright active**: ~400-600MB RAM per scraping session
- **Chromium process**: ~150-300MB RAM each

### Optimization Tips
1. **Use volume mounts** for browser cache (one-time download)
2. **Limit concurrent scrapes** to control memory usage
3. **Consider pre-warming** browsers on container start
4. **Monitor and scale** based on scraping load

## Production Deployment

### Kubernetes Example
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: onboarding-service
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: onboarding
        image: factorialbot/onboarding-service:latest
        env:
        - name: INSTALL_PLAYWRIGHT
          value: "true"
        - name: PLAYWRIGHT_BROWSERS_PATH
          value: "/app/.cache/ms-playwright"
        volumeMounts:
        - name: playwright-cache
          mountPath: /app/.cache/ms-playwright
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
      volumes:
      - name: playwright-cache
        persistentVolumeClaim:
          claimName: playwright-cache-pvc
```

### AWS Lightsail Considerations
Based on your production logs, ensure:
1. ✅ Sufficient disk space for browser download (~130MB)
2. ✅ Network access to playwright CDN (cdn.playwright.dev)
3. ✅ Memory limits accommodate Chromium (suggest 1GB minimum)
4. ✅ Volume persistence for browser cache

## Testing the Fix

### Verify Permissions
```bash
# Build and run
docker build -t test-onboarding -f onboarding-service/Dockerfile .
docker run --rm test-onboarding ls -la /app/.cache/

# Should show:
# drwxr-xr-x appuser appuser ms-playwright
```

### Test Playwright Installation
```bash
# Run container
docker run -d --name test-onboarding -e INSTALL_PLAYWRIGHT=true test-onboarding

# Wait 60 seconds for installation
sleep 60

# Check installation
docker exec test-onboarding ls -la /app/.cache/ms-playwright/
# Should show: chromium-1187/ (or similar version)

# Test browser launch
docker exec test-onboarding playwright show-browsers
```

### Test React SPA Scraping
```bash
# Get auth token
TOKEN=$(curl -X POST http://localhost:8000/auth/token ...)

# Scrape React SPA
curl -X POST http://localhost:8000/api/v1/websites/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "website_url=https://www.brookehowseestate.com/"

# Check logs - should see Playwright fallback
docker logs test-onboarding | grep "Playwright"
```

## Rollback Plan

If issues occur in production:

### Quick Disable
```bash
# Set INSTALL_PLAYWRIGHT=false in environment
# Redeploy - service works with requests-only scraping
```

### Previous Behavior
The old Dockerfile worked but had permission issues. If needed:
```dockerfile
# Revert to pre-change Dockerfile
# But note: You'll still get permission errors
```

## Summary of Fixes

| Issue | Previous State | Fixed State |
|-------|---------------|-------------|
| **Permission Errors** | Home directory with wrong permissions | Dedicated cache dir with appuser ownership |
| **System Dependencies** | Missing Chromium libs | All required libs installed at build time |
| **Cache Location** | Default `~/.cache` (inaccessible) | Custom `/app/.cache/ms-playwright` |
| **Detection Logic** | Used `playwright show-browsers` (unreliable) | Check for `chromium-*` directory |
| **Error Visibility** | Silent failures | Enhanced logging with diagnostics |
| **Container Startup** | Would fail if Playwright issues | Gracefully degrades to requests-only |

## References

- [Playwright Docker Documentation](https://playwright.dev/docs/docker)
- [Playwright System Requirements](https://playwright.dev/docs/browsers#system-requirements)
- [Docker Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
