# Instructions to Commit and Push MCP Servers

The `mcp-servers` and `mcp-nginx` folders have been added to the repository. To commit and push them to GitHub, run:

```bash
cd /workspace/MCP
./commit_and_push.sh
```

Or manually:

```bash
cd /workspace/MCP

# Initialize git if needed
git init

# Set remote
git remote add origin https://github.com/Bionic-AI-Solutions/MCP.git
# Or update if it exists:
# git remote set-url origin https://github.com/Bionic-AI-Solutions/MCP.git

# Configure git user
git config user.name "Bionic AI Solutions"
git config user.email "info@bionicaisolutions.com"

# Add the folders
git add mcp-servers/ mcp-nginx/

# Commit
git commit -m "Add MCP servers (Calculator, Postgres, MinIO) with Docker support and nginx configuration

- Added FastMCP-based MCP servers for Calculator, Postgres, and MinIO
- Multi-tenant support for Postgres and MinIO
- Docker Compose setup with Redis for tenant configuration storage
- Nginx reverse proxy configuration for external access
- Cursor IDE configuration files for local and remote access
- Comprehensive documentation and setup guides"

# Push
git branch -M main
git push -u origin main
```

## What's Being Committed

### mcp-servers/
- FastMCP-based MCP servers (Calculator, Postgres, MinIO)
- Docker Compose configuration
- Cursor IDE configuration files
- Documentation and setup guides

### mcp-nginx/
- Nginx reverse proxy configuration
- SSL/TLS support for external access

## External Endpoints

After deployment, the servers are available at:
- `https://mcp.bionicaisolutions.com/calculator/mcp`
- `https://mcp.bionicaisolutions.com/postgres/mcp`
- `https://mcp.bionicaisolutions.com/minio/mcp`


