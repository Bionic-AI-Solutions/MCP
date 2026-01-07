# MCP Servers DevContainer

A clean, simple DevContainer setup for developing and deploying MCP servers.

## Features

- ✅ All MCP server dependencies pre-installed
- ✅ Docker CLI (uses host docker daemon)
- ✅ kubectl for Kubernetes deployment
- ✅ Python 3.12 with all required packages
- ✅ Development tools (vim, nano, git)
- ✅ VS Code extensions pre-configured

## What's Included

### System Dependencies
- Python 3.12
- Docker CLI
- kubectl
- PostgreSQL client
- FFmpeg
- All required libraries for PDF generation, image processing, etc.

### Python Dependencies
- fastmcp
- psycopg (PostgreSQL)
- minio
- redis
- weasyprint, reportlab (PDF generation)
- httpx, aiohttp (HTTP clients)
- pytest, ruff, black (development tools)

### Mounts
- Docker socket (`/var/run/docker.sock`) - for building/pushing images
- Kubernetes config (`~/.kube`) - for cluster access
- MCP config files (`~/.cursor/mcp*.json`) - for Cursor integration
- Workspace - full access to code

## Usage

### Running MCP Servers

Start all servers:
```bash
cd mcp-servers
docker compose up -d
```

Start individual server:
```bash
cd mcp-servers
fastmcp run src/mcp_servers/calculator/server.py --transport http --port 8000 --host 0.0.0.0
```

### Building Docker Images

```bash
cd mcp-servers
docker build --target calculator -t my-calculator:latest .
docker push my-calculator:latest
```

### Kubernetes Deployment

```bash
cd mcp-servers/k8s
kubectl apply -f .
kubectl get pods -n mcp
```

### Running Tests

```bash
cd mcp-servers
pytest tests/
```

## Port Forwarding

The following ports are automatically forwarded:
- 8000: Calculator MCP Server
- 8001: Postgres MCP Server
- 8002: MinIO MCP Server
- 8003: PDF Generator MCP Server
- 8004: FFmpeg MCP Server
- 8005: Mail MCP Server
- 8006: OpenProject MCP Server
- 6379: Redis

## Environment Variables

- `PYTHONPATH=/workspace/mcp-servers/src`
- `DOCKER_HOST=unix:///var/run/docker.sock`
- `KUBECONFIG=/home/vscode/.kube/config`

## Troubleshooting

### Docker not accessible
- Check that `/var/run/docker.sock` is mounted
- Verify Docker is running on the host

### Kubernetes not accessible
- Check that `~/.kube/config` exists on the host
- Verify kubectl can connect from the host

### MCP servers won't start
- Check that dependencies are installed: `python3 -c "import fastmcp"`
- Verify PYTHONPATH is set correctly
- Check port availability
