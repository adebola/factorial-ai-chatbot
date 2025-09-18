#!/bin/bash
# Build script for a single FactorialBot service
# Usage: ./build-single-service.sh <service-name> [--push] [--platform PLATFORMS]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DOCKER_REGISTRY="${DOCKER_REGISTRY:-adebola}"
VERSION="${VERSION:-latest}"
PUSH_TO_REGISTRY=false
PLATFORMS="${PLATFORMS:-linux/amd64}"
SERVICE_NAME=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH_TO_REGISTRY=true
            shift
            ;;
        --platform)
            PLATFORMS="$2"
            shift 2
            ;;
        chat-service|onboarding-service|authorization-service|gateway-service|ai-authorization-service|ai-gateway-service)
            SERVICE_NAME="$1"
            shift
            ;;
        *)
            if [[ -z "$SERVICE_NAME" ]]; then
                SERVICE_NAME="$1"
            else
                echo -e "${RED}Unknown option: $1${NC}"
                echo "Usage: $0 <service-name> [--push] [--platform PLATFORMS]"
                echo "Available services:"
                echo "  - chat-service"
                echo "  - onboarding-service"
                echo "  - authorization-service (or ai-authorization-service)"
                echo "  - gateway-service (or ai-gateway-service)"
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate service name
if [[ -z "$SERVICE_NAME" ]]; then
    echo -e "${RED}Error: Service name is required${NC}"
    echo "Usage: $0 <service-name> [--push] [--platform PLATFORMS]"
    echo ""
    echo "Available services:"
    echo "  - chat-service"
    echo "  - onboarding-service"
    echo "  - authorization-service (or ai-authorization-service)"
    echo "  - gateway-service (or ai-gateway-service)"
    exit 1
fi

# Map service names to Dockerfile paths and image names
case "$SERVICE_NAME" in
    chat-service)
        DOCKERFILE="docker-build/dockerfiles/chat-service.Dockerfile"
        IMAGE_NAME="${DOCKER_REGISTRY}/chat-service:${VERSION}"
        ;;
    onboarding-service)
        DOCKERFILE="docker-build/dockerfiles/onboarding-service.Dockerfile"
        IMAGE_NAME="${DOCKER_REGISTRY}/onboarding-service:${VERSION}"
        ;;
    authorization-service|ai-authorization-service)
        DOCKERFILE="docker-build/dockerfiles/authorization-service.Dockerfile"
        IMAGE_NAME="${DOCKER_REGISTRY}/ai-authorization-service:${VERSION}"
        ;;
    gateway-service|ai-gateway-service)
        DOCKERFILE="docker-build/dockerfiles/gateway-service.Dockerfile"
        IMAGE_NAME="${DOCKER_REGISTRY}/ai-gateway-service:${VERSION}"
        ;;
    *)
        echo -e "${RED}Error: Unknown service: $SERVICE_NAME${NC}"
        echo "Available services: chat-service, onboarding-service, authorization-service, gateway-service"
        exit 1
        ;;
esac

# Change to backend directory
BACKEND_DIR="/Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend"
cd "$BACKEND_DIR"

echo -e "${YELLOW}Building $SERVICE_NAME...${NC}"
echo "  Registry: ${DOCKER_REGISTRY}"
echo "  Version: ${VERSION}"
echo "  Platforms: ${PLATFORMS}"
echo "  Push to registry: ${PUSH_TO_REGISTRY}"
echo "  Dockerfile: ${DOCKERFILE}"
echo "  Image: ${IMAGE_NAME}"
echo ""

# Check if dockerfile exists
if [[ ! -f "$DOCKERFILE" ]]; then
    echo -e "${RED}Error: Dockerfile not found: $DOCKERFILE${NC}"
    exit 1
fi

# Create buildx builder if it doesn't exist
if ! docker buildx inspect multiplatform-builder >/dev/null 2>&1; then
    echo -e "${YELLOW}Creating buildx builder for multi-platform builds...${NC}"
    docker buildx create --name multiplatform-builder --use
else
    docker buildx use multiplatform-builder
fi

# Build command
build_cmd="docker buildx build"
build_cmd="$build_cmd --platform $PLATFORMS"
build_cmd="$build_cmd -f $DOCKERFILE"
build_cmd="$build_cmd -t $IMAGE_NAME"

if $PUSH_TO_REGISTRY; then
    build_cmd="$build_cmd --push"
else
    # Note: --load only works with single platform
    if [[ "$PLATFORMS" == *","* ]]; then
        echo -e "${YELLOW}Warning: Multiple platforms specified. Cannot load to local Docker.${NC}"
        echo -e "${YELLOW}The image will be built but not loaded. Use --push to push to registry.${NC}"
    else
        build_cmd="$build_cmd --load"
    fi
fi

build_cmd="$build_cmd ."

echo -e "${YELLOW}Running: $build_cmd${NC}"
echo ""

if eval "$build_cmd"; then
    echo -e "\n${GREEN}✓ Successfully built ${IMAGE_NAME}${NC}"
    if $PUSH_TO_REGISTRY; then
        echo -e "${GREEN}✓ Successfully pushed ${IMAGE_NAME} to registry${NC}"
    fi

    # Show next steps
    echo -e "\n${YELLOW}Next steps:${NC}"
    if $PUSH_TO_REGISTRY; then
        echo "  - Image is available at: ${IMAGE_NAME}"
        echo "  - Pull on production: docker pull ${IMAGE_NAME}"
    else
        echo "  - Test locally: docker run --rm ${IMAGE_NAME}"
        echo "  - Push to registry: $0 $SERVICE_NAME --push"
    fi
else
    echo -e "\n${RED}✗ Failed to build ${SERVICE_NAME}${NC}"
    exit 1
fi

echo -e "\n${GREEN}Build complete!${NC}"