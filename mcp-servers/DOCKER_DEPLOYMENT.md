# Docker Deployment - MCP Servers

## Status: ✅ Deployed and Running

All MCP servers are now running in Docker containers and accessible via HTTP.

## Services

| Service | Port | Endpoint | Status |
|---------|------|----------|--------|
| Calculator | 8000 | `http://localhost:8000/mcp` | ✅ Running |
| Postgres | 8001 | `http://localhost:8001/mcp` | ✅ Running |
| MinIO | 8002 | `http://localhost:8002/mcp` | ✅ Running |
| Redis | 6379 | `localhost:6379` | ✅ Running |

## Cursor Configuration

The `mcp_client_config_cursor_local.json` has been updated to use Docker endpoints:

```json
{
  "mcpServers": {
    "calculator-mcp": {
      "url": "http://localhost:8000/mcp"
    },
    "postgres-mcp": {
      "url": "http://localhost:8001/mcp"
    },
    "minio-mcp": {
      "url": "http://localhost:8002/mcp"
    }
  }
}
```

## Next Steps

1. **Copy config to Cursor:**
   ```bash
   cp /workspace/mcp-servers/mcp_client_config_cursor_local.json ~/.cursor/mcp.json
   ```

2. **Restart Cursor** completely

3. **Verify connection** - The MCP servers should now be accessible from Cursor

## Managing Services

### Start services:
```bash
cd /workspace/mcp-servers
docker compose up -d
```

### Stop services:
```bash
cd /workspace/mcp-servers
docker compose down
```

### View logs:
```bash
docker compose logs -f
```

### Check status:
```bash
docker compose ps
```

## Testing

Test the endpoints:
```bash
# Calculator
curl http://localhost:8000/mcp -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'

# Postgres
curl http://localhost:8001/mcp -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'

# MinIO
curl http://localhost:8002/mcp -X POST -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
```

