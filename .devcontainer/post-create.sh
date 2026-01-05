#!/bin/bash
set -e

echo "🚀 Setting up MCP Servers Development Environment..."

# Ensure we're in the workspace
cd /workspace

# Set up Python path
export PYTHONPATH=/workspace/mcp-servers/src

# Verify Docker access
echo "📦 Verifying Docker access..."
if docker ps > /dev/null 2>&1; then
    echo "✅ Docker is accessible"
    docker --version
else
    echo "⚠️  Warning: Docker may not be accessible. Check docker socket mount."
fi

# Verify kubectl access
echo "☸️  Verifying kubectl access..."
if [ -f /home/vscode/.kube/config ]; then
    echo "✅ Kubernetes config found"
    if kubectl cluster-info > /dev/null 2>&1; then
        echo "✅ Kubernetes cluster is accessible"
        kubectl version --client
    else
        echo "⚠️  Warning: Kubernetes cluster may not be accessible. Check kubeconfig."
    fi
else
    echo "⚠️  Warning: Kubernetes config not found at /home/vscode/.kube/config"
fi

# Verify Python and dependencies
echo "🐍 Verifying Python environment..."
python3 --version
python3 -c "import fastmcp; print(f'✅ FastMCP version: {fastmcp.__version__}')" || echo "⚠️  FastMCP not found"

# Set up git (if needed)
echo "📝 Git configuration..."
git config --global --add safe.directory /workspace || true

# Create .cursor directory for MCP config files
echo "🔗 Setting up MCP configuration..."
mkdir -p /home/vscode/.cursor
if [ -d /workspace/mcp-servers ]; then
    echo "✅ MCP servers directory found"
    if ls /workspace/mcp-servers/mcp_client_config_*.json 1> /dev/null 2>&1; then
        echo "✅ MCP config files found:"
        ls -la /workspace/mcp-servers/mcp_client_config_*.json
        echo "✅ MCP config files should be mounted to ~/.cursor/"
    else
        echo "⚠️  MCP config files not found in workspace"
    fi
fi

echo "✨ DevContainer setup complete!"
echo ""
echo "Available commands:"
echo "  - docker compose up -d    # Start MCP servers"
echo "  - kubectl get pods        # Check Kubernetes pods"
echo "  - pytest                  # Run tests"
echo ""

