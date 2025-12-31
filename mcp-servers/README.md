# MCP Servers and Clients

This project provides MCP (Model Context Protocol) servers and clients built with [FastMCP](https://gofastmcp.com) for:

1. **Calculator** - Basic arithmetic operations
2. **Postgres** - Multi-tenant PostgreSQL database operations
3. **Minio** - Multi-tenant MinIO object storage operations

## Features

- ✅ Built with FastMCP 2.0 for production-ready MCP servers
- ✅ Multi-tenant support for Postgres and Minio
- ✅ Connection pooling for efficient resource management
- ✅ Comprehensive tool sets for database and object storage operations
- ✅ Example clients and usage scripts
- ✅ Type-safe with Pydantic models

## Installation

```bash
# Using uv (recommended)
uv pip install -e .

# Or using pip
pip install -e .
```

## Quick Start

### Calculator Server

The simplest server - no configuration needed:

```bash
# Run the calculator server
fastmcp run src/mcp_servers/calculator/server.py

# Or using the script
mcp-calculator-server
```

**Available Tools:**
- `add` - Add two numbers
- `subtract` - Subtract b from a
- `multiply` - Multiply two numbers
- `divide` - Divide a by b
- `power` - Raise base to the power of exponent
- `sqrt` - Calculate square root
- `modulo` - Calculate modulo (remainder)

### Postgres Server (Multi-tenant)

Configure tenants via environment variables or register them programmatically:

```bash
# Set environment variables for tenant configurations
export POSTGRES_TENANT_1_HOST=localhost
export POSTGRES_TENANT_1_PORT=5432
export POSTGRES_TENANT_1_DB=mydb
export POSTGRES_TENANT_1_USER=postgres
export POSTGRES_TENANT_1_PASSWORD=password

# Optional: Connection pool settings
export POSTGRES_TENANT_1_MIN_POOL_SIZE=2
export POSTGRES_TENANT_1_MAX_POOL_SIZE=10
export POSTGRES_TENANT_1_SSL=false

# Run the postgres server
fastmcp run src/mcp_servers/postgres/server.py

# Or using the script
mcp-postgres-server
```

**Available Tools:**
- `execute_query` - Execute SQL queries
- `list_tables` - List tables in a schema
- `describe_table` - Get table schema information
- `register_tenant` - Register a new tenant configuration

### Minio Server (Multi-tenant)

Configure tenants via environment variables or register them programmatically:

```bash
# Set environment variables for tenant configurations
export MINIO_TENANT_1_ENDPOINT=localhost:9000
export MINIO_TENANT_1_ACCESS_KEY=minioadmin
export MINIO_TENANT_1_SECRET_KEY=minioadmin123
export MINIO_TENANT_1_SECURE=false
export MINIO_TENANT_1_REGION=us-east-1

# Run the minio server
fastmcp run src/mcp_servers/minio/server.py

# Or using the script
mcp-minio-server
```

**Available Tools:**
- `list_buckets` - List all buckets
- `create_bucket` - Create a new bucket
- `delete_bucket` - Delete a bucket
- `bucket_exists` - Check if a bucket exists
- `list_objects` - List objects in a bucket
- `upload_object` - Upload an object
- `download_object` - Download an object
- `delete_object` - Delete an object
- `register_tenant` - Register a new tenant configuration

## Client Usage

### Using the Client Library

```python
from fastmcp import Client

async with Client("src/mcp_servers/calculator/server.py") as client:
    result = await client.call_tool("add", {"a": 10, "b": 5})
    print(result.content[0].text)  # "15.0"
```

### Running Examples

```bash
# Calculator example
python examples/calculator_example.py

# Postgres example (requires PostgreSQL running)
python examples/postgres_example.py

# Minio example (requires MinIO running)
python examples/minio_example.py
```

## Project Structure

```
mcp-servers/
├── src/
│   └── mcp_servers/
│       ├── __init__.py
│       ├── calculator/
│       │   ├── __init__.py
│       │   ├── server.py      # Calculator MCP server
│       │   └── client.py       # Example client
│       ├── postgres/
│       │   ├── __init__.py
│       │   ├── server.py       # Postgres MCP server
│       │   ├── client.py       # Example client
│       │   └── tenant_manager.py  # Multi-tenant connection management
│       └── minio/
│           ├── __init__.py
│           ├── server.py       # MinIO MCP server
│           ├── client.py       # Example client
│           └── tenant_manager.py  # Multi-tenant connection management
├── examples/
│   ├── calculator_example.py
│   ├── postgres_example.py
│   └── minio_example.py
├── tests/
├── pyproject.toml
└── README.md
```

## Multi-Tenant Support

Both Postgres and Minio servers support multi-tenant operations. Tenants can be configured in two ways:

### 1. Environment Variables

Use the pattern: `{SERVICE}_TENANT_{ID}_{CONFIG_KEY}`

**Postgres Example:**
```bash
export POSTGRES_TENANT_1_HOST=localhost
export POSTGRES_TENANT_1_PORT=5432
export POSTGRES_TENANT_1_DB=mydb
export POSTGRES_TENANT_1_USER=postgres
export POSTGRES_TENANT_1_PASSWORD=password

export POSTGRES_TENANT_2_HOST=another-host
export POSTGRES_TENANT_2_PORT=5432
export POSTGRES_TENANT_2_DB=otherdb
export POSTGRES_TENANT_2_USER=postgres
export POSTGRES_TENANT_2_PASSWORD=password
```

**MinIO Example:**
```bash
export MINIO_TENANT_1_ENDPOINT=localhost:9000
export MINIO_TENANT_1_ACCESS_KEY=minioadmin
export MINIO_TENANT_1_SECRET_KEY=minioadmin123
export MINIO_TENANT_1_SECURE=false
```

### 2. Programmatic Registration

Use the `register_tenant` tool to register tenants at runtime:

```python
await client.call_tool("register_tenant", {
    "tenant_id": "1",
    "host": "localhost",
    "port": 5432,
    "database": "mydb",
    "user": "postgres",
    "password": "password",
})
```

## Development

### Running Tests

```bash
pytest
```

### Code Quality

```bash
# Format code
black src/ examples/

# Lint code
ruff check src/ examples/
```

## Setting Up for Cursor IDE

### Step 1: Install Dependencies

Run the setup script to create a virtual environment and install dependencies:

```bash
cd /workspace/mcp-servers
./setup_for_cursor.sh
```

**Note**: If you get an error about `python3-venv`, install it first:
```bash
sudo apt install python3.12-venv
```

### Step 2: Configure Cursor

Copy the configuration file to Cursor's config directory:

```bash
cp /workspace/mcp-servers/mcp_client_config_cursor_local.json ~/.cursor/mcp.json
```

Or manually edit `~/.cursor/mcp.json` and add:

```json
{
  "mcpServers": {
    "calculator-mcp": {
      "command": "/workspace/mcp-servers/.venv/bin/fastmcp",
      "args": ["run", "/workspace/mcp-servers/src/mcp_servers/calculator/server.py"],
      "cwd": "/workspace/mcp-servers",
      "env": {
        "PYTHONPATH": "/workspace/mcp-servers/src"
      }
    },
    "postgres-mcp": {
      "command": "/workspace/mcp-servers/.venv/bin/fastmcp",
      "args": ["run", "/workspace/mcp-servers/src/mcp_servers/postgres/server.py"],
      "cwd": "/workspace/mcp-servers",
      "env": {
        "PYTHONPATH": "/workspace/mcp-servers/src",
        "POSTGRES_TENANT_1_HOST": "localhost",
        "POSTGRES_TENANT_1_PORT": "5432",
        "POSTGRES_TENANT_1_DB": "mydb",
        "POSTGRES_TENANT_1_USER": "postgres",
        "POSTGRES_TENANT_1_PASSWORD": "password"
      }
    },
    "minio-mcp": {
      "command": "/workspace/mcp-servers/.venv/bin/fastmcp",
      "args": ["run", "/workspace/mcp-servers/src/mcp_servers/minio/server.py"],
      "cwd": "/workspace/mcp-servers",
      "env": {
        "PYTHONPATH": "/workspace/mcp-servers/src",
        "MINIO_TENANT_1_ENDPOINT": "localhost:9000",
        "MINIO_TENANT_1_ACCESS_KEY": "minioadmin",
        "MINIO_TENANT_1_SECRET_KEY": "minioadmin123",
        "MINIO_TENANT_1_SECURE": "false"
      }
    }
  }
}
```

**Important**: Update the paths in the config if you're installing in a different location!

### Step 3: Restart Cursor

After updating the config, restart Cursor completely (not just reload).

### Troubleshooting

- **"fastmcp: command not found"**: Make sure you ran `./setup_for_cursor.sh` to create the virtual environment
- **"Module not found"**: Check that `PYTHONPATH` is set correctly in the config
- **"File not found"**: Use absolute paths (starting with `/`) in the config
- **Still having issues**: Test the server manually:
  ```bash
  cd /workspace/mcp-servers
  .venv/bin/fastmcp run src/mcp_servers/calculator/server.py
  ```

For remote access via HTTP/SSE, see `QUICK_START.md` and `NGINX_SETUP.md`.

## Available Tools

See `AVAILABLE_TOOLS.md` for a complete list of all available tools for each server.

## Docker Deployment

The MCP servers are fully dockerized and can be run using Docker Compose.

### Quick Start with Docker

```bash
cd /workspace/mcp-servers

# Copy environment template
cp .env.example .env
# Edit .env with your configuration

# Build and start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Services

- **Calculator Server**: `http://localhost:8000`
- **Postgres Server**: `http://localhost:8001`
- **MinIO Server**: `http://localhost:8002`
- **Redis**: `localhost:6379` (for tenant configuration storage)

For detailed Docker setup instructions, see [DOCKER_SETUP.md](DOCKER_SETUP.md).

## License

Apache-2.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

