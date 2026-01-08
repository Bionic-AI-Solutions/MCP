# MCP Servers Documentation

This directory contains usage guides for all MCP servers deployed on Kubernetes.

## Available MCP Servers

### Core Services

1. **[Calculator](./calculator.md)** - Basic arithmetic operations
   - Simple, stateless server for mathematical calculations
   - Tools: Addition, subtraction, multiplication, division, power, square root, modulo

2. **[PostgreSQL](./postgres.md)** - Database operations with multi-tenant support
   - Connect to PostgreSQL databases
   - Tools: Execute queries, list tables, describe tables, register tenants

3. **[MinIO](./minio.md)** - Object storage with multi-tenant support
   - S3-compatible object storage operations
   - Tools: Bucket management, object upload/download, list operations

### Content Generation

4. **[PDF Generator](./pdf-generator.md)** - PDF report generation from HTML templates
   - Generate PDFs from HTML templates with variable substitution
   - Tools: Generate PDF, register tenants
   - Supports base64 output or temporary file URLs

5. **[FFmpeg](./ffmpeg.md)** - Video and audio processing
   - Comprehensive video/audio processing using FFmpeg
   - Tools: Convert formats, extract audio, merge videos, add subtitles, trim, resize, extract frames

6. **[Nano Banana](./nano-banana.md)** - AI image generation with Gemini API
   - Generate and edit images using Google Gemini AI
   - Tools: Generate images, edit images, generate text content
   - Multi-tenant with per-tenant Gemini API keys

### Communication & Collaboration

7. **[Mail](./mail.md)** - Email sending with multi-tenant support
   - Send emails via mail service API
   - Tools: Send email, send with attachments, bulk sending
   - Supports HTML and text emails

8. **[OpenProject](./openproject.md)** - Project management operations
   - Comprehensive OpenProject API integration
   - Tools: Projects, work packages, users, attachments, relations, hierarchy management
   - Extensive project management capabilities

### Search & Discovery

9. **[MeiliSearch](./meilisearch.md)** - Search engine with multi-tenant support
   - Full-text search engine operations
   - Tools: Index management, document operations, search with filters and sorting

## Quick Start

1. Choose the MCP server you want to use
2. Read the corresponding usage guide
3. Configure the server (if multi-tenant, register a tenant first)
4. Start using the tools!

## Connection Information

All servers are accessible via HTTPS:

- **Calculator**: `https://mcp.bionicaisolutions.com/calculator/mcp`
- **PostgreSQL**: `https://mcp.bionicaisolutions.com/postgres/mcp`
- **MinIO**: `https://mcp.bionicaisolutions.com/minio/mcp`
- **PDF Generator**: `https://mcp.bionicaisolutions.com/pdf-generator/mcp`
- **FFmpeg**: `https://mcp.bionicaisolutions.com/ffmpeg/mcp`
- **Mail**: `https://mcp.bionicaisolutions.com/mail/mcp`
- **OpenProject**: `https://mcp.baisoln.com/openproject/mcp`
- **MeiliSearch**: `https://mcp.baisoln.com/meilisearch/mcp`
- **Nano Banana**: `https://mcp.baisoln.com/nano-banana/mcp`

## Multi-Tenant Servers

The following servers support multi-tenancy (require tenant registration):

- PostgreSQL
- MinIO
- PDF Generator
- Mail
- MeiliSearch
- Nano Banana

Each multi-tenant server:
- Stores tenant configurations in Redis
- Supports environment variable configuration
- Provides tenant registration tools
- Isolates data per tenant

## Health Checks

All servers provide health check endpoints:

```bash
curl https://mcp.baisoln.com/{server-name}/health
```

## Need Help?

Refer to the individual usage guides for detailed information about each server's tools, parameters, and examples.


