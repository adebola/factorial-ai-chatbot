#!/bin/bash

echo "=========================================="
echo "AUTH SERVER 401 FIX - QUICK RECOVERY"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ️  $1${NC}"
}

# 1. Stop server
print_info "Step 1: Stopping authorization server on port 9002..."
PIDS=$(lsof -ti:9002 2>/dev/null)
if [ ! -z "$PIDS" ]; then
    kill -9 $PIDS 2>/dev/null
    sleep 2
    print_success "Stopped server (PIDs: $PIDS)"
else
    print_info "No server running on port 9002"
fi
echo ""

# 2. Clear Redis
print_info "Step 2: Clearing Redis cache..."
if docker exec redis redis-cli FLUSHALL >/dev/null 2>&1; then
    print_success "Redis cache cleared"
else
    print_error "Failed to clear Redis - is it running?"
    print_info "Try: docker start redis"
fi
echo ""

# 3. Verify fix is in code
print_info "Step 3: Verifying fix exists in SecurityConfig.java..."
if grep -q 'setAuthoritiesClaimName("authorities")' authorization-server2/src/main/java/io/factorialsystems/authorizationserver2/config/SecurityConfig.java; then
    print_success "Fix found in source code"
else
    print_error "Fix NOT found in SecurityConfig.java!"
    print_info "The jwtAuthenticationConverter bean is missing or incorrect"
    echo ""
    print_info "Expected to find:"
    echo "  grantedAuthoritiesConverter.setAuthoritiesClaimName(\"authorities\");"
    echo ""
    exit 1
fi
echo ""

# 4. Clean build
print_info "Step 4: Clean build (this may take a minute)..."
cd authorization-server2

if mvn clean install -DskipTests -q; then
    print_success "Build completed successfully"
else
    print_error "Build failed - check for compilation errors"
    exit 1
fi
echo ""

# 5. Verify compiled class
print_info "Step 5: Verifying compiled class..."
if [ -f "target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class" ]; then
    TIMESTAMP=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class 2>/dev/null || stat -c "%y" target/classes/io/factorialsystems/authorizationserver2/config/SecurityConfig.class 2>/dev/null | cut -d'.' -f1)
    print_success "SecurityConfig.class compiled at $TIMESTAMP"
else
    print_error "SecurityConfig.class not found in target directory"
    exit 1
fi
echo ""

# 6. Start server
print_info "Step 6: Starting authorization server..."
print_info "Watch for this log message:"
echo "  'Configured JwtAuthenticationConverter to extract authorities from authorities claim'"
echo ""
print_info "Server starting... (press Ctrl+C to stop)"
echo ""
echo "=========================================="
echo ""

mvn spring-boot:run
