# RabbitMQ Connection - Quick Fix Guide

## 🔥 Most Common Issues

### Issue: "Connection refused"
```bash
# Check if RabbitMQ is running
docker ps | grep rabbitmq

# If not running, start it
docker-compose up -d rabbitmq

# Check logs
docker logs rabbitmq
```

### Issue: "Name or service not known" (DNS)
```bash
# Check if both on same network
docker network inspect chatcraft-network

# Test DNS from chat-service
docker exec chat-service ping -c 2 rabbitmq
```

### Issue: "ACCESS_REFUSED" (Auth)
```bash
# Check credentials match
docker exec rabbitmq rabbitmqctl list_users

# Verify environment variables
docker exec chat-service env | grep RABBITMQ
```

## 🚀 Quick Health Check

```bash
# One-liner to check everything
docker exec rabbitmq rabbitmq-diagnostics check_port_connectivity && \
docker exec chat-service nc -zv rabbitmq 5672 && \
echo "✅ RabbitMQ is healthy and reachable!"
```

## 📋 Required Environment Variables

```bash
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=rabbit_user
RABBITMQ_PASSWORD=rabbit_password
RABBITMQ_VHOST=/
```

## 🔍 What the New Logs Tell You

### Before Fix (Useless)
```
Failed to connect: . Retrying...
```

### After Fix (Helpful!)
```json
{
  "error": "Connection refused",
  "error_type": "AMQPConnectionError",
  "host": "rabbitmq",
  "port": 5672,
  "dns_resolution": {"success": true, "ip_address": "172.28.0.5"},
  "tcp_connection": {"success": false, "error": "Port closed"}
}
```

**Tells you exactly:**
- ✓ DNS works (can resolve hostname)
- ✗ TCP fails (port not reachable)
- → **Fix:** Start RabbitMQ container

## 🎯 Quick Deployment

```bash
# 1. Build new image
cd docker-build && ./build-single-service.sh chat-service

# 2. Push to registry
docker push adebola/chat-service:latest

# 3. Deploy
docker-compose -f docker-compose-production-optimized.yml pull chat-service
docker-compose -f docker-compose-production-optimized.yml up -d chat-service

# 4. Watch logs for detailed errors
docker logs -f chat-service | grep -i rabbitmq
```

## ✅ Verify Fix Worked

You should now see:
- ✅ Full error messages (not empty)
- ✅ All 3 retry attempts logged
- ✅ Automatic diagnostics run
- ✅ Connection details in every error

## 📚 Full Documentation

- Detailed guide: `RABBITMQ_TROUBLESHOOTING.md`
- Complete summary: `../RABBITMQ_CONNECTION_FIX_SUMMARY.md`
