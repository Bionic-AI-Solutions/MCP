#!/bin/bash
# Build script for MCP Server Docker images
# Builds, pushes, and restarts Kubernetes deployments

set -e

IMAGE_REGISTRY="${IMAGE_REGISTRY:-docker.io/docker4zerocool}"
IMAGE_NAME="${IMAGE_NAME:-mcp-servers}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NAMESPACE="${NAMESPACE:-mcp}"

echo "Building MCP Server Docker images..."
echo "Registry: $IMAGE_REGISTRY"
echo "Image: $IMAGE_NAME"
echo "Tag: $IMAGE_TAG"
echo "Namespace: $NAMESPACE"

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

echo ""
echo "Building openproject image..."
docker build --target openproject -t "$IMAGE_REGISTRY/$IMAGE_NAME-openproject:$IMAGE_TAG" .

echo ""
echo "Building meilisearch image..."
docker build --target meilisearch -t "$IMAGE_REGISTRY/$IMAGE_NAME-meilisearch:$IMAGE_TAG" .

echo ""
echo "Building genImage image..."
docker build --target genImage -t "$IMAGE_REGISTRY/$IMAGE_NAME-genimage:$IMAGE_TAG" .

echo ""
echo "Building ai-mcp-server image..."
docker build --target ai-mcp-server -t "$IMAGE_REGISTRY/$IMAGE_NAME-ai-mcp-server:$IMAGE_TAG" .

# Push all images to registry
echo ""
echo "Pushing images to registry..."
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-calculator:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-postgres:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-minio:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-ffmpeg:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-mail:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-openproject:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-meilisearch:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-genimage:$IMAGE_TAG"
docker push "$IMAGE_REGISTRY/$IMAGE_NAME-ai-mcp-server:$IMAGE_TAG"

echo ""
echo "Build and push complete!"
echo ""
echo "Images built and pushed:"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-calculator:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-postgres:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-minio:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-ffmpeg:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-mail:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-openproject:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-meilisearch:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-genimage:$IMAGE_TAG"
echo "  - $IMAGE_REGISTRY/$IMAGE_NAME-ai-mcp-server:$IMAGE_TAG"

# Restart Kubernetes deployments
if command -v kubectl &> /dev/null; then
    echo ""
    echo "Restarting Kubernetes deployments in namespace '$NAMESPACE'..."
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        echo "Warning: Namespace '$NAMESPACE' does not exist. Skipping pod restarts."
    else
        # Restart all MCP server deployments
        echo "  Restarting calculator deployment..."
        kubectl rollout restart deployment/mcp-calculator-server -n "$NAMESPACE" || echo "    Warning: calculator deployment not found"
        
        echo "  Restarting postgres deployment..."
        kubectl rollout restart deployment/mcp-postgres-server -n "$NAMESPACE" || echo "    Warning: postgres deployment not found"
        
        echo "  Restarting minio deployment..."
        kubectl rollout restart deployment/mcp-minio-server -n "$NAMESPACE" || echo "    Warning: minio deployment not found"
        
        echo "  Restarting pdf-generator deployment..."
        kubectl rollout restart deployment/mcp-pdf-generator-server -n "$NAMESPACE" || echo "    Warning: pdf-generator deployment not found"
        
        echo "  Restarting ffmpeg deployment..."
        kubectl rollout restart deployment/mcp-ffmpeg-server -n "$NAMESPACE" || echo "    Warning: ffmpeg deployment not found"
        
        echo "  Restarting mail deployment..."
        kubectl rollout restart deployment/mcp-mail-server -n "$NAMESPACE" || echo "    Warning: mail deployment not found"
        
        echo "  Restarting openproject deployment..."
        kubectl rollout restart deployment/mcp-openproject-server -n "$NAMESPACE" || echo "    Warning: openproject deployment not found"
        
        echo "  Restarting meilisearch deployment..."
        kubectl rollout restart deployment/mcp-meilisearch-server -n "$NAMESPACE" || echo "    Warning: meilisearch deployment not found"
        
        echo "  Restarting genimage deployment..."
        kubectl rollout restart deployment/mcp-genimage-server -n "$NAMESPACE" || echo "    Warning: genimage deployment not found"
        
        echo "  Restarting ai-mcp-server deployment..."
        kubectl rollout restart deployment/mcp-ai-mcp-server -n "$NAMESPACE" || echo "    Warning: ai-mcp-server deployment not found"
        
        echo ""
        echo "Waiting for rollouts to complete..."
        kubectl rollout status deployment/mcp-calculator-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-postgres-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-minio-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-pdf-generator-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-ffmpeg-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-mail-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-openproject-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-meilisearch-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-genimage-server -n "$NAMESPACE" --timeout=300s || true
        kubectl rollout status deployment/mcp-ai-mcp-server -n "$NAMESPACE" --timeout=300s || true
        
        echo ""
        echo "Pod status:"
        kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/part-of=mcp-servers
    fi
else
    echo ""
    echo "Warning: kubectl not found. Skipping Kubernetes pod restarts."
    echo "Install kubectl and ensure it's configured to restart pods manually."
fi

echo ""
echo "✅ Build, push, and deployment restart complete!"
