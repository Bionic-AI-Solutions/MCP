# SERVER_NAME MCP Server

[Description of what this server does]

## Features

- Multi-tenant support with tenant isolation
- Redis persistence for tenant configurations
- [List your server-specific features]

## Tools

### `example_tool`
- **Description**: [What this tool does]
- **Parameters**:
  - `tenant_id` (str, required): Tenant identifier
  - [Add other parameters]
- **Returns**: [Return value description]

### `register_tenant`
- **Description**: Register a new tenant configuration
- **Parameters**:
  - `tenant_id` (str, required): Unique tenant identifier
  - [Add your tenant configuration parameters]
- **Returns**: Success message

## Resources

- **`SERVER_NAME://{tenant_id}/info`** - Get information about a tenant
- **`SERVER_NAME://info`** - Get information about the server

## Configuration

### Environment Variables

```bash
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Tenant Configuration (optional - can also register programmatically)
SERVER_NAME_TENANT_1_API_KEY=your_api_key
SERVER_NAME_TENANT_1_API_URL=https://api.example.com
```

### Registering Tenants

#### Via Environment Variables
Set environment variables with the pattern:
```
SERVER_NAME_TENANT_{TENANT_ID}_{CONFIG_KEY}=value
```

#### Via MCP Tool
```python
await client.call_tool(
    "register_tenant",
    {
        "tenant_id": "my-tenant",
        # Add your configuration parameters
    }
)
```

## Usage Examples

See `examples/example_usage.py` for complete examples.

## Docker Deployment

The server runs in a Docker container and is accessible via:
- **Local**: `http://localhost:PORT_NUMBER/mcp`
- **Remote**: `https://mcp.bionicaisolutions.com/SERVER_NAME/mcp`

## Development

### Local Development
```bash
cd /workspace/MCP/mcp-servers
.venv/bin/fastmcp run src/mcp_servers/SERVER_NAME/server.py
```

### Docker Development
```bash
cd /workspace/MCP/mcp-servers
docker compose up -d mcp-SERVER_NAME-server
docker compose logs -f mcp-SERVER_NAME-server
```

## Troubleshooting

### Tenant Not Found
- Verify tenant is registered in Redis: `docker exec mcp-redis redis-cli GET "mcp:SERVER_NAME:tenant:{tenant_id}"`
- Check server logs: `docker logs mcp-SERVER_NAME-server`

### Connection Issues
- Verify Redis is running: `docker ps | grep redis`
- Check network connectivity: `docker network inspect mcp-servers_mcp-network`

