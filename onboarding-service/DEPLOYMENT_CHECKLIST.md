# Onboarding Service Deployment Checklist

## Pre-Deployment

### 1. Build Docker Image
```bash
# Navigate to backend directory
cd /path/to/backend

# Build for production (AMD64 platform)
docker build \
  --platform linux/amd64 \
  -f onboarding-service/Dockerfile \
  -t factorialbot/onboarding-service:v1.0.0 \
  -t factorialbot/onboarding-service:latest \
  .

# Verify image was built
docker images | grep onboarding-service
```

**Expected output**:
```
factorialbot/onboarding-service   latest    abc123def456   2 minutes ago   ~600MB
factorialbot/onboarding-service   v1.0.0    abc123def456   2 minutes ago   ~600MB
```

### 2. Test Image Locally
```bash
# Run test container
docker run -d \
  --name test-onboarding \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e OPENAI_API_KEY=sk-... \
  -e INSTALL_PLAYWRIGHT=true \
  factorialbot/onboarding-service:latest

# Wait for service to start (check logs)
docker logs -f test-onboarding

# Expected output:
# ========================================
# Onboarding Service Starting...
# ========================================
# Playwright cache directory: /app/.cache/ms-playwright
# Installing Playwright Chromium browser...
# Playwright installation running in background (PID: XX)
# ========================================
# Starting Onboarding Service Application
# ========================================
```

### 3. Verify Playwright Installation
```bash
# Wait 60 seconds for background installation
sleep 60

# Check installation
docker exec test-onboarding ls -la /app/.cache/ms-playwright/

# Expected output:
# drwxr-xr-x  appuser appuser chromium-1187
# drwxr-xr-x  appuser appuser chromium_headless_shell-1187
# drwxr-xr-x  appuser appuser ffmpeg-1011

# Verify permissions
docker exec test-onboarding ls -ld /app/.cache/ms-playwright

# Expected output:
# drwxr-xr-x  appuser appuser /app/.cache/ms-playwright
```

### 4. Test Scraping Functionality
```bash
# Get auth token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"test"}' | jq -r .access_token)

# Test React SPA scraping (requires Playwright)
curl -X POST http://localhost:8000/api/v1/websites/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "website_url=https://www.brookehowseestate.com/"

# Check logs for Playwright fallback
docker logs test-onboarding | grep "Playwright"

# Expected output:
# [timestamp] Trying requests first (AUTO strategy)
# [timestamp] Requests returned insufficient content, trying Playwright
# [timestamp] Playwright succeeded, caching preference
```

### 5. Cleanup Test Container
```bash
docker stop test-onboarding
docker rm test-onboarding
```

## Push to Registry

### Docker Hub
```bash
# Login to Docker Hub
docker login

# Push versioned tag
docker push factorialbot/onboarding-service:v1.0.0

# Push latest tag
docker push factorialbot/onboarding-service:latest
```

### AWS ECR (if using)
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Tag for ECR
docker tag factorialbot/onboarding-service:latest \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/onboarding-service:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/onboarding-service:latest
```

## AWS Lightsail Deployment

### Update Container Service

**Option 1: Using AWS Console**
1. Navigate to Lightsail Console
2. Select your container service
3. Click "Modify your deployment"
4. Update image tag: `factorialbot/onboarding-service:v1.0.0`
5. Verify environment variables (especially `INSTALL_PLAYWRIGHT=true`)
6. Save and deploy

**Option 2: Using AWS CLI**
```bash
# Create deployment JSON
cat > deployment.json << 'EOF'
{
  "containers": {
    "onboarding-service": {
      "image": "factorialbot/onboarding-service:v1.0.0",
      "environment": {
        "DATABASE_URL": "postgresql://...",
        "OPENAI_API_KEY": "sk-...",
        "INSTALL_PLAYWRIGHT": "true",
        "PLAYWRIGHT_BROWSERS_PATH": "/app/.cache/ms-playwright"
      },
      "ports": {
        "8000": "HTTP"
      }
    }
  },
  "publicEndpoint": {
    "containerName": "onboarding-service",
    "containerPort": 8000,
    "healthCheck": {
      "path": "/health",
      "intervalSeconds": 30
    }
  }
}
EOF

# Deploy to Lightsail
aws lightsail create-container-service-deployment \
  --service-name factorialbot-onboarding \
  --cli-input-json file://deployment.json
```

### Monitor Deployment
```bash
# Watch deployment status
aws lightsail get-container-service-deployments \
  --service-name factorialbot-onboarding

# Check container logs
aws lightsail get-container-log \
  --service-name factorialbot-onboarding \
  --container-name onboarding-service

# Expected in logs:
# [Playwright Installer] Starting installation at ...
# [Playwright Installer] ✓ Installation complete at ...
```

## Post-Deployment Verification

### 1. Check Service Health
```bash
# Health check endpoint
curl https://your-service-url.aws.lightsail.com/health

# Expected response:
# {"status": "healthy"}
```

### 2. Verify Playwright Installation
Look for these log entries:
```
✅ SUCCESS:
[Playwright Installer] Starting installation at Mon Nov  3 16:13:39 UTC 2025
[Playwright Installer] ✓ Installation complete at Mon Nov  3 16:14:20 UTC 2025

