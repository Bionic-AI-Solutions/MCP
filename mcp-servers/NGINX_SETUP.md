# Nginx Setup for MCP Servers

This document explains how the new FastMCP servers are configured to work with nginx.

## Overview

The new MCP servers (Calculator, Postgres, MinIO) are available externally via nginx at:
- `https://mcp.bionicaisolutions.com/calculator/sse` or `/calculator/mcp`
- `https://mcp.bionicaisolutions.com/postgres/sse` or `/postgres/mcp`
- `https://mcp.bionicaisolutions.com/minio/sse` or `/minio/mcp`

## Architecture

```
Internet
   │
   ▼
mcp.bionicaisolutions.com (nginx)
   │
   ├── /calculator/* → mcp-calculator-server:8000
   ├── /postgres/* → mcp-postgres-server-new:8001
   └── /minio/* → mcp-minio-server-new:8002
```

## Docker Services

The servers are defined in `/workspace/mcp-servers/docker-compose.yml`:

- **mcp-calculator-server**: Port 8000
- **mcp-postgres-server-new**: Port 8001
- **mcp-minio-server-new**: Port 8002

All services run on the shared `mcp-network` for nginx to access them.

## Nginx Configuration

The nginx configuration in `/workspace/mcp-nginx/nginx.conf` includes:

1. **Upstream definitions** for each server
2. **Location blocks** for routing:
   - `/calculator/`, `/calculator/sse`, `/calculator/mcp`
   - `/postgres/`, `/postgres/sse`, `/postgres/mcp`
   - `/minio/`, `/minio/sse`, `/minio/mcp`
3. **Health check endpoints** for monitoring

## Starting the Services

### 1. Start the MCP Servers

```bash
cd /workspace/mcp-servers
docker compose up -d
```

This will start:
- mcp-calculator-server
- mcp-postgres-server-new
- mcp-minio-server-new

### 2. Start Nginx

**Note**: The nginx setup is separate and should be configured in your infrastructure. The nginx configuration should route:
- `/calculator/*` → `mcp-calculator-server:8000`
- `/postgres/*` → `mcp-postgres-server-new:8001`
- `/minio/*` → `mcp-minio-server-new:8002`

Example nginx configuration:
```bash
# Configure nginx to proxy to the MCP servers
# See NGINX_SETUP.md for detailed configuration
```

Nginx will automatically connect to the servers via the shared `mcp-network`.

### 3. Verify Services

Check that all services are running:

```bash
docker ps | grep -E "mcp-calculator|mcp-postgres|mcp-minio|mcp-nginx"
```

## Testing the Endpoints

### Calculator

```bash
# Test SSE endpoint
curl https://mcp.bionicaisolutions.com/calculator/sse

# Test MCP endpoint
curl -X POST https://mcp.bionicaisolutions.com/calculator/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}'
```

### Postgres

```bash
# Test SSE endpoint
curl https://mcp.bionicaisolutions.com/postgres/sse

# Test health
curl https://mcp.bionicaisolutions.com/postgres/health
```

### MinIO

```bash
# Test SSE endpoint
curl https://mcp.bionicaisolutions.com/minio/sse

# Test health
curl https://mcp.bionicaisolutions.com/minio/health
```

## Client Configuration

For remote access, use this configuration in your MCP client:

```json
{
  "mcpServers": {
    "calculator-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/calculator/sse"
    },
    "postgres-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/postgres/sse"
    },
    "minio-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/minio/sse"
    }
  }
}
```

## Troubleshooting

### Services Not Accessible

1. Check if services are running:
   ```bash
   docker ps | grep mcp-
   ```

2. Check network connectivity:
   ```bash
   docker network inspect mcp-network
   ```

3. Test from nginx container:
   ```bash
   docker exec mcp-nginx curl http://mcp-calculator-server:8000/sse
   ```

### Nginx Configuration Issues

1. Check nginx logs:
   ```bash
   docker logs mcp-nginx
   ```

2. Test nginx configuration:
   ```bash
   docker exec mcp-nginx nginx -t
   ```

3. Reload nginx:
   ```bash
   docker exec mcp-nginx nginx -s reload
   ```

### SSL Certificate Issues

If you see SSL errors, ensure certificates are set up:

```bash
cd /workspace/mcp-nginx
./setup-ssl.sh  # If available
```

Or check certificates:
```bash
docker exec mcp-nginx ls -la /etc/letsencrypt/live/mcp.bionicaisolutions.com/
```

## Environment Variables

The servers support environment variables for configuration:

### Postgres Server

```bash
export POSTGRES_TENANT_1_HOST=your-host
export POSTGRES_TENANT_1_PORT=5432
export POSTGRES_TENANT_1_DB=your-db
export POSTGRES_TENANT_1_USER=your-user
export POSTGRES_TENANT_1_PASSWORD=your-password
```

### MinIO Server

```bash
export MINIO_TENANT_1_ENDPOINT=your-minio:9000
export MINIO_TENANT_1_ACCESS_KEY=your-key
export MINIO_TENANT_1_SECRET_KEY=your-secret
export MINIO_TENANT_1_SECURE=false
```

These can be set in the docker-compose.yml file or passed as environment variables when starting the containers.

