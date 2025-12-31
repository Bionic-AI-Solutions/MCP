# MCP Server Template

This template provides a boilerplate for creating new multi-tenant MCP servers that can be accessed remotely.

## Quick Start

1. **Generate a new server from this template:**
   ```bash
   cd /workspace/MCP/mcp-servers
   ./template/scripts/create_new_server.sh <server-name> <port> <description>
   ```

2. **Or manually copy and customize:**
   ```bash
   cp -r template/src/mcp_servers/SERVER_NAME src/mcp_servers/<your-server-name>
   # Then replace SERVER_NAME with your actual server name throughout the files
   ```

## Template Structure

```
template/
├── src/mcp_servers/SERVER_NAME/
│   ├── __init__.py
│   ├── server.py              # Main MCP server with multi-tenant support
│   ├── tenant_manager.py      # Tenant manager with Redis persistence
│   └── client.py              # Example client code
├── docs/
│   ├── README.md              # Server-specific documentation template
│   └── SETUP.md               # Setup guide template
├── scripts/
│   └── create_new_server.sh   # Script to generate new server from template
├── examples/
│   └── example_usage.py       # Example usage code
├── docker/
│   ├── Dockerfile.snippet      # Dockerfile snippet to add to main Dockerfile
│   └── docker-compose.snippet # docker-compose snippet
├── nginx/
│   └── nginx.conf.snippet     # Nginx configuration snippet
└── README.md                  # This file
```

## Features

- ✅ Multi-tenant support with tenant isolation
- ✅ Redis persistence for tenant configurations
- ✅ Docker containerization
- ✅ Remote access via HTTP/HTTPS
- ✅ Health checks
- ✅ Environment variable configuration
- ✅ Proper import handling (works in Docker and local)
- ✅ Type hints and validation with Pydantic

## Customization Steps

1. **Replace SERVER_NAME** with your actual server name in all files
2. **Update tenant configuration** in `tenant_manager.py` to match your service needs
3. **Implement your tools** in `server.py`
4. **Add dependencies** to `pyproject.toml` if needed
5. **Update Docker configuration** with your server's port and dependencies
6. **Add nginx configuration** for remote access
7. **Update documentation** with your server-specific details

## Port Assignment

Default ports:
- Calculator: 8000
- Postgres: 8001
- MinIO: 8002
- **Next available: 8003**

When creating a new server, use the next available port or specify your own.

## Integration Checklist

- [ ] Copy server code to `src/mcp_servers/<server-name>/`
- [ ] Add Docker stage to `Dockerfile`
- [ ] Add service to `docker-compose.yml`
- [ ] Add nginx configuration to `nginx.conf`
- [ ] Update `pyproject.toml` with dependencies
- [ ] Update `mcp_client_config_cursor_remote.json` with new server URL
- [ ] Test locally
- [ ] Test via remote URL
- [ ] Update documentation

