# Redis Persistence for Tenant Configurations

## Overview

Both Postgres and MinIO MCP servers now use Redis to persist tenant configurations across server restarts. This ensures that tenants registered programmatically via the `register_tenant` tool are not lost when the server restarts.

## Architecture

### Storage Structure

- **Postgres tenants**: Stored in Redis DB 0 with key prefix `mcp:postgres:tenant:{tenant_id}`
- **MinIO tenants**: Stored in Redis DB 1 with key prefix `mcp:minio:tenant:{tenant_id}`

### Data Format

Tenant configurations are stored as JSON strings in Redis, containing all tenant connection parameters.

## Configuration

### Environment Variables

Both servers use the following environment variables for Redis connection:

- `REDIS_HOST`: Redis hostname (default: `redis`)
- `REDIS_PORT`: Redis port (default: `6379`)
- `REDIS_DB`: Redis database number
  - Postgres: `0` (default)
  - MinIO: `1` (default)
- `REDIS_PASSWORD`: Optional Redis password

### Docker Compose

The `docker-compose.yml` already includes Redis service and configures both servers with Redis environment variables:

```yaml
redis:
  image: redis:7-alpine
  container_name: mcp-redis
  ports:
    - "6379:6379"
  volumes:
    - redis-data:/data
  command: redis-server --appendonly yes
  # ... health checks and network config
```

## Behavior

### Startup Sequence

1. **Server starts** → Lifespan function executes
2. **Initialize Redis connection** → Connect to Redis (with graceful fallback if unavailable)
3. **Load from Redis** → Load all tenant configurations from Redis
4. **Load from Environment** → Load any tenants configured via environment variables (takes precedence)
5. **Register tenants** → Create connection pools/clients for all loaded tenants

### Tenant Registration

When a tenant is registered via the `register_tenant` tool:

1. **Create connection pool/client** → Establish connection to the database/storage
2. **Store in memory** → Keep in `self.configs` dictionary for fast access
3. **Persist to Redis** → Save configuration to Redis for durability

### Tenant Lookup Priority

When a tenant is requested:

1. **Check memory** → If already loaded, use it
2. **Load from Redis** → If not in memory, try loading from Redis
3. **Load from Environment** → If not in Redis, try loading from environment variables
4. **Error** → If none found, raise an error

## Graceful Degradation

If Redis is unavailable:

- The server will continue to operate normally
- A warning message will be logged
- Tenants can still be loaded from environment variables
- Programmatically registered tenants will be lost on restart (but will work during the session)

## Security Considerations

⚠️ **Important**: Tenant configurations stored in Redis contain sensitive information:

- **Postgres**: Database passwords are stored in plain text
- **MinIO**: Access keys and secret keys are stored in plain text

### Recommendations for Production

1. **Encrypt sensitive fields** before storing in Redis
2. **Use Redis AUTH** (password protection)
3. **Enable Redis TLS** for encrypted connections
4. **Restrict Redis network access** to only the MCP servers
5. **Consider using a secrets management system** (e.g., HashiCorp Vault) for production

## Testing

To test Redis persistence:

1. **Start the servers**:
   ```bash
   cd /workspace/MCP/mcp-servers
   docker-compose up -d
   ```

2. **Register a tenant** via the MCP `register_tenant` tool

3. **Restart the server**:
   ```bash
   docker-compose restart mcp-postgres-server-new
   # or
   docker-compose restart mcp-minio-server-new
   ```

4. **Verify tenant is still available** after restart

## Monitoring

You can inspect Redis directly to see stored tenant configurations:

```bash
# Connect to Redis
docker exec -it mcp-redis redis-cli

# List all Postgres tenant keys
KEYS mcp:postgres:tenant:*

# List all MinIO tenant keys
SELECT 1
KEYS mcp:minio:tenant:*

# View a specific tenant configuration
GET mcp:postgres:tenant:tenant1
```

## Troubleshooting

### Redis Connection Issues

If you see warnings about Redis not being available:

1. **Check Redis is running**:
   ```bash
   docker-compose ps redis
   ```

2. **Check Redis logs**:
   ```bash
   docker-compose logs redis
   ```

3. **Verify network connectivity**:
   ```bash
   docker exec -it mcp-postgres-server-new ping redis
   ```

### Tenant Not Persisting

If tenants are lost after restart:

1. **Check Redis is accessible** from the server container
2. **Verify tenant was saved**:
   ```bash
   docker exec -it mcp-redis redis-cli GET mcp:postgres:tenant:YOUR_TENANT_ID
   ```
3. **Check server logs** for initialization errors

## Implementation Details

### PostgresTenantManager

- **File**: `src/mcp_servers/postgres/tenant_manager.py`
- **Redis DB**: 0
- **Key Pattern**: `mcp:postgres:tenant:{tenant_id}`
- **Methods**:
  - `_init_redis()`: Initialize Redis connection
  - `_save_to_redis()`: Save tenant config to Redis
  - `_load_from_redis()`: Load tenant config from Redis
  - `_load_all_from_redis()`: Load all tenant configs from Redis
  - `initialize()`: Load all tenants on startup
  - `register_tenant()`: Register and persist tenant

### MinioTenantManager

- **File**: `src/mcp_servers/minio/tenant_manager.py`
- **Redis DB**: 1
- **Key Pattern**: `mcp:minio:tenant:{tenant_id}`
- **Methods**: Same as PostgresTenantManager


