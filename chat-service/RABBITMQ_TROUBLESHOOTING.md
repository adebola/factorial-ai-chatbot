# RabbitMQ Connection Troubleshooting Guide

## Overview

The chat-service connects to RabbitMQ for two purposes:
1. **Event Publisher** - Publishes chat events to `chat.events` and `usage.events` exchanges
2. **Limit Warning Consumer** - Consumes limit warnings from `usage.events` exchange

## Recent Fixes Applied

### 1. Enhanced Error Logging
**Problem:** Error messages were empty in logs (e.g., "Failed to connect: . Retrying...")

**Fix:** Both `event_publisher.py` and `limit_warning_consumer.py` now include:
- Full error messages with `str(e) if str(e) else repr(e)`
- Connection details in structured logs (host, port, user, vhost, exchange, queue)
- Error type information for better debugging

**New log format:**
```json
{
  "event": "Failed to connect to RabbitMQ (attempt 1/3): Connection refused",
  "host": "rabbitmq",
  "port": 5672,
  "vhost": "/",
  "user": "rabbit_user",
  "error": "Connection refused",
  "error_type": "AMQPConnectionError"
}
```

### 2. Connection Diagnostics
**Added:** `rabbitmq_diagnostics.py` - Automatic diagnostics on connection failure

**What it checks:**
- DNS resolution (can the hostname be resolved?)
- TCP connectivity (is the port reachable?)
- Environment variables (are all required vars set?)

**When it runs:**
- Automatically when connection fails during startup
- Provides detailed information to help identify the root cause

### 3. Improved Docker Healthcheck
**Changed:** RabbitMQ healthcheck from `ping` to `check_port_connectivity`

**Before:**
```yaml
healthcheck:
  test: ["CMD", "rabbitmq-diagnostics", "ping", "-q"]
  interval: 60s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**After:**
```yaml
healthcheck:
  test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
  interval: 10s      # Check more frequently
  timeout: 5s
  retries: 5         # More retries
  start_period: 60s  # Longer startup period
```

**Why:** `check_port_connectivity` verifies that RabbitMQ can actually accept connections, not just that the process is running.

## Common Issues and Solutions

### Issue 1: "Connection refused" or "No route to host"

**Symptoms:**
```
Failed to connect to RabbitMQ (attempt 1/3): Connection refused
tcp_connection: {"success": false, "error": "Port 5672 is closed"}
```

**Possible Causes:**
1. RabbitMQ container not started
2. RabbitMQ still initializing
3. Network issues

**Solutions:**
```bash
# Check if RabbitMQ container is running
docker ps | grep rabbitmq

# Check RabbitMQ logs
docker logs rabbitmq

# Verify RabbitMQ health
docker exec rabbitmq rabbitmq-diagnostics ping

# Check if port is accessible from chat-service
docker exec chat-service nc -zv rabbitmq 5672
```

### Issue 2: DNS Resolution Failed

**Symptoms:**
```
dns_resolution: {"success": false, "error": "Name or service not known"}
```

**Possible Causes:**
1. Wrong hostname in RABBITMQ_HOST
2. Docker network issues
3. Services not on same network

**Solutions:**
```bash
# Check network configuration
docker network inspect chatcraft-network

# Verify both services are on the same network
docker inspect chat-service | grep NetworkMode
docker inspect rabbitmq | grep NetworkMode

# Test DNS resolution from chat-service
docker exec chat-service ping -c 2 rabbitmq
docker exec chat-service nslookup rabbitmq
```

### Issue 3: Authentication Failed

**Symptoms:**
```
Failed to connect: ACCESS_REFUSED - Login was refused using authentication mechanism PLAIN
```

**Possible Causes:**
1. Wrong username/password
2. Credentials not set in environment
3. Mismatch between RABBITMQ_USER and RABBITMQ_USERNAME

**Solutions:**
```bash
# Check environment variables in docker-compose
grep RABBITMQ docker-build/docker-compose-production-optimized.yml

# Verify credentials in RabbitMQ
docker exec rabbitmq rabbitmqctl list_users

# Check what the service is using
docker exec chat-service env | grep RABBITMQ
```

### Issue 4: Service Starts But No Retry Logs

**Symptoms:**
- See "Failed to connect (attempt 1/3)" but no subsequent attempts logged
- Service continues without RabbitMQ

**Explanation:**
This is **expected behavior**:
1. Both components retry 3 times (with 5-second delays)
2. After 3 failures, they give up and let the service continue
3. The service remains functional but RabbitMQ features are disabled

**The retries ARE happening**, but:
- Event publisher retries happen synchronously during startup
- Limit warning consumer retries happen in a background daemon thread
- After 3 failures, exceptions are caught and service continues

**To see all retry attempts:**
```bash
# Watch logs in real-time
docker logs -f chat-service

