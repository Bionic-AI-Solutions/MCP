# MCP (Model Context Protocol) Servers Collection

A collection of Model Context Protocol servers for various AI development tools and services.

## Contents

### mcp-servers/
FastMCP-based MCP servers with Docker support:
- **Calculator** - Basic arithmetic operations
- **Postgres** - Multi-tenant PostgreSQL database operations
- **MinIO** - Multi-tenant MinIO object storage operations

See [mcp-servers/README.md](mcp-servers/README.md) for detailed documentation.

### mcp-nginx/
Nginx reverse proxy configuration for external access to MCP servers.

### context7-mcp/
Context7 MCP server implementation.

### fastmcp/
FastMCP framework source code and documentation.

### mcp-ai/
MCP AI server deployment guides.

## Quick Start

### MCP Servers (Calculator, Postgres, MinIO)

```bash
cd mcp-servers
docker compose up -d
```

The servers will be available at:
- Calculator: `http://localhost:8000/mcp`
- Postgres: `http://localhost:8001/mcp`
- MinIO: `http://localhost:8002/mcp`

For external access via nginx:
- `https://mcp.bionicaisolutions.com/calculator/mcp`
- `https://mcp.bionicaisolutions.com/postgres/mcp`
- `https://mcp.bionicaisolutions.com/minio/mcp`

## Documentation

- [mcp-servers/README.md](mcp-servers/README.md) - Main MCP servers documentation
- [mcp-servers/DOCKER_SETUP.md](mcp-servers/DOCKER_SETUP.md) - Docker deployment guide
- [mcp-servers/QUICK_START.md](mcp-servers/QUICK_START.md) - Quick start guide
- [mcp-servers/NGINX_SETUP.md](mcp-servers/NGINX_SETUP.md) - Nginx configuration

## License

Apache-2.0

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

