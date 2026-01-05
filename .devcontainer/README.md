# MCP Servers DevContainer

This devcontainer provides a complete development environment for MCP (Model Context Protocol) servers development.

## Features

- ✅ Python 3.12 with all MCP server dependencies
- ✅ Docker CLI access (uses host Docker daemon)
- ✅ kubectl access (uses host kubectl and kubeconfig)
- ✅ All MCP server dependencies pre-installed
- ✅ VS Code extensions for Python development
- ✅ Port forwarding for all MCP servers (8000-8005, 6379)

## Prerequisites

- Docker Desktop or Docker Engine running on the host
- VS Code with the "Dev Containers" extension
- kubectl installed on the host (optional, for Kubernetes access)
- Kubernetes config at `~/.kube/config` (optional)

## First Time Setup

1. Open the project in VS Code
2. When prompted, click "Reopen in Container" or use Command Palette: `Dev Containers: Reopen in Container`
3. The first build may take 10-15 minutes due to ffmpeg dependencies
4. Subsequent builds will be much faster due to Docker layer caching

## What Gets Mounted

- **Docker Socket**: `/var/run/docker.sock` - Access to host Docker daemon
- **Docker CLI**: `/usr/bin/docker` and `/usr/local/bin/docker` - Docker commands
- **Kubernetes Config**: `~/.kube` directory - Kubernetes cluster access
- **kubectl**: `/usr/local/bin/kubectl` - Kubernetes CLI
- **MCP Config Files**: MCP client configuration files are mounted to `~/.cursor/`

## Port Forwarding

The following ports are automatically forwarded:

- `8000` - Calculator MCP Server
- `8001` - Postgres MCP Server
- `8002` - MinIO MCP Server
- `8003` - PDF Generator MCP Server
- `8004` - FFmpeg MCP Server
- `8005` - Mail MCP Server
- `6379` - Redis

## Usage

### Start MCP Servers

```bash
cd /workspace/mcp-servers
docker compose up -d
```

### Run Tests

```bash
cd /workspace/mcp-servers
pytest
```

### Access Kubernetes

```bash
kubectl get pods
kubectl get services
```

### Build Docker Images

```bash
cd /workspace/mcp-servers
docker compose build
```

## Environment Variables

The following environment variables are set:

- `PYTHONPATH=/workspace/mcp-servers/src`
- `DOCKER_HOST=unix:///var/run/docker.sock`

## Troubleshooting

### Docker not accessible

If Docker commands fail, verify:
1. Docker is running on the host
2. The docker socket is mounted correctly
3. You have permissions to access the docker socket

### Kubernetes not accessible

If kubectl commands fail, verify:
1. `~/.kube/config` exists on the host
2. The kubeconfig is valid
3. You can access the cluster from the host

### Build takes too long

The first build includes ffmpeg which has many dependencies. This is normal and subsequent builds will be faster due to caching.

### Python imports fail

Ensure you're in the correct directory and `PYTHONPATH` is set:
```bash
export PYTHONPATH=/workspace/mcp-servers/src
cd /workspace/mcp-servers
```

## VS Code Extensions

The following extensions are automatically installed:

- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Black Formatter (ms-python.black-formatter)
- Ruff (charliermarsh.ruff)
- Docker (ms-azuretools.vscode-docker)
- Kubernetes (ms-kubernetes-tools.vscode-kubernetes-tools)

## Customization

To customize the devcontainer:

1. Edit `.devcontainer/devcontainer.json` for VS Code settings
2. Edit `.devcontainer/Dockerfile` for container image changes
3. Edit `.devcontainer/post-create.sh` for post-creation setup

After making changes, rebuild the container:
- Command Palette: `Dev Containers: Rebuild Container`



