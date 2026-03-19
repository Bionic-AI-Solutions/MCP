#!/bin/bash
# Build, push, and deploy the Letta MCP server only.
# Usage: ./k8s/deploy-letta.sh [IMAGE_TAG]

set -e

IMAGE_REGISTRY="${IMAGE_REGISTRY:-docker.io/docker4zerocool}"
IMAGE_NAME="mcp-servers-letta"
IMAGE_TAG="${1:-latest}"
NAMESPACE="${NAMESPACE:-mcp}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "Building Letta MCP server..."
docker build --target letta -t "$IMAGE_REGISTRY/$IMAGE_NAME:$IMAGE_TAG" .

echo ""
echo "Pushing to registry..."
docker push "$IMAGE_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

if command -v kubectl &> /dev/null; then
    echo ""
    echo "Restarting mcp-letta-server deployment..."
    kubectl rollout restart deployment/mcp-letta-server -n "$NAMESPACE"
    echo "Waiting for rollout..."
    kubectl rollout status deployment/mcp-letta-server -n "$NAMESPACE" --timeout=120s
    echo ""
    echo "Pod status:"
    kubectl get pods -n "$NAMESPACE" -l app=mcp-letta-server
    echo ""
    echo "✅ Letta MCP server deployed!"
    echo "   Endpoint: https://mcp.baisoln.com/letta/mcp"
else
    echo ""
    echo "Warning: kubectl not found. Image pushed. Restart deployment manually:"
    echo "  kubectl rollout restart deployment/mcp-letta-server -n $NAMESPACE"
fi
