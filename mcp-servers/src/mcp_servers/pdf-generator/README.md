# PDF Generator MCP Server

A multi-tenant MCP server for generating PDF reports from HTML templates.

## Features

- Generate PDFs from HTML templates with variable substitution
- Support for base64 data stream or temporary file URLs
- Multi-tenant support with Redis persistence
- Automatic file cleanup after retention period

## Tools

### `generate_pdf`
Generate a PDF report from a template and content.

**Parameters:**
- `tenant_id` (str, required): Tenant identifier
- `template` (str, required): HTML template with `{{variable}}` placeholders
- `content` (dict, required): Dictionary of data to fill into the template
- `filename` (str, optional): Filename for the PDF (default: auto-generated)
- `return_format` (str, optional): 'base64' or 'url' (default: 'base64')

**Returns:**
- For `base64`: PDF data as base64-encoded string
- For `url`: Temporary file URL and file ID

### `register_tenant`
Register a new tenant configuration.

**Parameters:**
- `tenant_id` (str, required): Unique tenant identifier
- `storage_path` (str, optional): Custom storage path for this tenant's PDFs

## Usage Example

```python
from fastmcp import Client

async with Client("https://mcp.bionicaisolutions.com/pdf-generator/mcp") as client:
    result = await client.call_tool(
        "generate_pdf",
        {
            "tenant_id": "my-tenant",
            "template": "<html><body><h1>{{title}}</h1><p>{{content}}</p></body></html>",
            "content": {
                "title": "My Report",
                "content": "This is the report content"
            },
            "return_format": "base64"
        }
    )
```

## Template Variables

Use `{{variable_name}}` syntax in your HTML templates. The content dictionary provides values for these variables.

Example:
```html
<h1>{{title}}</h1>
<p>Customer: {{customer_name}}</p>
<p>Amount: ${{amount}}</p>
```

## Configuration

### Environment Variables

- `PDF_TEMP_DIR`: Directory for temporary PDF files (default: `/tmp/pdf-reports`)
- `PDF_RETENTION_HOURS`: Hours to keep temporary files (default: 24)

### Tenant Configuration

Tenants can be configured via:
1. Environment variables: `PDF_GENERATOR_TENANT_{TENANT_ID}_STORAGE_PATH`
2. MCP tool: `register_tenant`

## Dependencies

- `weasyprint`: Primary PDF generation library (HTML to PDF)
- `reportlab`: Fallback PDF generation library

## Docker Deployment

The server runs on port 8003 and is accessible via:
- Local: `http://localhost:8003/mcp`
- Remote: `https://mcp.bionicaisolutions.com/pdf-generator/mcp`

