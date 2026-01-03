#!/bin/bash
# Build a single Docker service image
# Usage: ./build-service.sh <service-name> [version] [docker-username]

set -e

# Configuration
SERVICE=$1
VERSION=${2:-latest}
DOCKER_USERNAME=${3:-adebola}
PROJECT_ROOT="../"

if [ -z "$SERVICE" ]; then
    echo "❌ Error: Service name is required"
    echo ""
    echo "Usage: ./build-service.sh <service-name> [version] [docker-username]"
    echo ""
    echo "Available services:"
    echo "  - gateway-service"
    echo "  - chat-service"
    echo "  - onboarding-service"
    echo "  - communications-service"
    echo "  - billing-service"
    echo "  - workflow-service"
    echo ""
    exit 1
fi

# Map service name to Dockerfile
case $SERVICE in
    gateway-service)
        DOCKERFILE="dockerfiles/gateway-service.Dockerfile"
        ;;
    chat-service)
        DOCKERFILE="dockerfiles/chat-service.Dockerfile"
        ;;
    onboarding-service)
        DOCKERFILE="dockerfiles/onboarding-service.Dockerfile"
        ;;
    communications-service)
        DOCKERFILE="dockerfiles/communications-service.Dockerfile"
        ;;
    billing-service)
        DOCKERFILE="dockerfiles/billing-service.Dockerfile"
        ;;
    workflow-service)
        DOCKERFILE="dockerfiles/workflow-service.Dockerfile"
        ;;
    *)
        echo "❌ Error: Unknown service '$SERVICE'"
        exit 1
        ;;
esac

IMAGE_NAME="$DOCKER_USERNAME/${SERVICE}:${VERSION}"

echo "🏗️  Building Docker image for $SERVICE..."
echo "📦 Version: $VERSION"
echo "🐳 Image: $IMAGE_NAME"
echo "🖥️  Target Platform: linux/amd64"
echo ""

# Build the image
echo "🔨 Building image..."
docker build --platform=linux/amd64 -f "$DOCKERFILE" -t "$IMAGE_NAME" "$PROJECT_ROOT"

echo ""
echo "✅ Build completed successfully!"
echo ""
echo "📋 Image created: $IMAGE_NAME"
echo ""
echo "Next steps:"
echo "  📤 Push to registry: docker push $IMAGE_NAME"
echo "  🚀 Run locally: docker run -p <port>:<port> $IMAGE_NAME"
echo ""
