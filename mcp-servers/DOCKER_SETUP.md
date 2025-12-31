# Docker Setup Guide

This guide explains how to run the MCP servers using Docker.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+

## Quick Start

1. **Clone and navigate to the directory:**
   ```bash
   cd /workspace/mcp-servers
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Build and start services:**
   ```bash
   docker compose up -d
   ```

4. **Verify services are running:**
   ```bash
   docker compose ps
   ```

5. **Check logs:**
   ```bash
   docker compose logs -f
   ```

## Services

The docker-compose setup includes:

- **redis** - Redis server for tenant configuration storage (port 6379)
- **mcp-calculator-server** - Calculator MCP server (port 8000)
- **mcp-postgres-server-new** - PostgreSQL MCP server (port 8001)
- **mcp-minio-server-new** - MinIO MCP server (port 8002)

## Configuration

### Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

- **PostgreSQL**: Update `POSTGRES_TENANT_*` variables with your database connection details
- **MinIO**: Update `MINIO_TENANT_*` variables with your MinIO endpoint and credentials
- **Redis**: Defaults are fine for local development (uses container name `redis`)

### Ports

By default, services expose:
- Calculator: `http://localhost:8000`
- Postgres: `http://localhost:8001`
- MinIO: `http://localhost:8002`
- Redis: `localhost:6379`

To change ports, edit `docker-compose.yml` and update the port mappings.

## Building

### Build all services:
```bash
docker compose build
```

### Build specific service:
```bash
docker compose build mcp-calculator-server
docker compose build mcp-postgres-server-new
docker compose build mcp-minio-server-new
```

## Running

### Start all services:
```bash
docker compose up -d
```

### Start specific service:
```bash
docker compose up -d mcp-calculator-server
```

### View logs:
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f mcp-calculator-server
```

## Health Checks

All services include health checks:

- **Calculator**: `http://localhost:8000/health`
- **Postgres**: `http://localhost:8001/health`
- **MinIO**: `http://localhost:8002/health`
- **Redis**: `redis-cli ping`

Check health status:
```bash
docker compose ps
```

## Testing

### Test Calculator Server:
```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {}, "id": 1}'
```

### Test Postgres Server:
```bash
curl http://localhost:8001/health
```

### Test MinIO Server:
```bash
curl http://localhost:8002/health
```

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v
```

## Updating Services

```bash
# Rebuild and restart
docker compose up -d --build

# Restart specific service
docker compose restart mcp-calculator-server
```

## Troubleshooting

### Services won't start

1. Check logs:
   ```bash
   docker compose logs
   ```

2. Verify environment variables:
   ```bash
   docker compose config
   ```

3. Check if ports are already in use:
   ```bash
   netstat -tulpn | grep -E "8000|8001|8002|6379"
   ```

### Redis connection issues

If Postgres or MinIO servers can't connect to Redis:

1. Verify Redis is running:
   ```bash
   docker compose ps redis
   ```

2. Check Redis logs:
   ```bash
   docker compose logs redis
   ```

3. Test Redis connection:
   ```bash
   docker compose exec redis redis-cli ping
   ```

### Database connection issues

If Postgres server can't connect to your database:

1. Verify database is accessible from the container:
   ```bash
   docker compose exec mcp-postgres-server-new ping your-postgres-host
   ```

2. Check environment variables:
   ```bash
   docker compose exec mcp-postgres-server-new env | grep POSTGRES
   ```

3. Test connection manually:
   ```bash
   docker compose exec mcp-postgres-server-new psql -h your-postgres-host -U postgres -d your-database
   ```

### MinIO connection issues

If MinIO server can't connect to your MinIO instance:

1. Verify MinIO endpoint is correct in `.env`
2. Check network connectivity:
   ```bash
   docker compose exec mcp-minio-server-new ping your-minio-endpoint
   ```

## Production Deployment

For production:

1. **Use external Redis**: Update `REDIS_HOST` to point to your Redis instance
2. **Use secrets management**: Don't store passwords in `.env`, use Docker secrets or a secrets manager
3. **Configure networking**: Use proper network isolation
4. **Set resource limits**: Add resource limits in `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '0.5'
         memory: 512M
   ```
5. **Enable logging**: Configure proper log rotation and aggregation
6. **Use HTTPS**: Set up reverse proxy (nginx/traefik) with SSL certificates

## Multi-tenant Setup

To add more tenants:

1. Add environment variables to `.env`:
   ```bash
   POSTGRES_TENANT_2_HOST=another-host
   POSTGRES_TENANT_2_PORT=5432
   # ... etc
   ```

2. Restart the service:
   ```bash
   docker compose restart mcp-postgres-server-new
   ```

Or register tenants programmatically using the `register_tenant` tool.

## Network Configuration

Services run on the `mcp-network` bridge network. To connect external services:

```bash
docker network connect mcp-network your-external-container
```

## Volumes

- **redis-data**: Persistent storage for Redis data

To backup Redis data:
```bash
docker compose exec redis redis-cli SAVE
docker cp mcp-redis:/data/dump.rdb ./backup/
```

