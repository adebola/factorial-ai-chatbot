# PostgreSQL Production Configuration Guide

**Date Created:** November 24, 2025
**Purpose:** Fix SSL connection pool errors in production RDS environment
**Affected Services:** onboarding-service, billing-service, chat-service, communications-service

---

## Problem Summary

Production services were experiencing `psycopg2.OperationalError: SSL connection has been closed unexpectedly` errors due to:

1. ❌ RDS requires SSL (`force_ssl=1`) but connection strings didn't specify SSL mode
2. ❌ Connection pool recycle period (1 hour) exceeded RDS idle connection timeout
3. ❌ No connection timeouts caused hanging instead of fast failures

---

## Solutions Implemented

### Code Changes (All Services - Completed ✅)

**Connection Pool Settings Updated:**
- `POOL_RECYCLE_SECONDS`: 3600 → **300** (recycle every 5 minutes instead of 1 hour)
- `POOL_TIMEOUT`: **30 seconds** (new - wait max 30s for connection from pool)
- `CONNECT_TIMEOUT`: **10 seconds** (new - connection establishment timeout)
- `STATEMENT_TIMEOUT`: **30 seconds** (new - maximum query execution time)

**These changes are:**
- ✅ Safe for development (localhost PostgreSQL)
- ✅ Safe for production (RDS)
- ✅ Already applied to all services
- ✅ No .env changes needed in development

### Production .env Changes (REQUIRED ⚠️)

**All production .env files must add `?sslmode=require` to DATABASE_URL:**

---

## Production Environment Variables

### onboarding-service

**Production .env location:** `/path/to/production/onboarding-service/.env`

```bash
# REQUIRED: Add ?sslmode=require to both URLs
DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/onboard_db?sslmode=require
VECTOR_DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/vector_db?sslmode=require

# Optional: Override defaults if needed
POOL_SIZE=10
POOL_MAX_OVERFLOW=20
POOL_RECYCLE_SECONDS=300
POOL_TIMEOUT=30
CONNECT_TIMEOUT=10
```

### billing-service

**Production .env location:** `/path/to/production/billing-service/.env`

```bash
# REQUIRED: Add ?sslmode=require
DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/billing_db?sslmode=require

# Optional: Override defaults if needed
POOL_SIZE=10
POOL_MAX_OVERFLOW=20
POOL_RECYCLE_SECONDS=300
POOL_TIMEOUT=30
CONNECT_TIMEOUT=10
```

### chat-service

**Production .env location:** `/path/to/production/chat-service/.env`

```bash
# REQUIRED: Add ?sslmode=require to both URLs
DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/chatbot_db?sslmode=require
VECTOR_DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/vector_db?sslmode=require

# Note: chat-service doesn't use config.py, so pool settings are hardcoded
# If needed, values can be overridden via environment (not currently supported)
```

### communications-service

**Production .env location:** `/path/to/production/communications-service/.env`

```bash
# REQUIRED: Add ?sslmode=require
DATABASE_URL=postgresql://USER:PASSWORD@RDS_ENDPOINT:5432/communications_db?sslmode=require

# Optional: Override defaults (communications service supports env vars)
POOL_SIZE=10
POOL_MAX_OVERFLOW=20
POOL_RECYCLE_SECONDS=300  # Now defaults to 300
POOL_TIMEOUT=30           # New setting
CONNECT_TIMEOUT=10        # New setting
```

---

## Development Environment (NO CHANGES REQUIRED ✅)

**Development .env files remain unchanged:**

```bash
# Development - NO SSL mode (localhost PostgreSQL doesn't have SSL)
DATABASE_URL=postgresql://postgres:password@localhost:5432/database_name

# The code changes are safe for development:
# - pool_recycle=300 works fine with localhost
# - Timeout parameters work fine with localhost
# - SSL is not required for localhost
```

---

## SSL Mode Options

When updating production .env files, you can choose:

| SSL Mode | Description | Recommended For |
|----------|-------------|-----------------|
| `sslmode=disable` | No SSL encryption | **Never use in production!** |
| `sslmode=allow` | Try non-SSL first, fallback to SSL | Not recommended |
| `sslmode=prefer` | Try SSL first, fallback to non-SSL | Development/staging with mixed environments |
| **`sslmode=require`** | **Require SSL, validate server** | **✅ Production (RECOMMENDED)** |
| `sslmode=verify-ca` | Require SSL + verify CA certificate | High-security production |
| `sslmode=verify-full` | Require SSL + verify CA + hostname | Maximum security |

