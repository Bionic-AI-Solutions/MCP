# MCP Server Template Overview

This template provides a complete boilerplate for creating new multi-tenant MCP servers that can be accessed remotely.

## What's Included

### Core Server Files
- **`server.py`** - Main MCP server with FastMCP, multi-tenant support, tools, and resources
- **`tenant_manager.py`** - Tenant manager with Redis persistence, environment variable support
- **`client.py`** - Example client code showing how to use the server
- **`__init__.py`** - Package initialization

### Configuration Templates
- **`Dockerfile.snippet`** - Docker stage to add to main Dockerfile
- **`docker-compose.snippet`** - Service definition to add to docker-compose.yml
- **`nginx.conf.snippet`** - Nginx location blocks for remote access

### Documentation
- **`README.md`** - Main template documentation
- **`QUICK_START.md`** - Quick start guide
- **`INTEGRATION_GUIDE.md`** - Step-by-step integration instructions
- **`docs/README.md`** - Server-specific documentation template
- **`docs/SETUP.md`** - Setup guide template

### Scripts
- **`create_new_server.sh`** - Automated script to generate new servers from template

### Examples
- **`example_usage.py`** - Example usage code

## Key Features

### Multi-Tenant Support
- Each tenant has isolated configuration
- Tenant-specific clients/connections
- Automatic tenant loading from Redis on startup

### Redis Persistence
- Tenant configurations persisted in Redis
- Survives container restarts
- Environment variable fallback

### Remote Access
- HTTP transport for remote access
- Nginx configuration for HTTPS
- Session management support

### Docker Integration
- Multi-stage Docker builds
- Health checks
- Network configuration
- Environment variable support

### Import Handling
- Works in both Docker and local environments
- Try/except pattern for imports
- Proper PYTHONPATH configuration

## Template Variables

When using the template, replace:
- `SERVER_NAME` - Your server name (lowercase, kebab-case)
- `Server Name Server` - Your server display name
- `PORT_NUMBER` - Your server's port (8003, 8004, etc.)
- `REDIS_DB_NUMBER` - Unique Redis DB number
- `[DESCRIPTION]` - Description of what your server does

## Usage Patterns

### Pattern 1: API Service
- Tenant config: API key, API URL, timeout
- Client: HTTP client (httpx, requests)
- Tools: API operations (GET, POST, etc.)

### Pattern 2: Database Service
- Tenant config: Host, port, database, credentials
- Client: Database connection pool
- Tools: Query execution, schema operations

### Pattern 3: Storage Service
- Tenant config: Endpoint, credentials, region
- Client: Storage client (S3, MinIO, etc.)
- Tools: Upload, download, list operations

## Customization Points

1. **Tenant Configuration** (`tenant_manager.py`)
   - Define your config model
   - Implement client creation
   - Add environment variable loading

2. **Tools** (`server.py`)
   - Implement your business logic
   - Add request/response models
   - Define tool parameters

3. **Resources** (`server.py`)
   - Add resource endpoints
   - Define resource schemas

4. **Dependencies** (`pyproject.toml`)
   - Add service-specific libraries
   - Update system dependencies in Dockerfile

## Best Practices

1. **Always use try/except for imports** - Ensures compatibility
2. **Return Dict[str, Any] for tools** - Allows flexible return types
3. **Use Pydantic models** - Type safety and validation
4. **Log with Context** - Better debugging
5. **Handle errors gracefully** - Return error messages, don't crash
6. **Test locally first** - Before Docker deployment
7. **Use Redis DB isolation** - Different DB per service
8. **Document your tools** - Clear descriptions help users

## Common Customizations

### Adding a New Tool
```python
@mcp.tool
async def my_tool(
    tenant_id: str,
    param1: str,
    param2: int = 10,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Tool description."""
    if ctx:
        await ctx.info(f"Executing my_tool for tenant: {tenant_id}")
    
    client = await tenant_manager.get_client(tenant_id)
    # Your logic here
    
    return {"success": True, "result": "..."}
```

### Adding a New Resource
```python
@mcp.resource("SERVER_NAME://{tenant_id}/data")
async def get_data_resource(tenant_id: str) -> str:
    """Get data for a tenant."""
    # Your logic here
    return json.dumps({"data": "..."}, indent=2)
```

### Custom Tenant Configuration
```python
class MyServiceTenantConfig(BaseModel):
    tenant_id: str
    api_key: str
    api_url: str
    timeout: int = 30
    retry_count: int = 3
```

## Testing Your Server

1. **Local Testing:**
   ```bash
   .venv/bin/fastmcp run src/mcp_servers/<server-name>/server.py
   ```

2. **Docker Testing:**
   ```bash
   docker compose build mcp-<server-name>-server
   docker compose up -d mcp-<server-name>-server
   docker compose logs -f mcp-<server-name>-server
   ```

3. **MCP Client Testing:**
   ```python
   from fastmcp import Client
   async with Client("src/mcp_servers/<server-name>/server.py") as client:
       # Test your tools
   ```

## Support

For questions or issues:
1. Check the integration guide
2. Review existing servers (postgres, minio) as examples
3. Check server logs: `docker compose logs mcp-<server-name>-server`

