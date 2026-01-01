# Kubernetes Deployment for MCP Servers

This directory contains Kubernetes manifests for deploying MCP servers to a Kubernetes cluster.

## Structure

```
k8s/
├── namespace.yaml              # mcp namespace definition
├── redis-pvc.yaml              # Redis persistent volume claim
├── redis-service.yaml          # Redis deployment and service
├── kustomization.yaml          # Kustomize configuration
├── REDIS_DATABASE_PATTERN.md   # Redis DB numbering pattern
├── calculator/                 # Calculator server manifests
│   └── deployment.yaml
├── postgres/                   # Postgres server manifests
│   └── deployment.yaml
├── minio/                      # MinIO server manifests
│   └── deployment.yaml
├── pdf-generator/              # PDF Generator server manifests
│   └── deployment.yaml
└── kong/                       # Kong ingress routes
    ├── calculator-routes.yaml
    ├── postgres-routes.yaml
    ├── minio-routes.yaml
    └── pdf-generator-routes.yaml
```

## Prerequisites

1. **Kubernetes cluster** with:
   - kubectl configured
   - Storage class for PVCs (or use `local-path` for local development)
   - Kong Ingress Controller installed
   - cert-manager installed (for TLS certificates)

2. **Docker Hub credentials**:
   - Create a secret named `dockerhub-pull-secret` in the `mcp` namespace
   ```bash
   kubectl create secret docker-registry dockerhub-pull-secret \
     --docker-server=https://index.docker.io/v1/ \
     --docker-username=<username> \
     --docker-password=<pat-token> \
     --namespace=mcp
   ```

3. **Image pull secret**:
   - Ensure images are pushed to Docker Hub: `docker.io/docker4zerocool/mcp-servers-*`

## Redis Persistence

All multi-tenant MCP servers use Redis for tenant configuration storage. Redis is configured with:

- **PersistentVolumeClaim**: `redis-data-pvc` (10Gi storage)
- **AOF Persistence**: Enabled for data durability
- **Database Isolation**: Each server uses a unique Redis database number

See `REDIS_DATABASE_PATTERN.md` for database assignments and best practices.

## Deployment

### Deploy All Resources

```bash
# Apply all manifests using Kustomize
kubectl apply -k k8s/

# Verify deployment
kubectl get all -n mcp
```

### Deploy Individual Server

```bash
# Apply specific server
kubectl apply -f k8s/<server-name>/deployment.yaml

# Check status
kubectl get pods -n mcp -l app=mcp-<server-name>-server
```

## Redis Database Pattern

Each multi-tenant server uses a unique Redis database:

| Server | Redis DB | Port |
|--------|----------|------|
| postgres | 0 | 8001 |
| minio | 1 | 8002 |
| pdf-generator | 2 | 8003 |

When adding a new server, assign the next available database number and document it in `REDIS_DATABASE_PATTERN.md`.

## Verification

### Check Pod Status

```bash
# All pods in mcp namespace
kubectl get pods -n mcp

# Specific server
kubectl get pods -n mcp -l app=mcp-<server-name>-server
```

### Check Redis Persistence

```bash
# Get Redis pod name
REDIS_POD=$(kubectl get pods -n mcp -l app=redis -o jsonpath='{.items[0].metadata.name}')

# Check tenant data in specific database
kubectl exec -n mcp $REDIS_POD -- redis-cli -n <DB_NUMBER> KEYS "mcp:*"

# Example: Check postgres tenants (DB 0)
kubectl exec -n mcp $REDIS_POD -- redis-cli -n 0 KEYS "mcp:postgres:*"
```

### Check PVC Status

```bash
# Verify Redis PVC is bound
kubectl get pvc -n mcp redis-data-pvc

# Check storage usage
kubectl describe pvc -n mcp redis-data-pvc
```

### Test Server Endpoints

```bash
# Health check
curl https://mcp.baisoln.com/<server-name>/health

# MCP initialize
curl -X POST https://mcp.baisoln.com/<server-name>/mcp \
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

### Pod Not Starting

```bash
# Check pod logs
kubectl logs -n mcp <pod-name>

# Check pod events
kubectl describe pod -n mcp <pod-name>

# Check image pull
kubectl get events -n mcp --sort-by='.lastTimestamp' | grep <pod-name>
```

### Redis Connection Issues

```bash
# Verify Redis is running
kubectl get pods -n mcp -l app=redis

# Test Redis connectivity from server pod
kubectl exec -n mcp <server-pod> -- nc -zv redis 6379

# Check Redis logs
kubectl logs -n mcp -l app=redis
```

### PVC Not Binding

```bash
# Check PVC status
kubectl get pvc -n mcp

# Check storage class
kubectl get storageclass

# For local development, you may need to create a local-path storage class
```

### Tenant Data Not Persisting

```bash
# Verify Redis persistence is enabled
kubectl exec -n mcp <redis-pod> -- redis-cli CONFIG GET appendonly

# Check if data exists in Redis
kubectl exec -n mcp <redis-pod> -- redis-cli -n <DB_NUMBER> KEYS "*"

# Verify PVC is mounted
kubectl describe pod -n mcp <redis-pod> | grep -A 5 "Mounts"
```

## Adding a New Server

1. **Copy template**:
   ```bash
   mkdir -p k8s/<server-name>
   cp template/k8s/deployment.yaml k8s/<server-name>/deployment.yaml
   ```

2. **Update placeholders** in `k8s/<server-name>/deployment.yaml`

3. **Assign Redis DB number** (see `REDIS_DATABASE_PATTERN.md`)

4. **Add to kustomization.yaml**:
   ```yaml
   resources:
     - <server-name>/deployment.yaml
   ```

5. **Create Kong routes** (see `kong/` directory for examples)

6. **Deploy and verify**

## Resources

- [Redis Database Pattern](./REDIS_DATABASE_PATTERN.md)
- [Template Integration Guide](../template/INTEGRATION_GUIDE.md)
- [Deployment Summary](./DEPLOYMENT_SUMMARY.md)