**For ChatCraft Production: Use `sslmode=require`**

---

## RDS-Specific Configuration

### AWS RDS PostgreSQL Settings

**Current RDS Configuration (from migration docs):**
```bash
# RDS Instance
DB Instance: factorialbot-prod
Engine: PostgreSQL
Force SSL: enabled (rds.force_ssl=1)
Idle Connection Timeout: ~10-15 minutes (typical for RDS)

# Parameter Group
Name: factorialbot-params
rds.force_ssl: 1 (enabled)
```

### Connection String Format for RDS

```bash
postgresql://USERNAME:PASSWORD@RDS-ENDPOINT.region.rds.amazonaws.com:5432/DATABASE_NAME?sslmode=require
```

**Example:**
```bash
DATABASE_URL=postgresql://chatcraft_admin:secure_password@factorialbot-prod.abc123.us-east-1.rds.amazonaws.com:5432/onboard_db?sslmode=require
```

---

## Connection Pool Settings Explained

### POOL_SIZE (default: 10)
- Number of persistent database connections maintained in the pool
- **Too low:** Connection exhaustion under load
- **Too high:** Wastes database resources
- **Recommended:** 10-20 connections per service

### POOL_MAX_OVERFLOW (default: 20)
- Additional temporary connections created when pool is exhausted
- These connections are closed after use
- **Recommended:** 1.5-2x POOL_SIZE

### POOL_RECYCLE_SECONDS (default: 300)
- **OLD:** 3600 (1 hour)
- **NEW:** 300 (5 minutes)
- Connections are recycled (closed and reopened) after this period
- **Why changed:** RDS closes idle connections after ~10-15 minutes
- Setting lower than RDS timeout prevents "connection closed" errors

### POOL_TIMEOUT (default: 30)
- Maximum seconds to wait for a connection from the pool
- **NEW setting** - previously would wait indefinitely
- Prevents hanging when pool is exhausted
- Returns error instead of hanging forever

### CONNECT_TIMEOUT (default: 10)
- **NEW setting** - connection establishment timeout
- Maximum seconds to wait when establishing new database connection
- Prevents hanging on network issues or database unavailability
- Faster failure allows for retries or circuit breaking

### STATEMENT_TIMEOUT (default: 30000ms / 30 seconds)
- **NEW setting** - maximum query execution time
- Prevents long-running queries from blocking connections
- Can be overridden per query if needed
- Set at PostgreSQL session level via connection options

---

## Troubleshooting Guide

### Error: "SSL connection has been closed unexpectedly"

**Symptoms:**
- Intermittent connection errors in production
- Errors occur after periods of inactivity
- SQLAlchemy pool reset failures

**Solution:**
1. ✅ **Verify `?sslmode=require` in DATABASE_URL** (production .env)
2. ✅ **Verify POOL_RECYCLE_SECONDS=300** (code already updated)
3. ✅ Restart the service
4. ✅ Monitor logs for 24 hours

### Error: "server does not support SSL, but SSL was required"

**Symptoms:**
- Service fails to start immediately
- Error occurs in development environment

**Cause:** Local PostgreSQL doesn't have SSL enabled

**Solution:**
```bash
# Development .env - REMOVE ?sslmode=require
DATABASE_URL=postgresql://postgres:password@localhost:5432/database_name

# Or enable SSL on local PostgreSQL (not recommended for dev)
```

### Error: "connection timed out"

**Symptoms:**
- Slow query responses
- Timeout errors after 30 seconds

**Possible Causes:**
1. Database query taking longer than 30 seconds (statement_timeout)
2. Network issues between app and database
3. Database under heavy load

**Solutions:**
```bash
# If legitimate long-running queries, increase timeout:
DATABASE_URL=...?sslmode=require&options=-c%20statement_timeout=60000

# Or disable statement timeout for specific queries in code:
db.execute("SET statement_timeout = 0")  # No timeout for this session
```

### Error: "TimeoutError: QueuePool limit of size X overflow Y reached"

**Symptoms:**
- All connections in pool are busy
- New requests wait for POOL_TIMEOUT (30s) then fail

**Causes:**
1. Too many concurrent database operations
2. Slow queries holding connections too long
3. Connection leaks (not being returned to pool)

**Solutions:**
```bash
# Increase pool size
POOL_SIZE=20
POOL_MAX_OVERFLOW=40

# Or investigate slow queries and connection leaks in code
```

---

## Deployment Checklist

### Pre-Deployment

