# Integration Guide: Adding a New MCP Server

This guide provides step-by-step instructions for integrating a new MCP server created from the template into the existing setup.

## Prerequisites

- New server created from template (using `create_new_server.sh` or manually)
- Server code customized and tested locally
- Dependencies identified and documented

## Step 1: Add Dockerfile Stage

1. Open `Dockerfile` in the root `mcp-servers` directory
2. Add the Dockerfile stage from `docker/<server-name>_Dockerfile.snippet`
3. Replace any placeholders if needed
4. Add any additional system dependencies to the `base` stage if required

**Example:**
```dockerfile
# MyService stage
FROM base as myservice
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8003
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/myservice/server.py", "--transport", "http", "--port", "8003", "--host", "0.0.0.0"]
```

## Step 2: Add Docker Compose Service

1. Open `docker-compose.yml`
2. Add the service from `docker/<server-name>_docker-compose.snippet`
3. Verify port doesn't conflict with existing services
4. Update Redis DB number if needed (should be unique per service)

**Ports in use:**
- 8000: Calculator
- 8001: Postgres
- 8002: MinIO
- **Next available: 8003**

## Step 3: Add Nginx Configuration

1. Open `MCP/mcp-nginx/nginx.conf`
2. Add upstream definition in the `http` block (before server blocks):
   ```nginx
   upstream mcp_<server-name>_backend {
       server mcp-<server-name>-server:PORT_NUMBER;
       keepalive 32;
   }
   ```
3. Add location blocks from `nginx/<server-name>_nginx.snippet` inside the HTTPS server block for `mcp.bionicaisolutions.com`
4. Update the default location block's error message to include your server path

## Step 4: Update Client Configuration

1. Open `mcp_client_config_cursor_remote.json`
2. Add your server configuration:
   ```json
   {
     "mcpServers": {
       "<server-name>-mcp-remote": {
         "url": "https://mcp.bionicaisolutions.com/<server-name>/mcp",
         "description": "Your Server Description - External access via HTTPS"
       }
     }
   }
   ```

## Step 5: Update Dependencies (if needed)

1. Open `pyproject.toml`
2. Add any new Python dependencies to the `dependencies` list
3. If adding system dependencies, update the `Dockerfile` base stage

## Step 6: Build and Test

### Build the Server
```bash
cd /workspace/MCP/mcp-servers
docker compose build mcp-<server-name>-server
```

### Start the Server
```bash
docker compose up -d mcp-<server-name>-server
```

### Check Logs
```bash
docker compose logs -f mcp-<server-name>-server
```

### Test Local Endpoint
```bash
curl http://localhost:PORT_NUMBER/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

### Test Remote Endpoint (after nginx reload)
```bash
curl https://mcp.bionicaisolutions.com/<server-name>/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

## Step 7: Reload Nginx

After updating nginx configuration:
```bash
# Find nginx container
docker ps | grep nginx

# Reload nginx
docker exec <nginx-container-name> nginx -s reload

# Or restart if reload doesn't work
docker restart <nginx-container-name>
```

## Step 8: Verify Integration

### Checklist

- [ ] Server builds without errors
- [ ] Server starts and health check passes
- [ ] Server logs show successful startup
- [ ] Local endpoint responds to initialize request
- [ ] Remote endpoint responds to initialize request (after nginx reload)
- [ ] Can register a tenant via MCP tool
- [ ] Can use tools with registered tenant
- [ ] Tenant configuration persists in Redis
- [ ] Server restarts and loads tenants from Redis

### Verification Commands

```bash
# Check server is running
docker ps | grep <server-name>

# Check health
curl http://localhost:PORT_NUMBER/health

# Check Redis persistence
docker exec mcp-redis redis-cli KEYS "mcp:<server-name>:tenant:*"

# Test tenant registration (via MCP client or direct script)
```

## Troubleshooting

### Server Won't Start
- Check logs: `docker compose logs mcp-<server-name>-server`
- Verify dependencies in `pyproject.toml`
- Check port conflicts: `netstat -tuln | grep PORT_NUMBER`

### Import Errors
- Verify `PYTHONPATH=/app/src` in Dockerfile
- Check import statements use try/except pattern (see template)
- Ensure all dependencies are in `pyproject.toml`

### Nginx 502 Bad Gateway
- Verify upstream server is running: `docker ps | grep <server-name>`
- Check nginx logs: `docker logs <nginx-container>`
- Verify upstream name matches in nginx.conf

### Tenant Not Found
- Check Redis: `docker exec mcp-redis redis-cli GET "mcp:<server-name>:tenant:<tenant-id>"`
- Verify tenant manager initialization in server logs
- Check environment variables if using env-based config

## Next Steps

After successful integration:
1. Update `AVAILABLE_TOOLS.md` with your server's tools
2. Add examples to `examples/` directory
3. Update main `README.md` if needed
4. Document any server-specific configuration requirements

