#!/bin/bash
# Diagnostic script for Authorization Server connectivity issues

echo "=== Authorization Server Diagnostics ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check if authorization-server container is running
echo -e "${YELLOW}1. Checking authorization-server container status...${NC}"
if docker ps | grep -q "authorization-service"; then
    echo -e "${GREEN}✓ Container is running${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep authorization
else
    echo -e "${RED}✗ Container is not running${NC}"
    echo "Checking if container exists but stopped:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep authorization
fi
echo ""

# 2. Check container logs for errors
echo -e "${YELLOW}2. Checking last 20 lines of authorization-server logs...${NC}"
docker logs authorization-service --tail 20 2>&1 | tail -10
echo ""

# 3. Test connectivity from host to port 9002
echo -e "${YELLOW}3. Testing connectivity to port 9002 from host...${NC}"
if nc -zv 127.0.0.1 9002 2>&1 | grep -q "succeeded"; then
    echo -e "${GREEN}✓ Port 9002 is accessible${NC}"
else
    echo -e "${RED}✗ Port 9002 is not accessible${NC}"
    echo "Checking what's listening on port 9002:"
    sudo lsof -i :9002 || netstat -tuln | grep 9002
fi
echo ""

# 4. Test HTTP connectivity
echo -e "${YELLOW}4. Testing HTTP connectivity to authorization server...${NC}"
echo "Attempting curl to http://127.0.0.1:9002/.well-known/openid-configuration"
curl -v -m 5 http://127.0.0.1:9002/.well-known/openid-configuration 2>&1 | head -20
echo ""

# 5. Check if authorization server is healthy
echo -e "${YELLOW}5. Checking authorization server health endpoint...${NC}"
curl -s -m 5 http://127.0.0.1:9002/actuator/health || echo -e "${RED}Health check failed${NC}"
echo ""

# 6. Check Docker network connectivity
echo -e "${YELLOW}6. Checking Docker network configuration...${NC}"
docker network ls | grep chatcraft
echo ""
echo "Authorization server network details:"
docker inspect authorization-service | grep -A 10 "Networks" || echo "Container not found"
echo ""

# 7. Check nginx configuration
echo -e "${YELLOW}7. Testing nginx configuration...${NC}"
if command -v nginx &> /dev/null; then
    nginx -t 2>&1 | grep -E "(test|successful|failed)"
else
    echo "nginx command not found, skipping nginx test"
fi
echo ""

# 8. Check firewall rules (if applicable)
echo -e "${YELLOW}8. Checking firewall status...${NC}"
if command -v ufw &> /dev/null; then
    sudo ufw status | grep -E "(9002|9000)" || echo "No specific rules for authorization server ports"
else
    echo "ufw not found, checking iptables:"
    sudo iptables -L -n | grep -E "(9002|9000)" || echo "No specific iptables rules found"
fi
echo ""

# 9. Verify docker-compose services
echo -e "${YELLOW}9. Checking all docker-compose services...${NC}"
docker-compose -f docker-compose-production-optimized.yml ps 2>/dev/null || docker compose -f docker-compose-production-optimized.yml ps
echo ""

# 10. Test from inside nginx container (if nginx is in container)
echo -e "${YELLOW}10. Additional connectivity tests...${NC}"
echo "Testing if authorization server responds to basic request:"
curl -I -m 5 http://127.0.0.1:9002/ 2>&1 | head -10
echo ""

echo -e "${YELLOW}=== Diagnostic Summary ===${NC}"
echo ""
echo "Common issues and solutions:"
echo "1. If container is not running: docker-compose up -d authorization-server"
echo "2. If port 9002 is not accessible: Check if container port mapping is correct (9002:9000)"
echo "3. If connection reset: Check Spring Boot application startup logs for errors"
echo "4. If nginx can't connect: Ensure nginx uses 127.0.0.1:9002 not localhost:9002"
echo "5. If health check fails: Authorization server may still be starting up"
echo ""
echo "To restart the authorization server:"
echo "  docker-compose -f docker-compose-production-optimized.yml restart authorization-server"
echo ""
echo "To view full logs:"
echo "  docker logs authorization-service -f"