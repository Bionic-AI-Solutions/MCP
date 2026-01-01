#!/bin/bash
# Build script for MCP Server Docker images

set -e

IMAGE_REGISTRY="${IMAGE_REGISTRY:-your-registry.io}"
IMAGE_NAME="${IMAGE_NAME:-mcp-servers}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Building MCP Server Docker images..."
echo "Registry: $IMAGE_REGISTRY"
echo "Image: $IMAGE_NAME"
echo "Tag: $IMAGE_TAG"

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Build images for each stage
echo ""
echo "Building calculator image..."
docker build --target calculator -t "$IMAGE_REGISTRY/$IMAGE_NAME-calculator:$IMAGE_TAG" .

echo ""
echo "Building postgres image..."
docker build --target postgres -t "$IMAGE_REGISTRY/$IMAGE_NAME-postgres:$IMAGE_TAG" .

echo ""
echo "Building minio image..."
docker build --target minio -t "$IMAGE_REGISTRY/$IMAGE_NAME-minio:$IMAGE_TAG" .

echo ""
echo "Building pdf-generator image..."
docker build --target pdf-generator -t "$IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator:$IMAGE_TAG" .

echo ""
echo "Building ffmpeg image..."
docker build --target ffmpeg -t "$IMAGE_REGISTRY/$IMAGE_NAME-ffmpeg:$IMAGE_TAG" .

echo ""
echo "Building mail image..."
docker build --target mail -t "$IMAGE_REGISTRY/$IMAGE_NAME-mail:$IMAGE_TAG" .

# Optionally push images
if [ "${PUSH_IMAGES:-false}" = "true" ]; then
    echo ""
    echo "Pushing images to registry..."
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-calculator:$IMAGE_TAG"
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-postgres:$IMAGE_TAG"
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-minio:$IMAGE_TAG"
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator:$IMAGE_TAG"
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-ffmpeg:$IMAGE_TAG"
    docker push "$IMAGE_REGISTRY/$IMAGE_NAME-mail:$IMAGE_TAG"
fi

echo ""
echo "Build complete!"
echo ""
echo "Images built:"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-calculator:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-postgres:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-minio:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-ffmpeg:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-mail:$IMAGE_TAG"




