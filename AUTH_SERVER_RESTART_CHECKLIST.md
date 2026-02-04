# Authorization Server - Restart/Rebuild Checklist

## The Problem

After making changes to the authorization server and restarting it, you get automatic logout with 401 errors on all API calls.

## Root Cause

The issue is likely one of these:

1. **Configuration not being applied** - Spring Boot configuration cache
2. **Bean not being registered** - The `jwtAuthenticationConverter` bean might not be loading
3. **Class not recompiled** - SecurityConfig.java changes not picked up
4. **Database connection issue** - Can't load OAuth2 client configuration
5. **Redis cache issue** - Old tokens cached

## Quick Fix Checklist

### Step 1: Verify SecurityConfig.java Has the Fix

```bash
cd authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config

# Check if jwtAuthenticationConverter bean exists
grep -A 10 "jwtAuthenticationConverter()" SecurityConfig.java
```

**Should see:**
```java
@Bean
public JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grantedAuthoritiesConverter = new JwtGrantedAuthoritiesConverter();
    grantedAuthoritiesConverter.setAuthoritiesClaimName("authorities");
    grantedAuthoritiesConverter.setAuthorityPrefix("");
    // ... rest of method
}
```

### Step 2: Clean Build

```bash
cd authorization-server2

# Clean and rebuild
mvn clean install -DskipTests

# Or if using IDE: Build → Rebuild Project
```

### Step 3: Clear Caches

```bash
# Clear Redis cache (important!)
docker exec redis redis-cli FLUSHALL

# Or restart Redis
docker restart redis
```

### Step 4: Restart Authorization Server

```bash
# Stop current server (Ctrl+C or kill process)
kill -9 $(lsof -ti:9002)

# Start fresh
cd authorization-server2
mvn spring-boot:run

# Or use IDE: Run → Restart
```

### Step 5: Check Server Logs on Startup

**Look for this line in the logs:**
```
Configured JwtAuthenticationConverter to extract authorities from 'authorities' claim
```

**If you DON'T see it:**
- The bean isn't being created
- Configuration file wasn't saved
- Build didn't include the changes

### Step 6: Test Login

```bash
# Clear browser cache/session storage
# Or use Incognito mode

# Try login at http://localhost:4201
```

## Troubleshooting

### Issue: jwtAuthenticationConverter bean not loading

**Check:**
1. Is the method annotated with `@Bean`?
2. Is it in a `@Configuration` class?
3. Are there any compilation errors?

**Fix:**
```bash
# Verify compilation
cd authorization-server2
mvn compile

# Check for errors in target directory
ls -la target/classes/io/factorialsystems/authorizationserver2/config/
```

### Issue: Changes not being picked up

**Symptoms:**
- You saved SecurityConfig.java
- But behavior hasn't changed

**Fix:**
```bash
# Force recompile
cd authorization-server2
rm -rf target/
mvn clean compile spring-boot:run
```

### Issue: Database connection problems

**Symptoms:**
- Server starts but OAuth2 doesn't work
- Logs show "Connection refused" or "relation does not exist"

**Fix:**
```bash
# Check database is running
docker ps | grep postgres

# Check connection
docker exec postgres psql -U postgres -d authorization_db2 -c "SELECT 1;"

# Restart database if needed
docker restart postgres
```

### Issue: Redis cache with old tokens

**Symptoms:**
- First login fails
- Second login (after clearing browser) works

**Fix:**
```bash
# Clear all Redis data
docker exec redis redis-cli FLUSHALL

# Or restart Redis
docker restart redis
```

## Prevention - Make Changes Stick

### 1. Always Use Clean Build

When making changes to SecurityConfig.java or any @Configuration class:

```bash
# Don't just restart
mvn spring-boot:run  ❌

# Do this instead
mvn clean install && mvn spring-boot:run  ✅
```

### 2. Verify Bean Registration

Add logging to confirm your bean is being created:

```java
@Bean
public JwtAuthenticationConverter jwtAuthenticationConverter() {
    log.info("🔧 Configuring JwtAuthenticationConverter"); // Add this

    JwtGrantedAuthoritiesConverter grantedAuthoritiesConverter = new JwtGrantedAuthoritiesConverter();
    grantedAuthoritiesConverter.setAuthoritiesClaimName("authorities");
    grantedAuthoritiesConverter.setAuthorityPrefix("");

    JwtAuthenticationConverter jwtAuthenticationConverter = new JwtAuthenticationConverter();
    jwtAuthenticationConverter.setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter);

    log.info("✅ JwtAuthenticationConverter configured successfully"); // Add this

    return jwtAuthenticationConverter;
}
```

### 3. Clear Caches After Rebuild

Add this to your restart script:

```bash
#!/bin/bash
# restart-auth-server.sh

echo "Stopping auth server..."
kill -9 $(lsof -ti:9002) 2>/dev/null

echo "Clearing Redis cache..."
docker exec redis redis-cli FLUSHALL

echo "Clean build..."
cd authorization-server2
mvn clean install -DskipTests

echo "Starting server..."
mvn spring-boot:run
```

## Quick Recovery Script

Save this as `fix-auth-401.sh`:

```bash
#!/bin/bash

echo "=========================================="
echo "AUTH SERVER 401 FIX - QUICK RECOVERY"
echo "=========================================="

# 1. Stop server
echo "1. Stopping auth server..."
kill -9 $(lsof -ti:9002) 2>/dev/null
sleep 2

# 2. Clear Redis
echo "2. Clearing Redis cache..."
docker exec redis redis-cli FLUSHALL

# 3. Verify fix is in code
echo "3. Checking if fix exists in SecurityConfig.java..."
if grep -q "setAuthoritiesClaimName(\"authorities\")" authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config/SecurityConfig.java; then
    echo "   ✅ Fix found in code"
else
    echo "   ❌ Fix NOT found - SecurityConfig.java needs to be updated!"
    exit 1
fi

# 4. Clean build
echo "4. Clean build..."
cd authorization-server2
mvn clean install -DskipTests

# 5. Start server
echo "5. Starting server..."
echo "   Watch for: 'Configured JwtAuthenticationConverter' in logs"
mvn spring-boot:run
```

## When This Happens

1. ✅ Run `./fix-auth-401.sh`
2. ✅ Watch for log message: "Configured JwtAuthenticationConverter"
3. ✅ Clear browser cache
4. ✅ Try login

## Root Cause Investigation

If this keeps happening, we need to find WHY the bean isn't loading. Check:

1. **Is SecurityConfig.java being compiled?**
   ```bash
   ls -la target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class
   stat -f "%Sm" target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class
   ```

2. **Is the bean method present in compiled bytecode?**
   ```bash
   javap -c target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class | grep jwtAuthenticationConverter
   ```

3. **Are there duplicate SecurityConfig classes?**
   ```bash
   find . -name "SecurityConfig.java"
   find . -name "SecurityConfig.class"
   ```

4. **Is Spring picking up the configuration?**
   - Check logs for "Autowired" or "Bean creation" errors
   - Look for ClassNotFoundException or NoSuchBeanDefinitionException

## Summary

**The fix is in the code**, but something is preventing it from being applied consistently. The most common causes are:

1. Not doing a clean build (mvn clean install)
2. Redis cache containing old tokens
3. IDE not recompiling properly
4. Server restart without rebuild

**Solution**: Always use the quick recovery script after making changes to the auth server.