# Check for all retry attempts
docker logs chat-service 2>&1 | grep -i "retry"
```

## Environment Variable Checklist

Required environment variables for RabbitMQ connection:

```bash
# Connection details
RABBITMQ_HOST=rabbitmq              # Hostname (use 'rabbitmq' in Docker)
RABBITMQ_PORT=5672                  # Port (default: 5672)
RABBITMQ_USER=rabbit_user           # Username
RABBITMQ_PASSWORD=rabbit_password   # Password
RABBITMQ_VHOST=/                    # Virtual host (default: /)

# Optional - Alternative URL format
RABBITMQ_URL=amqp://rabbit_user:rabbit_password@rabbitmq:5672/

# Exchange names (optional - have defaults)
RABBITMQ_CHAT_EXCHANGE=chat.events
RABBITMQ_USAGE_EXCHANGE=usage.events
```

**Check all variables:**
```bash
docker exec chat-service env | grep RABBITMQ
```

## Manual Connection Testing

### Test from Chat Service Container

```bash
# Enter the container
docker exec -it chat-service sh

# Test DNS resolution
ping -c 2 rabbitmq
nslookup rabbitmq

# Test TCP connection
nc -zv rabbitmq 5672

# Test with Python (if pika is installed)
python3 -c "
import pika
credentials = pika.PlainCredentials('rabbit_user', 'rabbit_password')
parameters = pika.ConnectionParameters('rabbitmq', 5672, '/', credentials)
connection = pika.BlockingConnection(parameters)
print('✓ Connection successful!')
connection.close()
"
```

### Test RabbitMQ Directly

```bash
# Check RabbitMQ status
docker exec rabbitmq rabbitmqctl status

# Check if TCP port is listening
docker exec rabbitmq netstat -tuln | grep 5672

# List users
docker exec rabbitmq rabbitmqctl list_users

# List exchanges
docker exec rabbitmq rabbitmqctl list_exchanges

# Check connections
docker exec rabbitmq rabbitmqctl list_connections
```

## Deployment Checklist

Before deploying to production:

- [ ] Verify RabbitMQ container starts successfully
- [ ] Check RabbitMQ healthcheck passes: `docker ps` (should show "healthy")
- [ ] Confirm environment variables are set correctly
- [ ] Test DNS resolution from chat-service to rabbitmq
- [ ] Verify TCP connectivity on port 5672
- [ ] Check that credentials match between services
- [ ] Review logs for detailed error messages (no more empty errors!)
- [ ] Confirm diagnostic logs appear if connection fails

## Interpreting New Diagnostic Logs

With the enhanced logging, you'll now see detailed diagnostics on failure:

```json
{
  "event": "RabbitMQ Connection Diagnostics",
  "host": "rabbitmq",
  "port": 5672,
  "user": "rabbit_user",
  "vhost": "/",
  "dns_resolution": {
    "success": true,
    "ip_address": "172.28.0.5"
  },
  "tcp_connection": {
    "success": false,
    "error": "Port 5672 is closed or unreachable"
  },
  "environment_vars": {
    "RABBITMQ_HOST": "rabbitmq",
    "RABBITMQ_PORT": "5672",
    "RABBITMQ_USER": "rabbit_user",
    "RABBITMQ_PASSWORD": "***REDACTED***",
    "RABBITMQ_VHOST": "/"
  }
}
```

**How to interpret:**
- ✓ **DNS success + TCP success** = RabbitMQ is reachable, check credentials
- ✓ **DNS success + TCP fail** = RabbitMQ container down or port not exposed
- ✗ **DNS fail** = Hostname wrong or network configuration issue

## Getting Help

If issues persist after checking the above:

1. **Collect full logs:**
   ```bash
   docker logs rabbitmq > rabbitmq.log
   docker logs chat-service > chat-service.log
   ```

2. **Run diagnostics:**
   ```bash
   docker exec chat-service python3 -c "
   from app.services.rabbitmq_diagnostics import log_diagnostics
   log_diagnostics()
   "
   ```

3. **Check system resources:**
   ```bash
   docker stats rabbitmq
   docker stats chat-service
   ```

4. **Review connection timeline:**
   - When did RabbitMQ start?
   - When did chat-service start?
   - How long between them?
   - Did healthcheck pass before chat-service connected?

## Related Files

- `/app/services/event_publisher.py` - RabbitMQ event publisher with retry logic
- `/app/services/limit_warning_consumer.py` - RabbitMQ consumer with retry logic
- `/app/services/rabbitmq_diagnostics.py` - Connection diagnostics helper
- `/app/main.py` - Startup sequence and error handling
- `docker-compose-production-optimized.yml` - RabbitMQ and service configuration
