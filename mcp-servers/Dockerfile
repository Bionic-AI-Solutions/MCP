# Multi-stage build for MCP servers
FROM python:3.12-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies (including fastmcp)
RUN uv pip install --system fastmcp psycopg[binary,pool] minio pydantic python-dotenv redis

# Calculator stage
FROM base as calculator
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/calculator/server.py", "--transport", "http", "--port", "8000", "--host", "0.0.0.0"]

# Postgres stage
FROM base as postgres
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/postgres/server.py", "--transport", "http", "--port", "8001", "--host", "0.0.0.0"]

# MinIO stage
FROM base as minio
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/minio/server.py", "--transport", "http", "--port", "8002", "--host", "0.0.0.0"]

