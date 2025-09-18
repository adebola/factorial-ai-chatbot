#!/bin/bash
# CORS debugging script for authorization server

echo "=== Authorization Server CORS Diagnostics ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DOMAIN="https://ai.factorialsystems.io"
AUTH_URL="${DOMAIN}/auth"

# 1. Check current CORS configuration in container
echo -e "${YELLOW}1. Current CORS Configuration in Container${NC}"
echo "----------------------------------------"
container_id=$(docker ps -q -f name=authorization-service)
if [ -n "$container_id" ]; then
    echo "Checking environment variables:"
    docker exec authorization-service printenv | grep -E "AUTHORIZATION_CONFIG|CORS|SERVER_" | sort
else
    echo -e "${RED}Container not running${NC}"
fi
echo ""

# 2. Test OPTIONS preflight request
echo -e "${YELLOW}2. Testing OPTIONS Preflight Request${NC}"
echo "----------------------------------------"
echo "Testing: OPTIONS ${AUTH_URL}/oauth2/authorize"
curl -v -X OPTIONS "${AUTH_URL}/oauth2/authorize" \
  -H "Origin: https://ai.factorialsystems.io" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type" \
  2>&1 | grep -E "(< HTTP|< Access-Control|CORS)" || echo "No CORS headers found"
echo ""

# 3. Test login page with Origin header
echo -e "${YELLOW}3. Testing Login Page with Origin Header${NC}"
echo "----------------------------------------"
echo "Testing: GET ${AUTH_URL}/login"
curl -v "${AUTH_URL}/login" \
  -H "Origin: https://ai.factorialsystems.io" \
  -H "Referer: https://ai.factorialsystems.io/" \
  2>&1 | grep -E "(< HTTP|< Access-Control|< X-Frame)" | head -10
echo ""

# 4. Test from different origins
echo -e "${YELLOW}4. Testing Different Origins${NC}"
echo "----------------------------------------"
for origin in "https://ai.factorialsystems.io" "http://localhost:3000" "https://app.chatcraft.cc"; do
    echo -e "${BLUE}Testing origin: $origin${NC}"
    response=$(curl -s -I -X OPTIONS "${AUTH_URL}/oauth2/authorize" \
      -H "Origin: $origin" \
      -H "Access-Control-Request-Method: POST" \
      2>&1 | grep "Access-Control-Allow-Origin" || echo "No CORS header")
    echo "Response: $response"
done
echo ""

# 5. Check actual Spring Boot application properties
echo -e "${YELLOW}5. Spring Boot Application Properties${NC}"
echo "----------------------------------------"
if [ -n "$container_id" ]; then
    echo "Attempting to get actuator info (if enabled):"
    curl -s "${AUTH_URL}/actuator/env/authorization.config.security" 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "Actuator endpoint not accessible"
fi
echo ""

# 6. Test JavaScript fetch simulation
echo -e "${YELLOW}6. Simulating Browser JavaScript Fetch${NC}"
echo "----------------------------------------"
echo "Simulating: fetch('${AUTH_URL}/login')"
curl -v "${AUTH_URL}/login" \
  -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8" \
  -H "Accept-Language: en-US,en;q=0.5" \
  -H "Origin: https://ai.factorialsystems.io" \
  -H "Referer: https://ai.factorialsystems.io/" \
  -H "Sec-Fetch-Dest: document" \
  -H "Sec-Fetch-Mode: navigate" \
  -H "Sec-Fetch-Site: same-origin" \
  2>&1 | grep -E "(< HTTP/|< Access-Control|< X-Frame-Options|< Content-Security-Policy)" | head -15
echo ""

# 7. Check nginx headers being added
echo -e "${YELLOW}7. Nginx Proxy Headers${NC}"
echo "----------------------------------------"
echo "Testing if nginx is adding/modifying CORS headers:"
# Direct to authorization server (if accessible)
echo "Direct to container (port 9002):"
curl -I -X OPTIONS http://127.0.0.1:9002/auth/login \
  -H "Origin: https://ai.factorialsystems.io" \
  2>&1 | grep -i "access-control" || echo "No CORS headers from direct connection"
echo ""
echo "Through nginx proxy:"
curl -I -X OPTIONS "${AUTH_URL}/login" \
  -H "Origin: https://ai.factorialsystems.io" \
  2>&1 | grep -i "access-control" || echo "No CORS headers through nginx"
echo ""

# 8. Common CORS error scenarios
echo -e "${BLUE}=== CORS Error Analysis ===${NC}"
echo "----------------------------------------"

# Check if container has correct environment
if [ -n "$container_id" ]; then
    cors_env=$(docker exec authorization-service printenv | grep AUTHORIZATION_CONFIG_SECURITY_ALLOWEDORIGINS)
    if [ -z "$cors_env" ]; then
        echo -e "${RED}CRITICAL: AUTHORIZATION_CONFIG_SECURITY_ALLOWEDORIGINS not set${NC}"
        echo "Fix: Add this to docker-compose environment:"
        echo '  AUTHORIZATION_CONFIG_SECURITY_ALLOWEDORIGINS: "https://ai.factorialsystems.io,http://localhost:3000"'
    else
        echo -e "${GREEN}✓ CORS environment variable is set${NC}"
        echo "Current value: $cors_env"
        if [[ ! "$cors_env" == *"https://ai.factorialsystems.io"* ]]; then
            echo -e "${RED}WARNING: https://ai.factorialsystems.io is not in allowed origins${NC}"
        fi
    fi
fi

echo ""
echo -e "${BLUE}Quick Fixes:${NC}"
echo "1. Restart with updated CORS configuration:"
echo "   docker-compose -f docker-compose-production-optimized.yml up -d --force-recreate authorization-server"
echo ""
echo "2. Verify CORS is applied:"
echo "   docker exec authorization-service printenv | grep CORS"
echo ""
echo "3. Check Spring Boot logs for CORS initialization:"
echo "   docker logs authorization-service | grep -i cors"
echo ""
echo "4. If using browser, check Developer Console for specific CORS error:"
echo "   - Open F12 Developer Tools"
echo "   - Go to Network tab"
echo "   - Look for red failed requests"
echo "   - Check Console for CORS error messages"