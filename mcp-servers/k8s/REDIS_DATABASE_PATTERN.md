# Redis Database Numbering Pattern for MCP Servers

## Overview

All multi-tenant MCP servers use Redis for persistent tenant configuration storage. To avoid conflicts, each server uses a **unique Redis database number** (0-15, as Redis supports 16 databases by default).

## Database Assignment

| Server Name | Redis DB | Port | Purpose |
|------------|----------|------|---------|
| postgres | 0 | 8001 | PostgreSQL tenant configurations |
| minio | 1 | 8002 | MinIO tenant configurations |
| pdf-generator | 2 | 8003 | PDF Generator tenant configurations |
| calculator | N/A | 8000 | Stateless, no Redis needed |

## Adding a New Multi-Tenant Server

When creating a new multi-tenant MCP server:

1. **Check available database numbers**: Review this document to find the next available number
2. **Update this table**: Add your server with the assigned database number
3. **Configure in deployment**: Set `REDIS_DB` in the ConfigMap to your assigned number
4. **Document in template**: Update the template deployment.yaml with the pattern

## Redis Configuration

### Connection Settings

All servers use the same Redis instance with these standard settings:

```yaml
REDIS_HOST: "redis"  # Service name in mcp namespace
REDIS_PORT: "6379"
REDIS_DB: "<ASSIGNED_NUMBER>"  # Unique per server
```

### Storage Pattern

Tenant configurations are stored with this key pattern:

```
mcp:<server-name>:tenant:<tenant-id>
```

Examples:
- `mcp:postgres:tenant:fedfina` (in Redis DB 0)
- `mcp:minio:tenant:my-tenant` (in Redis DB 1)
- `mcp:pdf-generator:tenant:client-1` (in Redis DB 2)

## Redis Persistence

The Redis instance uses a **PersistentVolumeClaim** (`redis-data-pvc`) to ensure tenant data persists across Redis pod restarts.

### Storage Details

- **PVC Name**: `redis-data-pvc`
- **Namespace**: `mcp`
- **Storage Size**: 10Gi
- **Access Mode**: ReadWriteOnce
- **Redis Persistence**: AOF (Append Only File) enabled

### Data Persistence Guarantees

✅ **MCP Server Restart**: Tenant data persists (loaded from Redis on startup)  
✅ **Redis Pod Restart**: Tenant data persists (stored in PVC)  
✅ **Cluster Restart**: Tenant data persists (PVC survives cluster restarts)

## Template Usage

When using the template to create a new server:

1. Copy `template/k8s/deployment.yaml` to `k8s/<server-name>/deployment.yaml`
2. Replace placeholders:
   - `<SERVER_NAME>` → your server name (lowercase, kebab-case)
   - `<SERVER_DISPLAY_NAME>` → display name
   - `<PORT_NUMBER>` → unique port (8000-8999)
   - `<REDIS_DB_NUMBER>` → next available Redis DB number
3. Add server-specific configuration to ConfigMap
4. Add tenant configuration environment variables if needed
5. Update `kustomization.yaml` to include the new deployment

## Verification

To verify Redis database assignments:

```bash
# Check tenant data in a specific database
kubectl exec -n mcp redis-<pod-name> -- redis-cli -n <DB_NUMBER> KEYS "mcp:*"

# Example: Check postgres tenants (DB 0)
kubectl exec -n mcp redis-<pod-name> -- redis-cli -n 0 KEYS "mcp:postgres:*"

# Example: Check minio tenants (DB 1)
kubectl exec -n mcp redis-<pod-name> -- redis-cli -n 1 KEYS "mcp:minio:*"
```

## Best Practices

1. **Always use unique database numbers** - Never reuse a number
2. **Document assignments** - Keep this file updated
3. **Test persistence** - Verify tenant data survives Redis restarts
4. **Monitor storage** - Check PVC usage as tenant count grows
5. **Backup strategy** - Consider backing up Redis data for disaster recovery