❌ FAILURE (previous issue - should not occur now):
Failed to install browsers
Error: EACCES: permission denied, mkdir '/home/appuser/.cache/ms-playwright/__dirlock'
```

### 3. Test JavaScript Scraping
```bash
# Get production auth token
TOKEN=$(curl -s -X POST https://your-service-url/api/v1/auth/login ...)

# Test React SPA scraping
curl -X POST https://your-service-url/api/v1/websites/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "website_url=https://www.brookehowseestate.com/"

# Check scraping status
curl https://your-service-url/api/v1/websites/ingestions/{ingestion_id}/status \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Monitor Resource Usage
```bash
# CPU and Memory usage
aws lightsail get-container-service-metric-data \
  --service-name factorialbot-onboarding \
  --metric-name CPUUtilization \
  --start-time 2025-11-03T00:00:00Z \
  --end-time 2025-11-03T23:59:59Z \
  --period 300 \
  --statistics Average
```

## Rollback Plan

### If Deployment Fails

**Quick Rollback**:
```bash
# Deploy previous version
aws lightsail create-container-service-deployment \
  --service-name factorialbot-onboarding \
  --containers '{"onboarding-service":{"image":"factorialbot/onboarding-service:v0.9.0"}}'
```

**Disable Playwright** (if issues persist):
```bash
# Update environment variable
aws lightsail create-container-service-deployment \
  --service-name factorialbot-onboarding \
  --containers '{"onboarding-service":{"environment":{"INSTALL_PLAYWRIGHT":"false"}}}'
```

## Troubleshooting Guide

### Issue: Permission Denied Errors

**Check**:
```bash
# View container logs
aws lightsail get-container-log \
  --service-name factorialbot-onboarding \
  --container-name onboarding-service \
  | grep -i "permission denied"
```

**Solution**: Already fixed in new Dockerfile. If still occurring:
1. Verify you're using the latest image
2. Check that `PLAYWRIGHT_BROWSERS_PATH=/app/.cache/ms-playwright` is set
3. Ensure no volume mounts override the cache directory

### Issue: Playwright Installation Times Out

**Check**:
```bash
# Check installation logs
aws lightsail get-container-log ... | grep "Playwright Installer"
```

**Possible causes**:
1. Network issues (CDN unreachable)
2. Insufficient memory (need 512MB+ free)
3. Slow disk I/O

**Solutions**:
1. Increase container memory allocation
2. Check Lightsail network connectivity
3. Consider pre-installing browsers in image (larger image size)

### Issue: Scraping Fails for React SPAs

**Check**:
```bash
# Look for AUTO strategy logs
aws lightsail get-container-log ... | grep "AUTO strategy"

# Should see:
# "Trying requests first (AUTO strategy)"
# "Requests returned insufficient content, trying Playwright"
# "Playwright succeeded, caching preference"
```

**If not seeing Playwright fallback**:
1. Verify `use_javascript` parameter was removed from code (should be)
2. Check that scraper is using AUTO strategy
3. Confirm Playwright installation completed successfully

## Environment Variables Checklist

Required for production:
- [ ] `DATABASE_URL` - PostgreSQL connection string
- [ ] `VECTOR_DATABASE_URL` - Vector database connection
- [ ] `OPENAI_API_KEY` - OpenAI API key for embeddings
- [ ] `REDIS_URL` - Redis connection for caching
- [ ] `MINIO_ENDPOINT` - Object storage endpoint
- [ ] `MINIO_ACCESS_KEY` - Object storage access key
- [ ] `MINIO_SECRET_KEY` - Object storage secret key
- [ ] `JWT_SECRET_KEY` - JWT signing secret
- [ ] `INSTALL_PLAYWRIGHT` - Set to `true` for JavaScript scraping

Optional:
- [ ] `PLAYWRIGHT_BROWSERS_PATH` - Browser cache location (default: `/app/.cache/ms-playwright`)
- [ ] `MAX_PAGES_PER_SITE` - Scraping limit (default: 100)
- [ ] `SCRAPING_DELAY` - Delay between requests (default: 1.0)

## Success Criteria

Deployment is successful when:
- ✅ Service health check returns 200 OK
- ✅ Playwright installation completes without errors
- ✅ React SPA scraping works (Playwright fallback triggers)
- ✅ No permission denied errors in logs
- ✅ Memory usage < 1GB under normal load
- ✅ CPU usage < 50% when idle

## Performance Baselines

**Startup Time**:
- Service available: < 5 seconds
- Playwright ready: 30-60 seconds (first start)
- Playwright ready: < 5 seconds (with cached browsers)

**Scraping Performance**:
- Static sites (requests): 0.5-2 seconds per page
- JavaScript sites (Playwright): 8-15 seconds per page
- Concurrent limit: 2-3 Playwright sessions per 1GB RAM

**Resource Usage**:
- Base: ~200MB RAM, 5-10% CPU
- Active scraping: ~400-600MB RAM per session
- Recommended minimum: 512MB RAM, 0.5 vCPU

## Next Steps After Deployment

1. **Monitor for 24 hours**
   - Check error rates
   - Monitor memory/CPU usage
   - Verify scraping success rates

2. **Setup Alerts**
   - High error rate (> 5%)
   - High memory usage (> 80%)
   - Playwright failures (> 10%)

3. **Performance Tuning**
   - Adjust concurrent scraping limits
   - Configure caching strategies
   - Scale horizontally if needed

4. **Documentation**
   - Update API docs with JavaScript scraping capabilities
   - Document supported website types
   - Add troubleshooting guide for users
