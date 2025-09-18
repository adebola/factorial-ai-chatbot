#!/bin/bash
# Build script for all FactorialBot services
# Usage: ./build-all-services.sh [--push]

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
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"
USE_BUILDX=true
SAVE_IMAGES=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH_TO_REGISTRY=true
            echo -e "${YELLOW}Images will be pushed to registry after building${NC}"
            shift
            ;;
        --platform)
            PLATFORMS="$2"
            echo -e "${YELLOW}Building for platforms: $PLATFORMS${NC}"
            shift 2
            ;;
        --no-buildx)
            USE_BUILDX=false
            echo -e "${YELLOW}Using traditional docker build (single platform)${NC}"
            shift
            ;;
        --save)
            SAVE_IMAGES=true
            echo -e "${YELLOW}Images will be saved to tar files${NC}"
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--push] [--platform PLATFORMS] [--no-buildx] [--save]"
            exit 1
            ;;
    esac
done

# Function to build a service
build_service() {
    local service_name=$1
    local dockerfile=$2
    local context=$3
    local image_name="${DOCKER_REGISTRY}/${service_name}:${VERSION}"

    echo -e "\n${YELLOW}Building ${service_name}...${NC}"
    echo "  Dockerfile: $dockerfile"
    echo "  Context: $context"
    echo "  Platforms: $PLATFORMS"
    echo "  Multi-platform: $USE_BUILDX"

    if $USE_BUILDX; then
        # Create buildx builder if it doesn't exist
        if ! docker buildx inspect multiplatform-builder >/dev/null 2>&1; then
            echo -e "${YELLOW}Creating buildx builder for multi-platform builds...${NC}"
            docker buildx create --name multiplatform-builder --use
        else
            docker buildx use multiplatform-builder
        fi

        # Build command for multi-platform
        local build_cmd="docker buildx build"
        build_cmd="$build_cmd --platform $PLATFORMS"
        build_cmd="$build_cmd -f $dockerfile"
        build_cmd="$build_cmd -t $image_name"

        if $PUSH_TO_REGISTRY; then
            build_cmd="$build_cmd --push"
        else
            build_cmd="$build_cmd --load"
        fi

        build_cmd="$build_cmd $context"

        echo -e "${YELLOW}Running: $build_cmd${NC}"
        if eval "$build_cmd"; then
            echo -e "${GREEN}✓ Successfully built ${image_name}${NC}"
            if $PUSH_TO_REGISTRY; then
                echo -e "${GREEN}✓ Successfully pushed ${image_name} (multi-platform)${NC}"
            fi
        else
            echo -e "${RED}✗ Failed to build ${service_name}${NC}"
            return 1
        fi
    else
        # Traditional single-platform build
        if docker build -f "$dockerfile" -t "$image_name" "$context"; then
            echo -e "${GREEN}✓ Successfully built ${image_name}${NC}"

            if $PUSH_TO_REGISTRY; then
                echo -e "${YELLOW}Pushing ${image_name} to registry...${NC}"
                if docker push "$image_name"; then
                    echo -e "${GREEN}✓ Successfully pushed ${image_name}${NC}"
                else
                    echo -e "${RED}✗ Failed to push ${image_name}${NC}"
                    return 1
                fi
            fi
        else
            echo -e "${RED}✗ Failed to build ${service_name}${NC}"
            return 1
        fi
    fi
}

# Change to backend directory
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend

echo -e "${YELLOW}Starting build process for all services...${NC}"
echo "Registry: ${DOCKER_REGISTRY}"
echo "Version: ${VERSION}"
echo "Platforms: ${PLATFORMS}"
echo "Multi-platform builds: ${USE_BUILDX}"
echo "Push to registry: ${PUSH_TO_REGISTRY}"

# Ensure docker buildx is available for multi-platform builds
if $USE_BUILDX; then
    if ! command -v docker &> /dev/null || ! docker buildx version &> /dev/null; then
        echo -e "${RED}Error: Docker Buildx is required for multi-platform builds${NC}"
        echo -e "${YELLOW}Please install Docker Buildx or use --no-buildx flag${NC}"
        exit 1
    fi
fi

# Build Python services
echo -e "\n${YELLOW}=== Building Python Services ===${NC}"

# Chat Service
build_service "chat-service" \
    "docker-build/dockerfiles/chat-service.Dockerfile" \
    "."

# Onboarding Service
build_service "onboarding-service" \
    "docker-build/dockerfiles/onboarding-service.Dockerfile" \
    "."

# Build Java services
echo -e "\n${YELLOW}=== Building Java Services ===${NC}"

# Authorization Server
build_service "ai-authorization-service" \
    "docker-build/dockerfiles/authorization-service.Dockerfile" \
    "."

# Gateway Service (if exists)
if [ -d "gateway-service" ]; then
    build_service "ai-gateway-service" \
        "docker-build/dockerfiles/gateway-service.Dockerfile" \
        "."
else
    echo -e "${YELLOW}Gateway service directory not found, skipping...${NC}"
fi

echo -e "\n${GREEN}=== Build Summary ===${NC}"
echo "All services built successfully!"

# List all built images
echo -e "\n${YELLOW}Built images:${NC}"
docker images | grep "${DOCKER_REGISTRY}" | grep "${VERSION}"

# Optional: Save images to tar for offline deployment
if $SAVE_IMAGES; then
    echo -e "\n${YELLOW}Saving images to tar files...${NC}"
    mkdir -p docker-images

    docker save -o docker-images/chat-service.tar ${DOCKER_REGISTRY}/chat-service:${VERSION}
    docker save -o docker-images/onboarding-service.tar ${DOCKER_REGISTRY}/onboarding-service:${VERSION}
    docker save -o docker-images/authorization-server.tar ${DOCKER_REGISTRY}/ai-authorization-server:${VERSION}

    echo -e "${GREEN}Images saved to docker-images/ directory${NC}"
fi

echo -e "\n${GREEN}Build complete!${NC}"