#!/bin/bash
# Fix service selectors after kustomize apply
# Kustomize commonLabels adds labels to service selectors that pods don't have
# This script patches services to only match on the 'app' label

set -e

NAMESPACE="${NAMESPACE:-mcp}"

echo "Fixing service selectors in namespace '$NAMESPACE'..."

for svc in calculator postgres minio ffmpeg pdf-generator genimage; do
  echo "Patching mcp-$svc-server..."
  kubectl patch svc mcp-$svc-server -n "$NAMESPACE" --type=json \
    -p='[{"op": "replace", "path": "/spec/selector", "value": {"app": "mcp-'$svc'-server"}}]' && \
    echo "✓ Fixed mcp-$svc-server" || echo "✗ Failed to patch mcp-$svc-server"
done

echo ""
echo "Verifying endpoints..."
kubectl get endpoints -n "$NAMESPACE" | grep -E "(calculator|postgres|minio|ffmpeg|pdf-generator|genimage)"

echo ""
echo "Done! All service selectors have been fixed."
