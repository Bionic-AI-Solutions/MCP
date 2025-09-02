# Context7 MCP Server - Docker Setup Guide

This guide explains how to run the Context7 MCP server in Docker containers for easy deployment and management.

## Prerequisites

- Docker installed and running
- Docker Compose installed
- Git (to clone the repository)

## Quick Start

### 1. Clone and Navigate to the Repository

```bash
git clone <repository-url>
cd context7-1
```

### 2. Build and Start the Server

```bash
# Make the helper script executable (first time only)
chmod +x scripts/docker-helper.sh

# Build the Docker image
./scripts/docker-helper.sh build

# Start the server
./scripts/docker-helper.sh start
```

### 3. Verify the Server is Running

```bash
# Check status
./scripts/docker-helper.sh status

# View logs
./scripts/docker-helper.sh logs
```

## Docker Helper Script Commands

The `scripts/docker-helper.sh` script provides easy management commands:

| Command | Description |
|---------|-------------|
| `build` | Build the Docker image |
| `start` | Start the server using docker-compose |
| `stop` | Stop the server |
| `restart` | Restart the server |
| `logs` | View server logs |
| `status` | Check server status |
| `cleanup` | Clean up Docker resources |
| `help` | Show help message |

## Manual Docker Commands

If you prefer to use Docker commands directly:

### Build the Image

```bash
docker build -t context7-mcp:latest .
```

### Start with Docker Compose

```bash
docker-compose up -d
```

### Stop the Server

```bash
docker-compose down
```

### View Logs

```bash
docker-compose logs -f context7-mcp
```

## Server Endpoints

Once running, the server provides these endpoints:

- **MCP Endpoint**: `http://localhost:8080/mcp`
- **SSE Endpoint**: `http://localhost:8080/sse`
- **Health Check**: `http://localhost:8080/ping`

## Configuration

### Environment Variables

Create a `config/.env` file based on `config/env.example`:

```bash
cp config/env.example config/.env
```

Edit the `.env` file to set your configuration:

```env
# Context7 API Key (optional - for higher rate limits)
CONTEXT7_API_KEY=your_actual_api_key_here

# Server Configuration
NODE_ENV=production
PORT=8080

# Proxy Configuration (if needed)
# HTTP_PROXY=http://proxy:port
# HTTPS_PROXY=http://proxy:port
```

### API Key

To get a Context7 API key:
1. Visit [context7.com/dashboard](https://context7.com/dashboard)
2. Create an account or sign in
3. Generate an API key
4. Add it to your `.env` file

## MCP Client Configuration

### Cursor Configuration

Add this to your `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "context7": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### VS Code Configuration

Add this to your VS Code MCP configuration:

```json
{
  "mcpServers": {
    "context7": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Check what's using port 8080
   lsof -i :8080
   
   # Or change the port in docker-compose.yml
   ports:
     - "8081:8080"  # Use port 8081 on host
   ```

2. **Docker Not Running**
   ```bash
   # Check Docker status
   docker info
   
   # Start Docker if needed
   sudo systemctl start docker
   ```

3. **Permission Issues**
   ```bash
   # Make script executable
   chmod +x scripts/docker-helper.sh
   
   # Or run with sudo if needed
   sudo ./scripts/docker-helper.sh start
   ```

### Health Checks

The server includes health checks. You can test manually:

```bash
# Test health endpoint
curl http://localhost:8080/ping

# Test MCP endpoint
curl http://localhost:8080/mcp
```

### Logs and Debugging

```bash
# View real-time logs
./scripts/docker-helper.sh logs

# View container details
docker-compose ps

# Check container resources
docker stats context7-mcp-server
```

## Production Deployment

For production use, consider:

1. **Environment Variables**: Use proper environment variable management
2. **Secrets**: Store API keys securely (e.g., Docker secrets, Kubernetes secrets)
3. **Monitoring**: Add monitoring and alerting
4. **Scaling**: Use Docker Swarm or Kubernetes for scaling
5. **Backup**: Implement backup strategies for configuration

## Security Considerations

1. **API Keys**: Never commit API keys to version control
2. **Network Access**: Restrict network access to necessary ports only
3. **Container Security**: Run containers as non-root users when possible
4. **Updates**: Regularly update the base image and dependencies

## Support

For issues and questions:
- Check the [main README](../README.md)
- Review the [Context7 documentation](https://context7.com)
- Check the [Remote Access Guide](./REMOTE_ACCESS.md) for network access
- Open an issue in the repository
