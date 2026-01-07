# MCP Servers DevContainer

This devcontainer provides a complete development environment for building, testing, and deploying MCP servers.

## Features

- **Python 3.12** with all project dependencies
- **Docker CLI** with access to host Docker daemon (for building and pushing images)
- **kubectl** with Kubernetes cluster access
- **MCP Configuration** mounted from host
- **Development Tools**: pytest, ruff, black, and more

## Prerequisites

- Docker Desktop or Docker Engine running on the host
- Kubernetes cluster access (kubeconfig at `~/.kube/config`)
- MCP configuration at `~/.cursor/mcp.json`

## Setup

1. Open the project in VS Code
2. When prompted, click "Reopen in Container"
3. Wait for the container to build and initialize

## Docker Operations

The devcontainer has full access to the host Docker daemon, allowing you to:

### Build Images

```bash
# Build a specific server
docker build --target openproject -t docker.io/docker4zerocool/mcp-servers-openproject:latest .

# Or use the helper script
docker-helper.sh build openproject latest
```

### Push Images

```bash
# First, login to Docker Hub
docker login
# Or use environment variables
export DOCKER_USERNAME=your-username
export DOCKER_PASSWORD=your-token
docker-helper.sh login

# Then push
docker push docker.io/docker4zerocool/mcp-servers-openproject:latest
# Or use the helper
docker-helper.sh build openproject latest
```

### Build All Servers

```bash
docker-helper.sh build-all latest
```

## Kubernetes Operations

Access your Kubernetes cluster directly:

```bash
# Check cluster connection
kubectl cluster-info

# Deploy changes
kubectl apply -k k8s/

# Check deployment status
kubectl get pods -n mcp

# View logs
kubectl logs -f deployment/mcp-openproject-server -n mcp
```

## Development Workflow

1. **Make code changes** in the container
2. **Test locally** using pytest
3. **Build Docker image** using `docker build` or `docker-helper.sh`
4. **Push to registry** using `docker push` or `docker-helper.sh`
5. **Deploy to Kubernetes** using `kubectl apply -k k8s/`
6. **Restart deployment** using `kubectl rollout restart`

## Helper Scripts

### docker-helper.sh

Convenient wrapper for common Docker operations:

```bash
# Login to Docker Hub
docker-helper.sh login

# Build and push a specific server
docker-helper.sh build <server-name> [tag]

# Build and push all servers
docker-helper.sh build-all [tag]
```

**Environment Variables:**
- `DOCKER_USERNAME` - Docker Hub username
- `DOCKER_PASSWORD` - Docker Hub password/token
- `DOCKER_REGISTRY` - Docker registry (default: docker.io/docker4zerocool)

## Troubleshooting

### Docker Access Issues

If you get "permission denied" errors with Docker:

1. Ensure Docker is running on the host
2. Check that `/var/run/docker.sock` is mounted
3. Restart the devcontainer

### Kubernetes Access Issues

If kubectl can't connect:

1. Verify `~/.kube/config` exists on the host
2. Check that the config is mounted at `/home/vscode/.kube/config`
3. Verify cluster credentials are valid

### MCP Configuration

If MCP tools aren't available:

1. Verify `~/.cursor/mcp.json` exists on the host
2. Check that it's mounted at `/home/vscode/.cursor/mcp.json`
3. Restart Cursor/VS Code after changes

## File Locations

- **Workspace**: `/workspace/mcp-servers`
- **Kubernetes Config**: `/home/vscode/.kube/config`
- **MCP Config**: `/home/vscode/.cursor/mcp.json`
- **Docker Socket**: `/var/run/docker.sock` (host socket)

## VS Code Extensions

The devcontainer automatically installs:

- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Kubernetes (ms-kubernetes-tools.vscode-kubernetes-tools)
- Docker (ms-azuretools.vscode-docker)

## Notes

- The container uses the **host Docker daemon** (not Docker-in-Docker) for better performance and to allow pushing images
- All Docker images built in the container are available on the host
- Kubernetes operations use the host's kubeconfig
- Python dependencies are installed using `uv` for faster installation









