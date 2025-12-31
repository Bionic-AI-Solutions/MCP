# Quick Start Guide

This guide will help you get the MCP servers running and accessible via nginx.

## Prerequisites

- Docker and Docker Compose installed
- Access to the `mcp-network` Docker network (or it will be created automatically)
- SSL certificates for `mcp.bionicaisolutions.com` (if using HTTPS)

## Step 1: Build and Start MCP Servers

```bash
cd /workspace/mcp-servers
docker compose build
docker compose up -d
```

This will start:
- `mcp-calculator-server` on port 8000
- `mcp-postgres-server-new` on port 8001
- `mcp-minio-server-new` on port 8002

## Step 2: Configure Environment Variables (Optional)

If you need to configure tenants, you can either:

### Option A: Set in docker-compose.yml

Edit `/workspace/mcp-servers/docker-compose.yml` and update the environment variables.

### Option B: Use .env file

Create a `.env` file in `/workspace/mcp-servers/`:

```bash
POSTGRES_TENANT_1_HOST=your-postgres-host
POSTGRES_TENANT_1_PORT=5432
POSTGRES_TENANT_1_DB=your-database
POSTGRES_TENANT_1_USER=postgres
POSTGRES_TENANT_1_PASSWORD=your-password

MINIO_TENANT_1_ENDPOINT=your-minio:9000
MINIO_TENANT_1_ACCESS_KEY=your-access-key
MINIO_TENANT_1_SECRET_KEY=your-secret-key
MINIO_TENANT_1_SECURE=false
```

## Step 3: Configure Nginx (Separate Setup)

**Note**: Nginx configuration is separate from this repository. Configure your nginx to route:
- `/calculator/*` → `mcp-calculator-server:8000`
- `/postgres/*` → `mcp-postgres-server-new:8001`
- `/minio/*` → `mcp-minio-server-new:8002`

See `NGINX_SETUP.md` for detailed nginx configuration examples.

## Step 4: Verify Services

Check that all services are running:

```bash
# Check MCP servers
docker ps | grep -E "mcp-calculator|mcp-postgres|mcp-minio"

# Check nginx
docker ps | grep mcp-nginx

# Test endpoints
curl https://mcp.bionicaisolutions.com/calculator/sse
curl https://mcp.bionicaisolutions.com/postgres/sse
curl https://mcp.bionicaisolutions.com/minio/sse
```

## Step 5: Configure MCP Client

Use the remote configuration in your MCP client (e.g., Cursor):

```json
{
  "mcpServers": {
    "calculator-mcp": {
      "url": "https://mcp.bionicaisolutions.com/calculator/sse"
    },
    "postgres-mcp": {
      "url": "https://mcp.bionicaisolutions.com/postgres/sse"
    },
    "minio-mcp": {
      "url": "https://mcp.bionicaisolutions.com/minio/sse"
    }
  }
}
```

## Troubleshooting

### Services Not Starting

1. Check Docker logs:
   ```bash
   docker logs mcp-calculator-server
   docker logs mcp-postgres-server-new
   docker logs mcp-minio-server-new
   ```

2. Verify network exists:
   ```bash
   docker network ls | grep mcp-network
   ```

3. If network doesn't exist, create it:
   ```bash
   docker network create mcp-network
   ```

### Nginx Can't Connect to Servers

1. Verify services are on the network:
   ```bash
   docker network inspect mcp-network
   ```

2. Test connectivity from nginx:
   ```bash
   docker exec mcp-nginx wget -O- http://mcp-calculator-server:8000/sse
   ```

3. Check nginx logs:
   ```bash
   docker logs mcp-nginx
   ```

### SSL Certificate Issues

If using HTTPS, ensure certificates are set up:

```bash
# Check certificates
docker exec mcp-nginx ls -la /etc/letsencrypt/live/mcp.bionicaisolutions.com/

# If missing, set up certbot (see nginx setup docs)
```

## Stopping Services

```bash
# Stop MCP servers
cd /workspace/mcp-servers
docker compose down

# Stop nginx
cd /workspace/mcp-nginx
docker compose down
```

## Updating Services

```bash
# Rebuild and restart MCP servers
cd /workspace/mcp-servers
docker compose build
docker compose up -d

# Reload nginx (if config changed)
docker exec mcp-nginx nginx -s reload
```

