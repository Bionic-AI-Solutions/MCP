# Getting Started with the MCP Server Template

Welcome! This template helps you create new multi-tenant MCP servers quickly.

## The Fastest Way

```bash
cd /workspace/MCP/mcp-servers
./template/scripts/create_new_server.sh my-service 8003 "My Service MCP Server"
```

That's it! The script will:
- Create all necessary files
- Replace all placeholders
- Generate Docker and nginx snippets
- Create example files

## What You Get

After running the script, you'll have:
- ✅ Complete server code structure
- ✅ Multi-tenant support with Redis
- ✅ Docker configuration snippets
- ✅ Nginx configuration snippets
- ✅ Example usage code
- ✅ Documentation templates

## Next Steps

1. **Customize the server code:**
   - Edit `src/mcp_servers/<server-name>/tenant_manager.py` - Define your tenant config
   - Edit `src/mcp_servers/<server-name>/server.py` - Implement your tools

2. **Integrate into the system:**
   - Follow `INTEGRATION_GUIDE.md` for step-by-step instructions
   - Add Docker configuration
   - Add nginx configuration
   - Build and test

## Need Help?

- **Quick Start**: See `QUICK_START.md`
- **Integration**: See `INTEGRATION_GUIDE.md`
- **Details**: See `TEMPLATE_OVERVIEW.md`
- **Summary**: See `SUMMARY.md`

## Example: Creating an API Service

```bash
# 1. Create the server
./template/scripts/create_new_server.sh api-service 8003 "API Service MCP Server"

# 2. Customize tenant_manager.py
# Add: api_key, api_url, timeout fields
# Implement: HTTP client creation

# 3. Customize server.py
# Add: get_data, post_data tools
# Add: Request/response models

# 4. Add dependencies to pyproject.toml
# Add: httpx or requests

# 5. Follow INTEGRATION_GUIDE.md to complete setup
```

That's all you need to get started!
