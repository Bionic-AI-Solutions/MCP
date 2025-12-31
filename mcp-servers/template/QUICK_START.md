# Quick Start: Creating a New MCP Server

This is the fastest way to create a new multi-tenant MCP server.

## Option 1: Using the Script (Recommended)

```bash
cd /workspace/MCP/mcp-servers
./template/scripts/create_new_server.sh my-service 8003 "My Service MCP Server"
```

This will:
- Create the server directory structure
- Copy all template files
- Replace all placeholders
- Generate Docker and nginx snippets
- Create example files

## Option 2: Manual Creation

1. **Copy the template:**
   ```bash
   cp -r template/src/mcp_servers/SERVER_NAME src/mcp_servers/my-service
   ```

2. **Replace placeholders:**
   ```bash
   cd src/mcp_servers/my-service
   find . -type f -exec sed -i 's/SERVER_NAME/my-service/g' {} +
   find . -type f -exec sed -i 's/Server Name Server/My Service Server/g' {} +
   ```

3. **Fix class names:**
   ```bash
   # Update to proper camelCase
   sed -i 's/my-serviceTenant/MyServiceTenant/g' *.py
   ```

## Next Steps

After creation, follow the [Integration Guide](INTEGRATION_GUIDE.md) to:
1. Add Docker configuration
2. Add docker-compose service
3. Add nginx configuration
4. Update client configs
5. Build and test

## Customization Checklist

- [ ] Update `tenant_manager.py` with your service configuration
- [ ] Implement your tools in `server.py`
- [ ] Add dependencies to `pyproject.toml`
- [ ] Update Docker configuration
- [ ] Test locally
- [ ] Test remotely

## Example: Creating an API Service Server

```bash
# Create the server
./template/scripts/create_new_server.sh api-service 8003 "API Service MCP Server"

# Customize tenant_manager.py:
# - Add api_key, api_url fields to TenantConfig
# - Implement API client creation in register_tenant
# - Update get_client to return API client

# Customize server.py:
# - Implement API-specific tools (get_data, post_data, etc.)
# - Add request/response models

# Add dependencies:
# - Add httpx or requests to pyproject.toml

# Build and test
docker compose build mcp-api-service-server
docker compose up -d mcp-api-service-server
```

