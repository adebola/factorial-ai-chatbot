#!/bin/bash
# Test script to validate all Dockerfiles can build successfully
# Usage: ./test-dockerfiles.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to test build a service
test_build_service() {
    local service_name=$1
    local dockerfile=$2
    local context=$3
    local test_tag="test-${service_name}:$(date +%s)"

    echo -e "\n${YELLOW}Testing build for ${service_name}...${NC}"
    echo "  Dockerfile: $dockerfile"
    echo "  Context: $context"

    if docker build -f "$dockerfile" -t "$test_tag" "$context" --no-cache; then
        echo -e "${GREEN}✓ ${service_name} builds successfully${NC}"

        # Clean up test image
        docker rmi "$test_tag" >/dev/null 2>&1 || true
        return 0
    else
        echo -e "${RED}✗ ${service_name} build failed${NC}"
        return 1
    fi
}

# Change to backend directory
BACKEND_DIR="/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend"
cd "$BACKEND_DIR"

echo -e "${YELLOW}Testing all Dockerfiles...${NC}"
echo "Working directory: $(pwd)"

# Track results
failed_builds=()
successful_builds=()

# Test Python services
echo -e "\n${YELLOW}=== Testing Python Services ===${NC}"

# Test Chat Service
if test_build_service "chat-service" "docker-build/dockerfiles/chat-service.Dockerfile" "."; then
    successful_builds+=("chat-service")
else
    failed_builds+=("chat-service")
fi

# Test Onboarding Service
if test_build_service "onboarding-service" "docker-build/dockerfiles/onboarding-service.Dockerfile" "."; then
    successful_builds+=("onboarding-service")
else
    failed_builds+=("onboarding-service")
fi

# Test Java services
echo -e "\n${YELLOW}=== Testing Java Services ===${NC}"

# Test Authorization Server
if test_build_service "authorization-server" "docker-build/dockerfiles/authorization-server.Dockerfile" "."; then
    successful_builds+=("authorization-server")
else
    failed_builds+=("authorization-server")
fi

# Test Gateway Service (if gateway-service directory exists)
if [ -d "gateway-service" ]; then
    if test_build_service "gateway-service" "docker-build/dockerfiles/gateway-service.Dockerfile" "."; then
        successful_builds+=("gateway-service")
    else
        failed_builds+=("gateway-service")
    fi
else
    echo -e "${YELLOW}Gateway service directory not found, skipping test...${NC}"
fi

# Results summary
echo -e "\n${YELLOW}=== Test Results Summary ===${NC}"

if [ ${#successful_builds[@]} -gt 0 ]; then
    echo -e "${GREEN}Successful builds (${#successful_builds[@]}):${NC}"
    for service in "${successful_builds[@]}"; do
        echo -e "  ${GREEN}✓${NC} $service"
    done
fi

if [ ${#failed_builds[@]} -gt 0 ]; then
    echo -e "\n${RED}Failed builds (${#failed_builds[@]}):${NC}"
    for service in "${failed_builds[@]}"; do
        echo -e "  ${RED}✗${NC} $service"
    done
    echo -e "\n${RED}Some Dockerfiles failed to build. Please check the errors above.${NC}"
    exit 1
else
    echo -e "\n${GREEN}🎉 All Dockerfiles build successfully!${NC}"
    echo -e "${GREEN}Ready for production deployment.${NC}"
fi

# Clean up any remaining test images
echo -e "\n${YELLOW}Cleaning up test images...${NC}"
docker images --format "table {{.Repository}}:{{.Tag}}" | grep "^test-" | xargs -r docker rmi >/dev/null 2>&1 || true

echo -e "\n${GREEN}Test complete!${NC}"