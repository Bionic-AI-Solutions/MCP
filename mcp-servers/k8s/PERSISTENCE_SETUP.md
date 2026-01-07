# Redis Persistence Setup for MCP Servers

## Overview

This document describes the Redis persistence configuration for the MCP namespace, ensuring tenant configurations persist across Redis pod restarts.

## What Was Changed

### 1. Redis PersistentVolumeClaim

**File**: `k8s/redis-pvc.yaml`

Created a PersistentVolumeClaim (PVC) for Redis data storage:
- **Name**: `redis-data-pvc`
- **Namespace**: `mcp`
- **Storage Size**: 10Gi
- **Access Mode**: ReadWriteOnce
- **Storage Class**: Configurable (commented out for cluster defaults)

### 2. Redis Deployment Update

**File**: `k8s/redis-service.yaml`

Updated Redis deployment to use PVC instead of `emptyDir`:
- Changed from `emptyDir: {}` to `persistentVolumeClaim: { claimName: redis-data-pvc }`
- Redis AOF (Append Only File) persistence already enabled
- Data now persists across Redis pod restarts

### 3. Kustomization Update

**File**: `k8s/kustomization.yaml`

Added `redis-pvc.yaml` to the resources list to ensure PVC is created before Redis deployment.

### 4. Template for New Servers

**File**: `template/k8s/deployment.yaml`

Created a Kubernetes deployment template that includes:
- Redis configuration pattern with database numbering
- Placeholder comments explaining the Redis DB assignment
- Standard structure for ConfigMap, Deployment, Service, and optional Secrets

### 5. Documentation

Created comprehensive documentation:
- **`k8s/REDIS_DATABASE_PATTERN.md`**: Database numbering pattern and best practices
- **`k8s/README.md`**: Complete Kubernetes deployment guide
- **`template/INTEGRATION_GUIDE.md`**: Updated with Kubernetes deployment steps

## Redis Database Pattern

Each multi-tenant MCP server uses a unique Redis database number:

| Server | Redis DB | Port | Status |
|--------|----------|------|--------|
| postgres | 0 | 8001 | ✅ Configured |
| minio | 1 | 8002 | ✅ Configured |
| pdf-generator | 2 | 8003 | ✅ Configured |
| calculator | N/A | 8000 | Stateless (no Redis) |

**Next available**: DB 3

## Persistence Guarantees

### Before (emptyDir)
- ❌ Redis pod restart: Data lost
- ✅ MCP server restart: Data persisted (loaded from Redis)

### After (PVC)
- ✅ Redis pod restart: Data persists
- ✅ MCP server restart: Data persists (loaded from Redis)
- ✅ Cluster restart: Data persists (PVC survives)

## Deployment

### Apply Changes

```bash
# Apply all manifests (including new PVC)
kubectl apply -k k8s/

# Verify PVC is created and bound
kubectl get pvc -n mcp redis-data-pvc

# Verify Redis pod is using the PVC
kubectl describe pod -n mcp -l app=redis | grep -A 5 "Mounts"
```

### Verify Persistence

```bash
# Get Redis pod name
REDIS_POD=$(kubectl get pods -n mcp -l app=redis -o jsonpath='{.items[0].metadata.name}')

# Check tenant data exists
kubectl exec -n mcp $REDIS_POD -- redis-cli -n 0 KEYS "mcp:postgres:*"
kubectl exec -n mcp $REDIS_POD -- redis-cli -n 1 KEYS "mcp:minio:*"
kubectl exec -n mcp $REDIS_POD -- redis-cli -n 2 KEYS "mcp:pdf-generator:*"

# Restart Redis pod
kubectl delete pod -n mcp $REDIS_POD

# Wait for new pod
kubectl wait --for=condition=ready pod -n mcp -l app=redis --timeout=60s

# Verify data still exists
NEW_REDIS_POD=$(kubectl get pods -n mcp -l app=redis -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n mcp $NEW_REDIS_POD -- redis-cli -n 0 KEYS "mcp:postgres:*"
```

## Storage Configuration

### Default Configuration

The PVC uses the cluster's default storage class. For most clusters, this will automatically provision persistent storage.

### Custom Storage Class

If your cluster requires a specific storage class, uncomment and set it in `k8s/redis-pvc.yaml`:

```yaml
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd  # or your storage class name
  resources:
    requests:
      storage: 10Gi
```

### Local Development

For local development (e.g., k3d, minikube), you may need to use a local-path storage class:

```yaml
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
```

## Adding a New Multi-Tenant Server

When creating a new multi-tenant MCP server:

1. **Copy template**:
   ```bash
   mkdir -p k8s/<server-name>
   cp template/k8s/deployment.yaml k8s/<server-name>/deployment.yaml
   ```

2. **Assign Redis DB number**:
   - Check `k8s/REDIS_DATABASE_PATTERN.md` for next available number
   - Update `REDIS_DB` in ConfigMap
   - Document assignment in `REDIS_DATABASE_PATTERN.md`

3. **Deploy**:
   ```bash
   kubectl apply -k k8s/
   ```

## Troubleshooting

### PVC Not Binding

```bash
# Check PVC status
kubectl get pvc -n mcp redis-data-pvc

# Check events
kubectl describe pvc -n mcp redis-data-pvc

# Check available storage classes
kubectl get storageclass

# If no default storage class, set one explicitly in redis-pvc.yaml
```

### Redis Pod Can't Mount PVC

```bash
# Check pod events
kubectl describe pod -n mcp -l app=redis

# Verify PVC exists and is bound
kubectl get pvc -n mcp redis-data-pvc

# Check storage class compatibility
kubectl get pv
```

### Data Not Persisting

```bash
# Verify AOF is enabled
kubectl exec -n mcp <redis-pod> -- redis-cli CONFIG GET appendonly

# Should return: 1) "appendonly" 2) "yes"

# Check if data directory is mounted
kubectl exec -n mcp <redis-pod> -- ls -la /data

# Should show appendonly.aof file
```

## Best Practices

1. **Monitor Storage Usage**: Check PVC usage as tenant count grows
   ```bash
   kubectl describe pvc -n mcp redis-data-pvc
   ```

2. **Backup Strategy**: Consider backing up Redis data for disaster recovery
   ```bash
   # Export Redis data
   kubectl exec -n mcp <redis-pod> -- redis-cli --rdb /tmp/dump.rdb
   kubectl cp mcp/<redis-pod>:/tmp/dump.rdb ./redis-backup-$(date +%Y%m%d).rdb
   ```

3. **Storage Scaling**: If needed, increase PVC size (may require storage class support)
   ```bash
   kubectl patch pvc redis-data-pvc -n mcp -p '{"spec":{"resources":{"requests":{"storage":"20Gi"}}}}'
   ```

4. **Database Isolation**: Always use unique Redis DB numbers per server

## Related Documentation

- [Redis Database Pattern](./REDIS_DATABASE_PATTERN.md)
- [Kubernetes Deployment Guide](./README.md)
- [Template Integration Guide](../template/INTEGRATION_GUIDE.md)