- [ ] Code changes deployed to all services (already done ✅)
- [ ] Backup current production .env files
- [ ] Verify RDS endpoint and credentials
- [ ] Plan maintenance window (low-traffic period)

### Deployment Steps

**For each service (onboarding, billing, chat, communications):**

1. **Update production .env file:**
   ```bash
   # SSH to production server
   nano /path/to/service/.env

   # Add ?sslmode=require to DATABASE_URL
   # Save and exit
   ```

2. **Restart the service:**
   ```bash
   # Docker
   docker-compose restart service-name

   # Or systemd
   sudo systemctl restart service-name

   # Or Kubernetes
   kubectl rollout restart deployment/service-name
   ```

3. **Verify service starts successfully:**
   ```bash
   # Check logs for errors
   docker logs service-name
   # or
   sudo journalctl -u service-name -f
   # or
   kubectl logs deployment/service-name
   ```

4. **Test database connectivity:**
   ```bash
   # Hit health check endpoint
   curl http://service-url/health

   # Or check application logs for successful queries
   ```

### Post-Deployment Monitoring

**First 5 minutes:**
- [ ] Services started without errors
- [ ] No SSL connection errors in logs
- [ ] Database queries executing normally
- [ ] API endpoints responding

**First hour:**
- [ ] No connection pool exhaustion errors
- [ ] No timeout errors
- [ ] Connection pool recycling working (check after 5 minutes)
- [ ] Monitor database connection count in RDS console

**First 24 hours:**
- [ ] No SSL connection closure errors
- [ ] Connection pool remains healthy
- [ ] No increase in error rates
- [ ] Database performance normal

---

## Monitoring Queries

### Check Active Connections (PostgreSQL)

```sql
-- See all active connections per database
SELECT
    datname,
    count(*) as connections,
    max(state) as states
FROM pg_stat_activity
WHERE datname IN ('onboard_db', 'billing_db', 'chatbot_db', 'communications_db', 'vector_db')
GROUP BY datname;

-- See connection details
SELECT
    pid,
    datname,
    usename,
    application_name,
    client_addr,
    state,
    query_start,
    NOW() - query_start AS duration
FROM pg_stat_activity
WHERE datname IN ('onboard_db', 'billing_db', 'chatbot_db', 'communications_db', 'vector_db')
ORDER BY query_start;
```

### Check Connection Limits (RDS)

```sql
-- See current connection settings
SHOW max_connections;

-- See current connection count vs limit
SELECT count(*) as current_connections,
       (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections;
```

---

## Rollback Procedure

If critical issues occur after deployment:

### Quick Rollback

**1. Revert .env changes:**
```bash
# Remove ?sslmode=require from DATABASE_URL
# Or restore backup .env files
```

**2. Restart services:**
```bash
docker-compose restart service-name
# or
sudo systemctl restart service-name
```

### Full Rollback (if needed)

**1. Revert code changes via git:**
```bash
cd /path/to/service
git revert COMMIT_HASH
git push
```

**2. Redeploy previous version**

**3. Restart services**

---

## Performance Impact

### Expected Improvements

✅ **Eliminated SSL connection closure errors**
✅ **Faster failure on connection issues** (timeouts prevent hanging)
✅ **Better connection pool health** (5-minute recycle vs 1-hour)
✅ **More predictable behavior** under load

### Potential Considerations

⚠️ **Slightly more connection churn** (recycling every 5 minutes vs 1 hour)
- Impact: Negligible - PostgreSQL handles reconnections efficiently
- Trade-off: Worth it to avoid stale SSL connections

⚠️ **Queries timeout after 30 seconds** (new limit)
- Impact: Long-running queries may need optimization
- Solution: Override per-query if legitimately long-running

---

## Additional Resources

**PostgreSQL SSL Documentation:**
- https://www.postgresql.org/docs/current/libpq-ssl.html

**AWS RDS SSL:**
- https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html

**SQLAlchemy Connection Pooling:**
- https://docs.sqlalchemy.org/en/20/core/pooling.html

**psycopg2 Connection Parameters:**
- https://www.psycopg.org/docs/module.html#psycopg2.connect

---

## Support

**For issues or questions:**
1. Check application logs for specific error messages
2. Verify .env configuration matches this guide
3. Test database connectivity manually using psql
4. Check RDS console for connection metrics and logs

**Production Database Team:**
- Slack: #database-ops
- Email: ops@chatcraft.cc

---

**Document Version:** 1.0
**Last Updated:** November 24, 2025
**Updated By:** Claude Code
**Next Review:** December 2025
