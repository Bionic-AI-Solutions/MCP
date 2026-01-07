# Multi-stage build for MCP servers
FROM python:3.12-slim as base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies (including fastmcp)
RUN uv pip install --system fastmcp psycopg[binary,pool] minio pydantic python-dotenv redis weasyprint reportlab httpx email-validator aiohttp meilisearch

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

# PDF Generator stage
FROM base as pdf-generator
# Install additional system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    libpango1.0-dev \
    libcairo2-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    libharfbuzz-dev \
    libraqm-dev \
    libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
ENV PDF_TEMP_DIR=/tmp/pdf-reports
ENV PDF_RETENTION_HOURS=24
EXPOSE 8003
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/pdf-generator/server.py", "--transport", "http", "--port", "8003", "--host", "0.0.0.0"]

# FFmpeg stage
FROM base as ffmpeg
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/ffmpeg/server.py", "--transport", "http", "--port", "8004", "--host", "0.0.0.0"]

# Mail stage
FROM base as mail
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8005
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8005/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/mail/server.py", "--transport", "http", "--port", "8005", "--host", "0.0.0.0"]

# OpenProject stage
FROM base as openproject
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8006
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8006/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/openproject/server.py", "--transport", "http", "--port", "8006", "--host", "0.0.0.0"]

# MeiliSearch stage
FROM base as meilisearch
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE 8007
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8007/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/meilisearch/server.py", "--transport", "http", "--port", "8007", "--host", "0.0.0.0"]

