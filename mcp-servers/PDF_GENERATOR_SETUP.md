# PDF Generator MCP Server - Setup Complete

## What Was Created

A complete PDF Generator MCP server that:
- ✅ Generates PDF reports from HTML templates
- ✅ Supports base64 data stream or temporary file URLs
- ✅ Multi-tenant support with Redis persistence
- ✅ Docker containerization
- ✅ Remote access via HTTPS with HTTP and SSE protocols

## Server Details

- **Port**: 8003
- **Local URL**: `http://localhost:8003/mcp`
- **Remote URL**: `https://mcp.bionicaisolutions.com/pdf-generator/mcp`
- **Redis DB**: 2

## Files Created/Modified

### Server Code
- `src/mcp_servers/pdf-generator/server.py` - Main server with PDF generation tools
- `src/mcp_servers/pdf-generator/tenant_manager.py` - Tenant management
- `src/mcp_servers/pdf-generator/__init__.py` - Package initialization
- `src/mcp_servers/pdf-generator/client.py` - Example client code
- `src/mcp_servers/pdf-generator/README.md` - Server documentation

### Configuration
- `Dockerfile` - Added PDF generator stage with WeasyPrint dependencies
- `docker-compose.yml` - Added PDF generator service
- `pyproject.toml` - Added weasyprint and reportlab dependencies
- `mcp-nginx/nginx.conf` - Added nginx configuration for HTTP and SSE
- `mcp_client_config_cursor_remote.json` - Added remote client config

### Examples
- `examples/pdf_generator_example.py` - Usage examples

## Dependencies Added

### Python Packages
- `weasyprint>=60.0` - Primary PDF generation (HTML to PDF)
- `reportlab>=4.0.0` - Fallback PDF generation

### System Packages (Docker)
- `libpango-1.0-0` - Text rendering
- `libpangoft2-1.0-0` - Font handling
- `libharfbuzz0b` - Text shaping
- `libcairo2` - Graphics rendering
- `libgdk-pixbuf2.0-0` - Image handling
- `libffi-dev` - Foreign function interface
- `shared-mime-info` - MIME type detection

## Available Tools

### `generate_pdf`
Generate a PDF report from an HTML template and content data.

**Parameters:**
- `tenant_id` (str): Tenant identifier
- `template` (str): HTML template with `{{variable}}` placeholders
- `content` (dict): Data dictionary for template variables
- `filename` (str, optional): PDF filename
- `return_format` (str): 'base64' or 'url' (default: 'base64')

**Returns:**
- Base64 format: `{"success": true, "data": "...", "filename": "...", "size_bytes": ...}`
- URL format: `{"success": true, "url": "...", "file_id": "...", "expires_at": "..."}`

### `register_tenant`
Register a tenant configuration.

**Parameters:**
- `tenant_id` (str): Unique tenant identifier
- `storage_path` (str, optional): Custom storage path

## Quick Start

### 1. Build and Start

```bash
cd /workspace/MCP/mcp-servers
docker compose build mcp-pdf-generator-server
docker compose up -d mcp-pdf-generator-server
```

### 2. Verify Health

```bash
curl http://localhost:8003/health
```

### 3. Test Local Endpoint

```bash
curl -X POST http://localhost:8003/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test", "version": "1.0"}
    },
    "id": 1
  }'
```

### 4. Reload Nginx

```bash
docker ps | grep nginx
docker exec <nginx-container> nginx -s reload
```

### 5. Test Remote Endpoint

```bash
curl -X POST https://mcp.bionicaisolutions.com/pdf-generator/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {"name": "test", "version": "1.0"}
    },
    "id": 1
  }'
```

## Usage Example

See `examples/pdf_generator_example.py` for a complete example.

Quick example:
```python
from fastmcp import Client

async with Client("https://mcp.bionicaisolutions.com/pdf-generator/mcp") as client:
    result = await client.call_tool(
        "generate_pdf",
        {
            "tenant_id": "my-tenant",
            "template": "<html><body><h1>{{title}}</h1></body></html>",
            "content": {"title": "My Report"},
            "return_format": "base64"
        }
    )
    # Decode base64 PDF data
    pdf_data = base64.b64decode(result['data'])
```

## Template Syntax

Use `{{variable_name}}` in your HTML templates:

```html
<!DOCTYPE html>
<html>
<head><title>{{title}}</title></head>
<body>
    <h1>{{title}}</h1>
    <p>Customer: {{customer_name}}</p>
    <p>Amount: ${{amount}}</p>
</body>
</html>
```

## Configuration

### Environment Variables

- `PDF_TEMP_DIR`: Temporary PDF storage (default: `/tmp/pdf-reports`)
- `PDF_RETENTION_HOURS`: File retention time (default: 24)

### Volume

PDF files are stored in a Docker volume: `pdf-reports`

## Troubleshooting

### Import Errors
- Ensure all dependencies are installed: `docker compose build --no-cache mcp-pdf-generator-server`

### PDF Generation Fails
- Check server logs: `docker compose logs mcp-pdf-generator-server`
- Verify WeasyPrint dependencies are installed
- Check template HTML is valid

### Nginx 502
- Verify server is running: `docker ps | grep pdf-generator`
- Check nginx logs: `docker logs <nginx-container>`
- Verify upstream configuration

## Next Steps

1. Test the server locally
2. Test via remote URL
3. Customize templates for your use case
4. Implement file URL serving (currently returns placeholder URL)
5. Add template management features if needed

