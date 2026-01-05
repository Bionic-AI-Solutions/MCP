# DevContainer Dockerfile for MCP Servers Development
FROM python:3.12-slim

# Install system dependencies in stages for better caching
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gnupg \
    lsb-release \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install build tools and libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install ffmpeg (can be slow, but needed for ffmpeg server)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install editors (optional, can be removed if not needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    nano \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (will use host's docker daemon via mount)
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl (will use host's kubectl via mount, but install as fallback)
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/kubectl-fallback || true

# Install uv for faster dependency management
RUN pip install --no-cache-dir uv

# Create vscode user (matching devcontainer default)
RUN groupadd -r vscode && useradd -r -g vscode -m -s /bin/bash vscode

# Set up workspace directory
WORKDIR /workspace

# Copy dependency files for mcp-servers
COPY mcp-servers/pyproject.toml /workspace/mcp-servers/

# Install Python dependencies
WORKDIR /workspace/mcp-servers
RUN uv pip install --system \
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
    "pytest>=8.3.3" \
    "pytest-asyncio>=1.2.0" \
    "pytest-cov>=6.1.1" \
    "ruff>=0.12.8" \
    "black>=24.0.0"

# Set Python path
ENV PYTHONPATH=/workspace/mcp-servers/src
ENV PATH="/usr/local/bin:${PATH}"

# Create .kube directory for vscode user
RUN mkdir -p /home/vscode/.kube && chown -R vscode:vscode /home/vscode

# Set working directory back to workspace root
WORKDIR /workspace

# Switch to vscode user
USER vscode

# Default command
CMD ["/bin/bash"]

