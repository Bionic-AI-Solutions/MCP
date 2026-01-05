# Quick Start Guide - MCP Servers Kubernetes Deployment

## Prerequisites Checklist

- [ ] Kubernetes cluster (1.24+) with kubectl configured
- [ ] Kong Ingress Controller installed
- [ ] Docker registry access (to push images)
- [ ] DNS configured: `mcp.baisoln.com` → Kong Gateway IP

## Step 1: Build Docker Images

```bash
cd /home/skadam/git/MCP/mcp-servers

# Set your registry details
export IMAGE_REGISTRY="your-registry.io"  # e.g., docker.io/your-org, harbor.example.com
export IMAGE_NAME="mcp-servers"
export IMAGE_TAG="latest"

# Build all images
./k8s/build-images.sh

# Push to registry
PUSH_IMAGES=true ./k8s/build-images.sh
```

## Step 2: Update Image References

Edit `k8s/kustomization.yaml` and update the image references:

```yaml
images:
  - name: mcp-servers-calculator
    newName: your-registry.io/mcp-servers-calculator
    newTag: latest
  # ... update others similarly
```

Or use kustomize commands:

```bash
cd k8s
kustomize edit set image mcp-servers-calculator=your-registry.io/mcp-servers-calculator:latest
kustomize edit set image mcp-servers-postgres=your-registry.io/mcp-servers-postgres:latest
kustomize edit set image mcp-servers-minio=your-registry.io/mcp-servers-minio:latest
kustomize edit set image mcp-servers-pdf-generator=your-registry.io/mcp-servers-pdf-generator:latest
```

## Step 3: Configure Secrets (Optional)

Update tenant secrets if needed:

```bash
# Postgres secrets
kubectl create secret generic mcp-postgres-secrets \
  --from-literal=tenant-1-host=your-postgres-host \
  --from-literal=tenant-1-port=5432 \
  --from-literal=tenant-1-db=your-database \
  --from-literal=tenant-1-user=postgres \
  --from-literal=tenant-1-password=your-password \
  --namespace=mcp \
  --dry-run=client -o yaml | kubectl apply -f -

# MinIO secrets
kubectl create secret generic mcp-minio-secrets \
  --from-literal=tenant-1-endpoint=your-minio-endpoint \
  --from-literal=tenant-1-access-key=your-access-key \
  --from-literal=tenant-1-secret-key=your-secret-key \
  --namespace=mcp \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Step 4: Deploy

```bash
# Using the deployment script
export IMAGE_REGISTRY="your-registry.io"
export IMAGE_NAME="mcp-servers"
export IMAGE_TAG="latest"
./k8s/deploy.sh

# Or using kubectl directly
kubectl apply -k k8s/
```

## Step 5: Verify Deployment

```bash
# Check pods
kubectl get pods -n mcp

# Check services
kubectl get svc -n mcp

# Check ingress
kubectl get ingress -n mcp

# Check logs
kubectl logs -n mcp -l app=mcp-calculator-server
```

## Step 6: Test Endpoints

```bash
# Health checks
curl https://mcp.baisoln.com/calculator/health
curl https://mcp.baisoln.com/postgres/health
curl https://mcp.baisoln.com/minio/health
curl https://mcp.baisoln.com/pdf-generator/health

# MCP Protocol test
curl -X POST https://mcp.baisoln.com/calculator/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0"
      }
    },
    "id": 1
  }'
```

## Troubleshooting

### Pods not starting
```bash
kubectl describe pod <pod-name> -n mcp
kubectl logs <pod-name> -n mcp
```

### Image pull errors
- Verify image exists in registry
- Check image pull secrets if using private registry
- Verify image name and tag in kustomization.yaml

### Ingress not working
```bash
# Check Kong pods
kubectl get pods -n kong

# Check ingress status
kubectl describe ingress -n mcp

# Check Kong routes (if Kong Admin API accessible)
kubectl port-forward -n kong svc/kong-admin 8001:8001
curl http://localhost:8001/routes
```

## Available Endpoints

All servers are accessible at:
- **HTTP Protocol**: `https://mcp.baisoln.com/<server-name>/mcp`
- **SSE Protocol**: `https://mcp.baisoln.com/<server-name>/sse`
- **Health Check**: `https://mcp.baisoln.com/<server-name>/health`

Where `<server-name>` is one of:
- `calculator`
- `postgres`
- `minio`
- `pdf-generator`








