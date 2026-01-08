# PDF Generator MCP Server - Usage Guide

## Overview

The PDF Generator MCP server provides PDF report generation from HTML templates with multi-tenant support. It supports variable substitution in templates and can return PDFs as base64 data or temporary file URLs.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "pdf-generator-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/pdf-generator/mcp",
      "description": "PDF Generator MCP Server - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-pdf-generator-server

# Server will be available at http://localhost:8003
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant:

**Tool:** `pdf_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `storage_path` (optional): Custom storage path for this tenant's PDFs

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "storage_path": "/custom/path"
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `pdf_generate_pdf` - Generate PDF

Generate a PDF report from an HTML template and content data.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `template` (required): HTML template string with `{{variable}}` placeholders
- `content` (required): Dictionary of data to fill into the template
- `filename` (optional): Filename for the PDF (default: auto-generated)
- `return_format` (optional): `'base64'` to return PDF as base64 data stream, `'url'` for temporary file URL (default: `'base64'`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "template": "<html><body><h1>{{title}}</h1><p>{{content}}</p></body></html>",
  "content": {
    "title": "My Report",
    "content": "This is the report content"
  },
  "return_format": "base64"
}
```

**Response (base64 format):**
```json
{
  "success": true,
  "filename": "report_my-tenant_abc123_20240101_120000.pdf",
  "data": "JVBERi0xLjQKJeLjz9MKMy...",
  "format": "base64",
  "size_bytes": 12345,
  "message": "PDF generated successfully as base64 data stream"
}
```

**Response (url format):**
```json
{
  "success": true,
  "file_id": "abc123def456",
  "url": "https://mcp.bionicaisolutions.com/pdf-generator/file/abc123def456",
  "filename": "report_my-tenant_abc123_20240101_120000.pdf",
  "expires_at": "2024-01-02T12:00:00",
  "message": "PDF generated successfully. Access via URL: https://..."
}
```

## Template Variables

Use `{{variable_name}}` syntax in your HTML templates. The content dictionary provides values for these variables.

**Example Template:**
```html
<!DOCTYPE html>
<html>
<head>
    <title>{{report_title}}</title>
    <style>
        body { font-family: Arial, sans-serif; }
        h1 { color: #333; }
    </style>
</head>
<body>
    <h1>{{report_title}}</h1>
    <p>Customer: {{customer_name}}</p>
    <p>Amount: ${{amount}}</p>
    <p>Date: {{date}}</p>
</body>
</html>
```

**Content Dictionary:**
```json
{
  "report_title": "Monthly Invoice",
  "customer_name": "John Doe",
  "amount": "1,234.56",
  "date": "January 1, 2024"
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: PDF_GENERATOR_TENANT_{TENANT_ID}_STORAGE_PATH
export PDF_GENERATOR_TENANT_1_STORAGE_PATH="/custom/path"
```

## Features

- **Multi-tenant**: Each tenant can have custom storage paths
- **HTML templates**: Use standard HTML with CSS styling
- **Variable substitution**: Use `{{variable}}` syntax for dynamic content
- **Multiple output formats**: Base64 data stream or temporary file URLs
- **Redis persistence**: Tenant configurations persist across restarts
- **Automatic cleanup**: Temporary files are cleaned up after retention period

## Resources

Access tenant information as resources:

- `pdf-generator://{tenant_id}/info` - Get tenant-specific information
- `pdf-generator://info` - Get server information including features and configuration

## Example Workflow

1. Register your tenant:
   ```
   pdf_register_tenant(tenant_id="my-tenant")
   ```

2. Generate a PDF:
   ```
   pdf_generate_pdf(
     tenant_id="my-tenant",
     template="<html><body><h1>{{title}}</h1></body></html>",
     content={"title": "My Report"},
     return_format="base64"
   )
   ```

3. Use the base64 data to save or display the PDF

## Notes

- Templates support full HTML and CSS
- PDFs are generated using WeasyPrint (primary) or ReportLab (fallback)
- Default file retention: 24 hours
- Temporary files are stored in `/tmp/pdf-reports` by default
- Base64 format is recommended for immediate use
- URL format is useful for sharing or downloading later
- Filenames are auto-generated if not provided


