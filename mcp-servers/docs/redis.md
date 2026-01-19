# Redis MCP Server - Usage Guide

## Overview

The Redis MCP server provides Redis operations with multi-tenant support. Each tenant can connect to their own Redis instance, allowing you to manage multiple Redis databases through a single MCP server.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "redis-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/redis/mcp",
      "description": "Redis MCP Server - Multi-tenant Redis operations - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-redis-server

# Server will be available at http://localhost:8010
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your Redis connection details:

**Tool:** `redis_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `host` (required): Redis host address
- `port` (optional): Redis port (default: `6379`)
- `password` (optional): Redis password
- `db` (optional): Redis database number (0-15, default: `0`)
- `ssl` (optional): Use SSL/TLS connection (default: `false`)
- `decode_responses` (optional): Decode responses as strings (default: `true`)
- `max_concurrent_requests` (optional): Maximum concurrent requests per tenant (default: `100`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "host": "localhost",
  "port": 6379,
  "password": null,
  "db": 0,
  "ssl": false,
  "decode_responses": true,
  "max_concurrent_requests": 100
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `redis_register_tenant` - Register Tenant

Register a new tenant configuration with concurrency control.

**Parameters:**
- `tenant_id` (required): Unique identifier for this tenant
- `host` (required): Redis host
- `port` (optional): Redis port (default: 6379)
- `password` (optional): Redis password
- `db` (optional): Redis database number (0-15, default: 0)
- `ssl` (optional): Use SSL/TLS (default: false)
- `decode_responses` (optional): Decode responses as strings (default: true)
- `max_concurrent_requests` (optional): Maximum concurrent requests per tenant (default: 100)

### 2. `redis_get` - Get Value

Get a value from Redis by key.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `key` (required): Redis key

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "key": "user:123:name"
}
```

**Response:**
```json
{
  "success": true,
  "key": "user:123:name",
  "value": "John Doe"
}
```

### 3. `redis_set` - Set Value

Set a value in Redis with optional TTL.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `key` (required): Redis key
- `value` (required): Value to set
- `ttl` (optional): Time to live in seconds

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "key": "user:123:name",
  "value": "John Doe",
  "ttl": 3600
}
```

**Response:**
```json
{
  "success": true,
  "message": "Key 'user:123:name' set successfully"
}
```

### 4. `redis_delete` - Delete Key

Delete a key from Redis.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `key` (required): Redis key

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "key": "user:123:name"
}
```

**Response:**
```json
{
  "success": true,
  "deleted": true,
  "message": "Key 'user:123:name' deleted"
}
```

### 5. `redis_keys` - List Keys

List keys matching a pattern.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `pattern` (optional): Key pattern (default: `"*"`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "pattern": "user:*"
}
```

**Response:**
```json
{
  "success": true,
  "pattern": "user:*",
  "keys": ["user:123:name", "user:456:name"],
  "count": 2
}
```

### 6. `redis_exists` - Check Key Exists

Check if a key exists in Redis.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `key` (required): Redis key

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "key": "user:123:name"
}
```

**Response:**
```json
{
  "success": true,
  "key": "user:123:name",
  "exists": true
}
```

### 7. `redis_ttl` - Get Time to Live

Get the time to live (TTL) of a key in seconds.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `key` (required): Redis key

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "key": "user:123:name"
}
```

**Response:**
```json
{
  "success": true,
  "key": "user:123:name",
  "ttl": 3600,
  "expires_in_seconds": 3600,
  "persistent": false
}
```

### 8. `redis_info` - Get Redis Server Information

Get Redis server information.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `section` (optional): Info section (e.g., "server", "memory", "stats")

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "section": "server"
}
```

**Response:**
```json
{
  "success": true,
  "section": "server",
  "info": {
    "redis_version": "7.0.0",
    "redis_mode": "standalone",
    ...
  }
}
```

### 9. `redis_ping` - Ping Redis Server

Ping Redis server to test connection.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID

**Example:**
```json
{
  "tenant_id": "my-tenant"
}
```

**Response:**
```json
{
  "success": true,
  "pong": true
}
```

### 10. `redis_execute_command` - Execute Custom Command

Execute an arbitrary Redis command.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `command` (required): Redis command (e.g., "GET", "SET", "DEL", "KEYS", "INFO", "HGET", "HSET", etc.)
- `args` (optional): Command arguments as a list of strings

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "command": "HGET",
  "args": ["user:123", "email"]
}
```

**Response:**
```json
{
  "success": true,
  "result": "john@example.com"
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: REDIS_TENANT_{TENANT_ID}_HOST
export REDIS_TENANT_1_HOST="localhost"
export REDIS_TENANT_1_PORT="6379"
export REDIS_TENANT_1_PASSWORD=""
export REDIS_TENANT_1_DB="0"
export REDIS_TENANT_1_SSL="false"
export REDIS_TENANT_1_DECODE_RESPONSES="true"
export REDIS_TENANT_1_MAX_CONCURRENT="100"
```

## Features

- **Multi-tenant**: Each tenant connects to their own Redis instance
- **Redis persistence**: Tenant configurations persist across restarts (Redis DB 4)
- **Concurrency control**: Configurable max concurrent requests per tenant
- **Full Redis support**: All standard Redis commands via `redis_execute_command`
- **Key-value operations**: GET, SET, DELETE, EXISTS, TTL
- **Pattern matching**: List keys with pattern matching
- **Server information**: Get Redis server info and stats
- **Connection testing**: Ping endpoint for health checks

## Resources

Access tenant information as resources:

- `redis://{tenant_id}/keys` - Get list of keys for a tenant
- `redis://info` - Get information about the Redis MCP server

## Example Workflow

1. Register your tenant:
   ```
   redis_register_tenant(tenant_id="my-tenant", host="localhost", port=6379, db=0)
   ```

2. Test connection:
   ```
   redis_ping(tenant_id="my-tenant")
   ```

3. Set a value:
   ```
   redis_set(tenant_id="my-tenant", key="user:123:name", value="John Doe", ttl=3600)
   ```

4. Get a value:
   ```
   redis_get(tenant_id="my-tenant", key="user:123:name")
   ```

5. List keys:
   ```
   redis_keys(tenant_id="my-tenant", pattern="user:*")
   ```

6. Check TTL:
   ```
   redis_ttl(tenant_id="my-tenant", key="user:123:name")
   ```

7. Execute custom command:
   ```
   redis_execute_command(tenant_id="my-tenant", command="HGET", args=["user:123", "email"])
   ```

## Notes

- Tenant configurations are stored in Redis (DB 4)
- Each tenant maintains its own Redis connection
- Use `redis_execute_command` for advanced Redis operations (HASH, LIST, SET, SORTED SET operations)
- TTL values: `-1` means the key has no expiration, `-2` means the key doesn't exist
- Pattern matching supports Redis glob-style patterns (e.g., `user:*`, `*:name`, `user:?23:*`)
- The server automatically handles connection pooling and reconnection
- Use `decode_responses=true` for string responses, `false` for binary data
