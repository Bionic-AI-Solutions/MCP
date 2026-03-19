---
name: pdf
description: Generate PDF documents from HTML content via the PDF Generator MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<generate|get> [--tenant <id>]"
---

# PDF Generator MCP Server

Server: `pdf-generator` at `pdf-generator/mcp` (stateful transport)
Alternate domain: `mcp.bionicaisolutions.com`
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `pdf_generate_pdf` | `tenant_id, html_content, options?` | Generate a PDF from HTML |
| `pdf_get_pdf_file` | `tenant_id, file_id` | Retrieve a previously generated PDF |
| `pdf_register_tenant` | `tenant_id, gotenberg_url` | Register a tenant with a Gotenberg URL |

## Usage Examples

Generate a PDF from HTML:
```bash
~/.claude/bin/mcp-rpc call pdf-generator pdf_generate_pdf '{"tenant_id": "base", "html_content": "<html><body><h1>Invoice #123</h1><p>Total: $500</p></body></html>"}'
```

Retrieve a generated PDF by file_id:
```bash
~/.claude/bin/mcp-rpc call pdf-generator pdf_get_pdf_file '{"tenant_id": "base", "file_id": "<file_id_from_generate>"}'
```

Generate with options (page size, margins):
```bash
~/.claude/bin/mcp-rpc call pdf-generator pdf_generate_pdf '{"tenant_id": "base", "html_content": "<html><body><h1>Report</h1></body></html>", "options": {"paperWidth": 8.5, "paperHeight": 11, "marginTop": 1}}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default connection.
- Register additional tenants with `pdf_register_tenant` or via K8s secret `mcp-pdf-generator-tenants`.
- The generate call returns a `file_id` that can be used with `pdf_get_pdf_file` to retrieve the PDF.
- PDF content is returned as base64-encoded data.
