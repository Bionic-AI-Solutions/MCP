# Nano Banana MCP Server - Usage Guide

## Overview

The Nano Banana MCP server provides AI image generation and editing using Google's Gemini API with multi-tenant support. Each tenant uses their own Gemini API key.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "nano-banana-mcp-remote": {
      "url": "https://mcp.baisoln.com/nano-banana/mcp",
      "description": "Nano Banana MCP Server - AI image generation with Gemini API - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-nano-banana-server

# Server will be available at http://localhost:8008
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your Gemini API key:

**Tool:** `nb_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `gemini_api_key` (required): Your Google Gemini API key from [Google AI Studio](https://ai.google.com/studio/)
- `model` (optional): Gemini model to use (default: `"gemini-2.0-flash-exp"`)
- `max_concurrent_requests` (optional): Max concurrent requests per tenant (default: `10`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "gemini_api_key": "your-gemini-api-key-here",
  "model": "gemini-2.0-flash-exp",
  "max_concurrent_requests": 10
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `nb_generate_image` - Generate Images

Generate images from text prompts using Gemini AI.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `prompt` (required): Text description of the image to generate
- `width` (optional): Image width in pixels (default: `1024`)
- `height` (optional): Image height in pixels (default: `1024`)
- `output_path` (optional): File path to save the image

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "prompt": "A futuristic robot holding a banana in a cyberpunk cityscape",
  "width": 1024,
  "height": 1024
}
```

**Response:**
```json
{
  "success": true,
  "image_data": "base64-encoded-image-data...",
  "output_path": "/path/to/saved/image.png",
  "width": 1024,
  "height": 1024,
  "format": "png"
}
```

### 2. `nb_edit_image` - Edit Images

Edit existing images using AI prompts.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `image_data` (required): Base64-encoded image string OR file path to existing image
- `prompt` (required): Description of the edit to make
- `output_path` (optional): File path to save the edited image

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "image_data": "/path/to/image.png",
  "prompt": "Add a sunset in the background and make the colors more vibrant"
}
```

**Response:**
```json
{
  "success": true,
  "image_data": "base64-encoded-edited-image...",
  "output_path": "/path/to/edited/image.png"
}
```

### 3. `nb_generate_content` - Generate Text Content

Generate text content using Gemini AI.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `prompt` (required): Text prompt for content generation
- `temperature` (optional): Sampling temperature 0.0-1.0 (default: `0.7`)
- `max_tokens` (optional): Maximum tokens to generate

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "prompt": "Write a short story about a robot and a banana",
  "temperature": 0.7
}
```

**Response:**
```json
{
  "success": true,
  "text": "Generated story text here...",
  "model": "gemini-2.0-flash-exp"
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: NANO_BANANA_TENANT_{TENANT_ID}_GEMINI_API_KEY
export NANO_BANANA_TENANT_1_GEMINI_API_KEY="your-api-key"
export NANO_BANANA_TENANT_1_MODEL="gemini-2.0-flash-exp"
export NANO_BANANA_TENANT_1_MAX_CONCURRENT="10"
```

## Features

- **Multi-tenant**: Each tenant uses their own Gemini API key
- **Concurrency control**: Semaphore-based limiting per tenant
- **Redis persistence**: Tenant configurations persist across restarts
- **Health check**: Available at `/health` endpoint

## Resources

Access tenant information as resources:

- `nano-banana://{tenant_id}/info` - Get tenant-specific information
- `nano-banana://info` - Get server information

## Example Workflow

1. Register your tenant:
   ```
   nb_register_tenant(tenant_id="my-tenant", gemini_api_key="...")
   ```

2. Generate an image:
   ```
   nb_generate_image(tenant_id="my-tenant", prompt="A robot with a banana")
   ```

3. Edit the image:
   ```
   nb_edit_image(tenant_id="my-tenant", image_data="base64...", prompt="Make it more colorful")
   ```

## Health Check

Check server status:
```bash
curl https://mcp.baisoln.com/nano-banana/health
```

Response:
```json
{
  "status": "healthy",
  "service": "nano-banana-mcp-server",
  "version": "1.0.0",
  "tenant_manager_initialized": true
}
```

## Notes

- Get your Gemini API key from [Google AI Studio](https://ai.google.com/studio/)
- Default model: `gemini-2.0-flash-exp`
- Images are returned as base64-encoded strings
- Tenant configurations are stored in Redis (DB 6)
- Each tenant has independent concurrency limits

The server is ready to use once you register a tenant with your Gemini API key.

