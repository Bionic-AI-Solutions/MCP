# SERVER_NAME MCP Server Setup Guide

This guide walks you through setting up the SERVER_NAME MCP server.

## Prerequisites

- Docker and Docker Compose installed
- Access to Redis (included in docker-compose)
- [List any other prerequisites specific to your server]

## Step 1: Add Server Code

1. Copy the template to your server directory:
   ```bash
   cp -r template/src/mcp_servers/SERVER_NAME src/mcp_servers/<your-server-name>
   ```

2. Replace `SERVER_NAME` with your actual server name in all files:
   ```bash
   find src/mcp_servers/<your-server-name> -type f -exec sed -i 's/SERVER_NAME/<your-server-name>/g' {} +
   ```

## Step 2: Customize Configuration

1. **Update `tenant_manager.py`**:
   - Define your tenant configuration model
   - Implement client/connection creation logic
   - Update environment variable loading

2. **Update `server.py`**:
   - Implement your MCP tools
   - Add request/response models
   - Customize resources

## Step 3: Add Dependencies

1. **Update `pyproject.toml`**:
   ```toml
   dependencies = [
       # ... existing dependencies ...
       "your-service-library>=1.0.0",
   ]
   ```

2. **Update `Dockerfile`**:
   - Add any system dependencies to the base stage
   - Add Python dependencies to the pip install command

## Step 4: Docker Configuration

1. **Add to `Dockerfile`**:
   - Copy the Dockerfile snippet from `template/docker/Dockerfile.snippet`
   - Replace placeholders with your values

2. **Add to `docker-compose.yml`**:
   - Copy the docker-compose snippet from `template/docker/docker-compose.snippet`
   - Replace placeholders with your values
   - Choose an available port (next available: 8003)

## Step 5: Nginx Configuration

1. **Add upstream** to `nginx.conf`:
   ```nginx
   upstream mcp_<server-name>_backend {
       server mcp-<server-name>-server:PORT_NUMBER;
       keepalive 32;
   }
   ```

2. **Add location blocks**:
   - Copy the nginx snippet from `template/nginx/nginx.conf.snippet`
   - Replace placeholders
   - Add inside the HTTPS server block

## Step 6: Update Client Configuration

1. **Update `mcp_client_config_cursor_remote.json`**:
   ```json
   {
     "mcpServers": {
       "<server-name>-mcp-remote": {
         "url": "https://mcp.bionicaisolutions.com/<server-name>/mcp",
         "description": "SERVER_NAME MCP Server - External access via HTTPS"
       }
     }
   }
   ```

## Step 7: Build and Test

1. **Build the Docker image**:
   ```bash
   docker compose build mcp-<server-name>-server
   ```

2. **Start the server**:
   ```bash
   docker compose up -d mcp-<server-name>-server
   ```

3. **Test locally**:
   ```bash
   curl http://localhost:PORT_NUMBER/mcp -X POST \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
   ```

4. **Test remote** (after nginx reload):
   ```bash
   curl https://mcp.bionicaisolutions.com/<server-name>/mcp -X POST \
     -H "Content-Type: application/json" \
     -H "Accept: application/json, text/event-stream" \
     -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
   ```

## Step 8: Reload Nginx

After updating nginx configuration:
```bash
docker exec <nginx-container> nginx -s reload
```

## Verification Checklist

- [ ] Server code added and customized
- [ ] Dependencies added to pyproject.toml
- [ ] Docker configuration added
- [ ] Nginx configuration added
- [ ] Client configuration updated
- [ ] Server builds successfully
- [ ] Server starts and health check passes
- [ ] Local endpoint works
- [ ] Remote endpoint works (after nginx reload)
- [ ] Can register tenants
- [ ] Can use tools with registered tenants

