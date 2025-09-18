#!/bin/bash
# Deep diagnostic script for Authorization Server issues

echo "=== Authorization Server Deep Diagnostics ==="
echo ""
echo "Timestamp: $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 1. Check container status
echo -e "${YELLOW}1. Container Status Check${NC}"
echo "----------------------------------------"
container_id=$(docker ps -q -f name=authorization-service)
if [ -n "$container_id" ]; then
    echo -e "${GREEN}✓ Container is running${NC}"
    echo "Container ID: $container_id"
    docker inspect authorization-service --format='Status: {{.State.Status}}'
    docker inspect authorization-service --format='Started: {{.State.StartedAt}}'
    docker inspect authorization-service --format='Restart Count: {{.RestartCount}}'
else
    echo -e "${RED}✗ Container is not running${NC}"
    # Check if it exists but stopped
    if docker ps -a | grep -q authorization-service; then
        echo "Container exists but is stopped. Last status:"
        docker ps -a --filter name=authorization-service --format "table {{.Names}}\t{{.Status}}\t{{.State}}"
    fi
fi
echo ""

# 2. Check port binding from Docker
echo -e "${YELLOW}2. Docker Port Mapping${NC}"
echo "----------------------------------------"
docker port authorization-service 2>/dev/null || echo -e "${RED}Cannot get port mapping${NC}"
echo ""
echo "Docker inspect ports:"
docker inspect authorization-service --format='{{json .NetworkSettings.Ports}}' 2>/dev/null | python3 -m json.tool || echo "Failed to get port info"
echo ""

# 3. Check what's actually listening on port 9002
echo -e "${YELLOW}3. Port 9002 Listening Status${NC}"
echo "----------------------------------------"
echo "Checking what's listening on port 9002:"
sudo netstat -tlnp | grep :9002 || sudo lsof -i :9002 || echo -e "${RED}Nothing listening on port 9002${NC}"
echo ""

# 4. Check container networking
echo -e "${YELLOW}4. Container Network Configuration${NC}"
echo "----------------------------------------"
docker inspect authorization-service --format='Network Mode: {{.HostConfig.NetworkMode}}' 2>/dev/null
docker inspect authorization-service --format='IP Address: {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null
echo ""

# 5. Test connectivity from INSIDE the container
echo -e "${YELLOW}5. Testing From Inside Container${NC}"
echo "----------------------------------------"
if [ -n "$container_id" ]; then
    echo "Testing localhost:9000 from inside container:"
    docker exec authorization-service curl -s -m 2 http://localhost:9000/actuator/health 2>&1 || echo -e "${RED}Failed to connect from inside container${NC}"
    echo ""
    echo "Checking if Java process is running:"
    docker exec authorization-service ps aux | grep java | head -1 || echo -e "${RED}No Java process found${NC}"
else
    echo -e "${RED}Container not running, skipping internal tests${NC}"
fi
echo ""

# 6. Check container logs for startup errors
echo -e "${YELLOW}6. Container Logs (Last 50 lines)${NC}"
echo "----------------------------------------"
docker logs authorization-service --tail 50 2>&1 | tail -30 || echo -e "${RED}Cannot get logs${NC}"
echo ""

# 7. Check environment variables
echo -e "${YELLOW}7. Critical Environment Variables${NC}"
echo "----------------------------------------"
if [ -n "$container_id" ]; then
    docker exec authorization-service printenv | grep -E "SERVER_|SPRING_" | head -10
else
    echo "Getting from docker inspect:"
    docker inspect authorization-service --format='{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep -E "SERVER_|SPRING_" | head -10
fi
echo ""

# 8. Memory and CPU usage
echo -e "${YELLOW}8. Container Resource Usage${NC}"
echo "----------------------------------------"
docker stats authorization-service --no-stream 2>/dev/null || echo -e "${RED}Cannot get stats${NC}"
echo ""

# 9. Test different connection methods
echo -e "${YELLOW}9. Connection Tests${NC}"
echo "----------------------------------------"
echo "Test 1: Using curl to 127.0.0.1:9002"
timeout 2 curl -v http://127.0.0.1:9002/ 2>&1 | grep -E "(Connected|Recv|Connection)" | head -5

echo ""
echo "Test 2: Using nc (netcat) to 127.0.0.1:9002"
echo "GET / HTTP/1.1\nHost: localhost\n\n" | timeout 2 nc 127.0.0.1 9002 2>&1 | head -5 || echo "Connection failed"

echo ""
echo "Test 3: Using telnet to 127.0.0.1:9002"
timeout 2 telnet 127.0.0.1 9002 2>&1 | head -5 || echo "Telnet failed"
echo ""

# 10. Check if authorization_db exists
echo -e "${YELLOW}10. Database Connection Check${NC}"
echo "----------------------------------------"
echo "Checking if authorization_db exists:"
docker exec postgres psql -U postgres -lqt 2>/dev/null | grep authorization_db || echo -e "${RED}authorization_db not found${NC}"
echo ""

# 11. Suggest fixes
echo -e "${BLUE}=== Diagnostic Analysis ===${NC}"
echo "----------------------------------------"

if [ -z "$container_id" ]; then
    echo -e "${RED}CRITICAL: Container is not running${NC}"
    echo "Fix: docker-compose -f docker-compose-production-optimized.yml up -d authorization-server"
elif ! sudo netstat -tlnp | grep -q :9002; then
    echo -e "${RED}CRITICAL: Port 9002 is not bound${NC}"
    echo "Possible fixes:"
    echo "1. Add SERVER_ADDRESS=0.0.0.0 to environment variables"
    echo "2. Check if container is restarting due to errors"
    echo "3. Verify the application is starting correctly"
fi

echo ""
echo -e "${BLUE}Quick Fix Commands:${NC}"
echo "1. Restart the service:"
echo "   docker-compose -f docker-compose-production-optimized.yml restart authorization-server"
echo ""
echo "2. Recreate the service:"
echo "   docker-compose -f docker-compose-production-optimized.yml up -d --force-recreate authorization-server"
echo ""
echo "3. Check live logs:"
echo "   docker logs -f authorization-service"
echo ""
echo "4. Execute into container:"
echo "   docker exec -it authorization-service sh"