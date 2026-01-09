#!/bin/bash
# Deployment script for MCP Servers on Kubernetes

set -e

NAMESPACE="mcp"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-your-registry.io}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_NAME="${IMAGE_NAME:-mcp-servers}"

echo "Deploying MCP Servers to Kubernetes..."
echo "Namespace: $NAMESPACE"
echo "Image: $IMAGE_REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed or not in PATH"
    exit 1
fi

# Check if namespace exists, create if not
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    echo "Creating namespace $NAMESPACE..."
    kubectl create namespace $NAMESPACE
fi

# Update image references in kustomization.yaml if provided
if [ -n "$IMAGE_REGISTRY" ] && [ -n "$IMAGE_NAME" ] && [ -n "$IMAGE_TAG" ]; then
    echo "Updating image references in kustomization.yaml..."
    cd k8s
    # Update kustomization.yaml with actual image values
    if command -v yq &> /dev/null; then
        yq eval ".images[0].newName = \"$IMAGE_REGISTRY/$IMAGE_NAME-calculator\"" -i kustomization.yaml
        yq eval ".images[0].newTag = \"$IMAGE_TAG\"" -i kustomization.yaml
        yq eval ".images[1].newName = \"$IMAGE_REGISTRY/$IMAGE_NAME-postgres\"" -i kustomization.yaml
        yq eval ".images[1].newTag = \"$IMAGE_TAG\"" -i kustomization.yaml
        yq eval ".images[2].newName = \"$IMAGE_REGISTRY/$IMAGE_NAME-minio\"" -i kustomization.yaml
        yq eval ".images[2].newTag = \"$IMAGE_TAG\"" -i kustomization.yaml
        yq eval ".images[3].newName = \"$IMAGE_REGISTRY/$IMAGE_NAME-pdf-generator\"" -i kustomization.yaml
        yq eval ".images[3].newTag = \"$IMAGE_TAG\"" -i kustomization.yaml
    else
        echo "Warning: yq not found. Please update kustomization.yaml manually with image references."
    fi
    cd ..
fi

# Apply using kustomize
echo "Applying Kubernetes manifests with kustomize..."
kubectl apply -k k8s/

# Apply all resources using kustomize
echo "Applying Kubernetes manifests..."
kubectl apply -k k8s/

# Wait for deployments to be ready
echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/mcp-calculator-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-postgres-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-minio-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-pdf-generator-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-openproject-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-meilisearch-server -n $NAMESPACE || true
kubectl wait --for=condition=available --timeout=300s deployment/mcp-genimage-server -n $NAMESPACE || true

# Show status
echo ""
echo "Deployment Status:"
echo "=================="
kubectl get pods -n $NAMESPACE
echo ""
kubectl get svc -n $NAMESPACE
echo ""
kubectl get ingress -n $NAMESPACE

echo ""
echo "Deployment complete!"
echo ""
echo "Test endpoints:"
echo "  Calculator:   https://mcp.baisoln.com/calculator/health"
echo "  Postgres:     https://mcp.baisoln.com/postgres/health"
echo "  MinIO:        https://mcp.baisoln.com/minio/health"
echo "  PDF Gen:      https://mcp.baisoln.com/pdf-generator/health"
echo "  OpenProject:  https://mcp.baisoln.com/openproject/health"
echo "  MeiliSearch:  https://mcp.baisoln.com/meilisearch/health"
echo "  GenImage:     https://mcp.baisoln.com/genimage/health"

