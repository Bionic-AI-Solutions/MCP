#!/bin/bash
set +e  # Don't exit on errors

echo "🚀 Setting up MCP Servers Development Environment..."

# Ensure we're in the workspace
cd /workspace 2>&1 || true

# Install system dependencies needed for MCP servers
echo "📦 Installing system dependencies..."
sudo apt-get update 2>&1 || true

# Install Docker CLI
echo "🐳 Installing Docker CLI..."
sudo apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release 2>&1 || true

if [ ! -f /usr/bin/docker ]; then
    sudo install -m 0755 -d /etc/apt/keyrings 2>&1 || true
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>&1 || true
    sudo chmod a+r /etc/apt/keyrings/docker.gpg 2>&1 || true
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null 2>&1 || true
    sudo apt-get update 2>&1 || true
    sudo apt-get install -y docker-ce-cli 2>&1 || echo "⚠️  Docker CLI installation may have failed"
fi

# Install other system dependencies
sudo apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    ffmpeg 2>&1 || echo "⚠️  Some system packages may have failed to install"
sudo rm -rf /var/lib/apt/lists/* 2>&1 || true

# Install uv for faster dependency management
echo "📦 Installing uv..."
pip install --upgrade pip 2>&1 || true
pip install uv 2>&1 || true

# Install Python dependencies for mcp-servers
if [ -f "mcp-servers/pyproject.toml" ]; then
    echo "📦 Installing MCP server dependencies..."
    cd mcp-servers 2>&1 || true
    uv pip install --system \
        fastmcp \
        psycopg[binary,pool] \
        minio \
        pydantic \
        python-dotenv \
        redis \
        weasyprint \
        reportlab \
        httpx \
        email-validator \
        aiohttp \
        pytest \
        pytest-asyncio \
        pytest-cov \
        ruff \
        black 2>&1 || echo "⚠️  Some dependencies may have failed to install"
    cd /workspace 2>&1 || true
fi

# Set up Python path
export PYTHONPATH=/workspace/mcp-servers/src

# Verify Docker access
echo "📦 Verifying Docker access..."
if docker ps > /dev/null 2>&1; then
    echo "✅ Docker is accessible"
    docker --version 2>&1 || true
else
    echo "⚠️  Warning: Docker may not be accessible. Check docker socket mount."
fi

# Verify kubectl access
echo "☸️  Verifying kubectl access..."
if command -v kubectl > /dev/null 2>&1; then
    echo "✅ kubectl is installed"
    kubectl version --client 2>&1 || true
    if [ -f /home/vscode/.kube/config ]; then
        echo "✅ Kubernetes config found"
        kubectl cluster-info > /dev/null 2>&1 && echo "✅ Kubernetes cluster is accessible" || echo "⚠️  Cannot connect to cluster"
    else
        echo "⚠️  Kubernetes config not found at /home/vscode/.kube/config"
    fi
else
    echo "⚠️  kubectl not found"
fi

# Verify Python and dependencies
echo "🐍 Verifying Python environment..."
python3 --version 2>&1 || echo "⚠️  Python not found"
python3 -c "import fastmcp; print(f'✅ FastMCP version: {fastmcp.__version__}')" 2>&1 || echo "⚠️  FastMCP not found"
python3 -c "import psycopg; print('✅ psycopg installed')" 2>&1 || echo "⚠️  psycopg not found"
python3 -c "import minio; print('✅ minio installed')" 2>&1 || echo "⚠️  minio not found"
python3 -c "import redis; print('✅ redis installed')" 2>&1 || echo "⚠️  redis not found"

# Set up git
echo "📝 Git configuration..."
git config --global --add safe.directory /workspace 2>&1 || true

# Create .cursor directory
echo "🔗 Setting up MCP configuration..."
mkdir -p /home/vscode/.cursor 2>&1 || true

echo ""
echo "✨ DevContainer setup complete!"
echo ""
echo "Available commands:"
echo "  - cd mcp-servers && docker compose up -d    # Start MCP servers"
echo "  - kubectl get pods                          # Check Kubernetes pods"
echo "  - pytest                                    # Run tests"
echo "  - docker build -t myimage:tag .             # Build Docker images"
echo "  - kubectl apply -f k8s/                     # Deploy to Kubernetes"
echo ""

# Always exit successfully
exit 0
