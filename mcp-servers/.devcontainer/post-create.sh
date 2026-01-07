#!/bin/bash
set -e

echo "🚀 Setting up MCP Servers development environment..."

# Verify Docker CLI is available
if command -v docker &> /dev/null; then
    echo "✅ Docker CLI is available"
    docker --version
else
    echo "⚠️  Docker CLI not found (should be installed via features)"
fi

# Verify Docker socket access
if [ -S /var/run/docker.sock ]; then
    echo "✅ Docker socket found at /var/run/docker.sock"
    # Add user to docker group if needed (for socket access)
    sudo usermod -aG docker vscode 2>/dev/null || echo "⚠️  Could not add user to docker group (may need container restart)"
else
    echo "⚠️  Docker socket not found at /var/run/docker.sock"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install uv

# Install project dependencies using uv (faster than pip)
if [ -f "pyproject.toml" ]; then
    echo "📦 Installing project dependencies..."
    uv pip install --system -e .
fi

# Install development dependencies
if [ -f "pyproject.toml" ]; then
    echo "📦 Installing development dependencies..."
    uv pip install --system -e ".[dev]" || echo "⚠️  Dev dependencies optional"
fi

# Verify Docker access
echo "🐳 Verifying Docker access..."
if docker ps &> /dev/null; then
    echo "✅ Docker is accessible"
    docker --version
else
    echo "⚠️  Warning: Docker may not be accessible. Check Docker socket mount."
fi

# Verify kubectl access
echo "☸️  Verifying kubectl access..."
if kubectl version --client &> /dev/null; then
    echo "✅ kubectl is accessible"
    kubectl version --client
    if [ -f "/home/vscode/.kube/config" ]; then
        echo "✅ Kubernetes config found"
        kubectl cluster-info 2>/dev/null || echo "⚠️  Cannot connect to cluster (may need authentication)"
    else
        echo "⚠️  Kubernetes config not found at /home/vscode/.kube/config"
    fi
else
    echo "⚠️  kubectl not found"
fi

# Verify MCP config
if [ -f "/home/vscode/.cursor/mcp.json" ]; then
    echo "✅ MCP configuration found"
else
    echo "⚠️  MCP configuration not found at /home/vscode/.cursor/mcp.json"
fi

# Set up git (if needed)
git config --global --add safe.directory /workspace/mcp-servers || true

# Make docker-helper.sh available
if [ -f ".devcontainer/docker-helper.sh" ]; then
    chmod +x .devcontainer/docker-helper.sh
    # Create symlink in a directory that's in PATH
    mkdir -p ~/bin
    ln -sf /workspace/mcp-servers/.devcontainer/docker-helper.sh ~/bin/docker-helper 2>/dev/null || true
    echo "✅ Docker helper script available (use: docker-helper.sh or docker-helper)"
fi

echo "✅ Development environment setup complete!"
echo ""
echo "📝 Available commands:"
echo "  - docker build ...           : Build Docker images"
echo "  - docker push ...            : Push images to registry"
echo "  - docker-helper.sh build ... : Build and push specific server"
echo "  - docker-helper.sh build-all : Build and push all servers"
echo "  - kubectl ...                : Manage Kubernetes resources"
echo "  - uv pip install ...         : Install Python packages"
echo "  - pytest                     : Run tests"
echo ""
echo "💡 Tip: Use 'docker-helper.sh login' to authenticate with Docker Hub"

