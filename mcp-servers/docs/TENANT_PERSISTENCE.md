# Tenant Configuration Persistence

## Storage Location

Tenant configurations for the Postgres MCP server are stored in **Redis** with the following key pattern:

```
mcp:postgres:tenant:<tenant_id>
```

For example, the `fedfina` tenant is stored at:
```
mcp:postgres:tenant:fedfina
```

## How It Works

1. **Registration**: When you register a tenant using `register_tenant`, the configuration is:
   - Stored in Redis (persistent storage)
   - Loaded into memory (connection pools)

2. **Server Startup**: When the MCP server starts, it:
   - Automatically loads all tenant configurations from Redis
   - Recreates connection pools for each tenant
   - This happens in the `initialize()` method during server lifespan

3. **Server Restart**: When the MCP server pod restarts:
   - ✅ **Tenant configurations WILL persist** (stored in Redis)
   - ✅ **Connection pools will be automatically recreated** from Redis data
   - ✅ **No need to re-register tenants**

## Current Persistence Status

### ✅ MCP Server Restarts
- ✅ **Tenant configs persist** - Stored in Redis
- ✅ **Auto-reload on startup** - Server loads from Redis automatically

### ⚠️ Redis Pod Restarts
- ⚠️ **Current setup**: Redis uses `emptyDir` volume
- ⚠️ **Data is lost** if Redis pod is deleted/recreated
- ⚠️ **Redis has AOF enabled** (`--appendonly yes`) but data is in memory/emptyDir

### Recommendations

For **production use**, consider:

1. **Add PersistentVolume for Redis**:
   ```yaml
   volumes:
     - name: redis-data
       persistentVolumeClaim:
         claimName: redis-pvc
   ```

2. **Or use a managed Redis service** (AWS ElastiCache, Redis Cloud, etc.)

3. **Current setup is fine for development** - tenant configs persist across MCP server restarts

## Verification

To verify tenant persistence:

```bash
# Check Redis directly
kubectl exec -n mcp <redis-pod> -- redis-cli KEYS "mcp:postgres:tenant:*"

# Restart MCP server and verify tenants are still available
kubectl rollout restart deployment -n mcp mcp-postgres-server
# Wait for pod to be ready, then test:
curl https://mcp.baisoln.com/postgres/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_tables","arguments":{"tenant_id":"fedfina"}},"id":1}'
```

## Code Reference

- **Storage**: `src/mcp_servers/postgres/tenant_manager.py`
  - `_save_to_redis()` - Saves tenant config to Redis
  - `_load_from_redis()` - Loads tenant config from Redis
  - `_load_all_from_redis()` - Loads all tenants on startup
  - `initialize()` - Called on server startup to load all tenants

- **Server Startup**: `src/mcp_servers/postgres/server.py`
  - `lifespan()` function calls `tenant_manager.initialize()` on startup


