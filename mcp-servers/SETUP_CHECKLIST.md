# Setup Checklist for New Location

When setting up the MCP servers in a new location, follow this checklist:

## 1. Copy Files

Copy the entire `mcp-servers` directory to your new location.

## 2. Update Paths in Configuration

Edit `mcp_client_config_cursor_local.json` and update all paths:

- Replace `/workspace/mcp-servers` with your new path
- Update the `command` path to point to your new location's `.venv/bin/fastmcp`
- Update all `args` paths to point to your new location's server files

## 3. Run Setup Script

```bash
cd <your-new-path>/mcp-servers
./setup_for_cursor.sh
```

This will:
- Create a `.venv` virtual environment
- Install all dependencies
- Verify the installation

## 4. Configure Cursor

Copy the updated config to Cursor:

```bash
cp <your-new-path>/mcp-servers/mcp_client_config_cursor_local.json ~/.cursor/mcp.json
```

## 5. Restart Cursor

Restart Cursor completely for the changes to take effect.

## 6. Test

Test that the servers work:

```bash
cd <your-new-path>/mcp-servers
.venv/bin/fastmcp run src/mcp_servers/calculator/server.py
```

If this works, Cursor should be able to connect.

## Files to Keep

Essential files for recreation:
- `pyproject.toml` - Dependencies
- `src/` - Source code
- `examples/` - Example usage
- `README.md` - Main documentation
- `AVAILABLE_TOOLS.md` - Tool documentation
- `QUICK_START.md` - Docker setup guide
- `NGINX_SETUP.md` - Nginx configuration
- `setup_for_cursor.sh` - Setup script
- `mcp_client_config_cursor_local.json` - Cursor config (update paths!)
- `mcp_client_config_cursor_remote.json` - Remote config
- `Dockerfile`, `docker-compose.yml` - Containerization
- `.gitignore`, `.dockerignore` - Git/Docker ignores

## Files That Can Be Recreated

These are generated and don't need to be copied:
- `.venv/` - Virtual environment (recreated by setup script)
- `__pycache__/` - Python cache (auto-generated)

