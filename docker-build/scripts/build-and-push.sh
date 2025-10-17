#!/bin/bash
# Build and push all Docker images to Docker Hub
# Usage: ./build-and-push.sh [version] [docker-username]

set -e

# Configuration
VERSION=${1:-latest}
DOCKER_USERNAME=${2:-adebola}
PROJECT_ROOT="../"

echo "🏗️  Building FactorialBot Docker images..."
echo "📦 Version: $VERSION"
echo "🐳 Docker Hub username: $DOCKER_USERNAME"
echo "🖥️  Target Platform: linux/amd64 (Intel compatible)"

# Ensure Docker buildx is set up for cross-platform builds
echo "🔧 Setting up Docker buildx for cross-platform builds..."
if ! docker buildx ls | grep -q multiplatform; then
    echo "📋 Creating multiplatform builder instance..."
    docker buildx create --name multiplatform --driver docker-container --use
    docker buildx inspect --bootstrap
else
    echo "✅ Multiplatform builder already exists"
    docker buildx use multiplatform
fi

# Function to build and push an image
build_and_push() {
    local service=$1
    local dockerfile=$2
    local image_name="$DOCKER_USERNAME/${service}:${VERSION}"
    
    echo ""
    echo "🔨 Building $service for Intel/AMD64 platform (M1 Mac compatible)..."
    docker build --platform=linux/amd64 -f "$dockerfile" -t "$image_name" "$PROJECT_ROOT"
    
    echo "📤 Pushing $service to Docker Hub..."
    docker push "$image_name"
    
    # Also tag as latest if version is not latest
    if [ "$VERSION" != "latest" ]; then
        docker tag "$image_name" "$DOCKER_USERNAME/${service}:latest"
        docker push "$DOCKER_USERNAME/${service}:latest"
    fi
    
    echo "✅ $service completed"
}

# Build and push all services
build_and_push "gateway-service" "dockerfiles/gateway-service.Dockerfile"
build_and_push "chat-service" "dockerfiles/chat-service.Dockerfile"
build_and_push "onboarding-service" "dockerfiles/onboarding-service.Dockerfile"
build_and_push "communications-service" "dockerfiles/communications-service.Dockerfile"
build_and_push "billing-service" "dockerfiles/billing-service.Dockerfile"
build_and_push "workflow-service" "dockerfiles/workflow-service.Dockerfile"

echo ""
echo "🎉 All images built and pushed successfully!"
echo ""
echo "📋 Images created:"
echo "   - $DOCKER_USERNAME/gateway-service:$VERSION"
echo "   - $DOCKER_USERNAME/chat-service:$VERSION"
echo "   - $DOCKER_USERNAME/onboarding-service:$VERSION"
echo "   - $DOCKER_USERNAME/communications-service:$VERSION"
echo "   - $DOCKER_USERNAME/billing-service:$VERSION"
echo "   - $DOCKER_USERNAME/workflow-service:$VERSION"
echo ""
echo "🚀 Ready for deployment with: docker-compose up -d"