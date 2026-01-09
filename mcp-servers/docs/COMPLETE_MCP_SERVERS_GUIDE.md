# Complete MCP Servers Guide

## Table of Contents

1. [Overview](#overview)
2. [Connection Information](#connection-information)
3. [Core Services](#core-services)
   - [Calculator](#1-calculator-mcp-server)
   - [PostgreSQL](#2-postgresql-mcp-server)
   - [MinIO](#3-minio-mcp-server)
4. [Content Generation](#content-generation)
   - [PDF Generator](#4-pdf-generator-mcp-server)
   - [FFmpeg](#5-ffmpeg-mcp-server)
   - [GenImage](#6-genimage-mcp-server)
   - [AI MCP Server](#7-ai-mcp-server)
5. [Communication & Collaboration](#communication--collaboration)
   - [Mail](#8-mail-mcp-server)
   - [OpenProject](#9-openproject-mcp-server)
6. [Search & Discovery](#search--discovery)
   - [MeiliSearch](#10-meilisearch-mcp-server)
7. [Multi-Tenant Architecture](#multi-tenant-architecture)
8. [Quick Reference](#quick-reference)

---

## Overview

This guide provides comprehensive documentation for all MCP (Model Context Protocol) servers deployed on Kubernetes. These servers provide various capabilities including database operations, object storage, content generation, AI services, communication, and search functionality.

All servers are accessible via HTTPS through Kong Ingress and support both HTTP and SSE (Server-Sent Events) protocols for real-time communication.

---

## Connection Information

All servers are accessible via HTTPS:

| Server | Remote URL | Local Port |
|--------|-----------|------------|
| Calculator | `https://mcp.bionicaisolutions.com/calculator/mcp` | 8000 |
| PostgreSQL | `https://mcp.bionicaisolutions.com/postgres/mcp` | 8001 |
| MinIO | `https://mcp.bionicaisolutions.com/minio/mcp` | 8002 |
| PDF Generator | `https://mcp.bionicaisolutions.com/pdf-generator/mcp` | 8003 |
| FFmpeg | `https://mcp.bionicaisolutions.com/ffmpeg/mcp` | 8004 |
| Mail | `https://mcp.bionicaisolutions.com/mail/mcp` | 8005 |
| OpenProject | `https://mcp.baisoln.com/openproject/mcp` | 8006 |
| MeiliSearch | `https://mcp.baisoln.com/meilisearch/mcp` | 8007 |
| GenImage | `https://mcp.baisoln.com/genimage/mcp` | 8008 |
| AI MCP Server | `https://mcp.baisoln.com/ai-mcp-server/mcp` | 8009 |

### Health Checks

All servers provide health check endpoints:

```bash
curl https://mcp.baisoln.com/{server-name}/health
```

---

## Core Services

### 1. Calculator MCP Server

#### Overview

The Calculator MCP server provides basic arithmetic operations. It's a simple, stateless server that performs mathematical calculations.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "calculator-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/calculator/mcp",
      "description": "Calculator MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-calculator-server
# Server available at http://localhost:8000
```

#### Available Tools

1. **`calc_add`** - Addition
   - Parameters: `a` (float), `b` (float)
   - Example: `calc_add(a=10, b=5)` → `15.0`

2. **`calc_subtract`** - Subtraction
   - Parameters: `a` (float), `b` (float)
   - Example: `calc_subtract(a=10, b=3)` → `7.0`

3. **`calc_multiply`** - Multiplication
   - Parameters: `a` (float), `b` (float)
   - Example: `calc_multiply(a=6, b=7)` → `42.0`

4. **`calc_divide`** - Division
   - Parameters: `a` (float), `b` (float)
   - Example: `calc_divide(a=20, b=4)` → `5.0`
   - Note: Raises error if b is zero

5. **`calc_power`** - Exponentiation
   - Parameters: `base` (float), `exponent` (float)
   - Example: `calc_power(base=2, exponent=8)` → `256.0`

6. **`calc_sqrt`** - Square Root
   - Parameters: `value` (float)
   - Example: `calc_sqrt(value=64)` → `8.0`

7. **`calc_modulo`** - Modulo
   - Parameters: `a` (float), `b` (float)
   - Example: `calc_modulo(a=17, b=5)` → `2.0`

#### Notes

- All operations return floating-point numbers
- Division by zero raises a `ValueError`
- Square root of negative numbers raises a `ValueError`
- The server is stateless and requires no configuration

---

### 2. PostgreSQL MCP Server

#### Overview

The PostgreSQL MCP server provides database operations with multi-tenant support. Each tenant can connect to their own PostgreSQL database instance.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "postgres-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/postgres/mcp",
      "description": "PostgreSQL MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-postgres-server
# Server available at http://localhost:8001
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "host": "localhost",
  "database": "mydb",
  "user": "postgres",
  "password": "password",
  "port": 5432,
  "min_pool_size": 2,
  "max_pool_size": 10,
  "ssl": false
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`pg_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `host`, `database`, `user`, `password`, `port` (optional), `min_pool_size` (optional), `max_pool_size` (optional), `ssl` (optional)

2. **`pg_execute_query`** - Execute SQL Query
   - Parameters: `tenant_id`, `query`, `params` (optional)
   - Example: `pg_execute_query(tenant_id="my-tenant", query="SELECT * FROM users WHERE age > %s", params=[18])`

3. **`pg_list_tables`** - List Tables
   - Parameters: `tenant_id`, `schema` (optional, default: "public")
   - Returns: List of tables with their types

4. **`pg_describe_table`** - Describe Table
   - Parameters: `tenant_id`, `table_name`, `schema` (optional)
   - Returns: Detailed table structure with columns, types, and constraints

#### Configuration via Environment Variables

```bash
export POSTGRES_TENANT_1_HOST="localhost"
export POSTGRES_TENANT_1_PORT="5432"
export POSTGRES_TENANT_1_DATABASE="mydb"
export POSTGRES_TENANT_1_USER="postgres"
export POSTGRES_TENANT_1_PASSWORD="password"
export POSTGRES_TENANT_1_SSL="false"
```

#### Features

- Multi-tenant: Each tenant connects to their own PostgreSQL database
- Connection pooling: Configurable connection pool per tenant
- Redis persistence: Tenant configurations persist across restarts (Redis DB 1)
- Parameterized queries: Support for safe parameterized SQL queries
- Schema introspection: List tables and describe table structures

---

### 3. MinIO MCP Server

#### Overview

The MinIO MCP server provides object storage operations with multi-tenant support. Each tenant can connect to their own MinIO instance or S3-compatible storage.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "minio-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/minio/mcp",
      "description": "MinIO MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-minio-server
# Server available at http://localhost:8002
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "endpoint": "localhost:9000",
  "access_key": "minioadmin",
  "secret_key": "minioadmin123",
  "secure": false,
  "region": null
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`minio_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `endpoint`, `access_key`, `secret_key`, `secure` (optional), `region` (optional)

2. **`minio_list_buckets`** - List Buckets
   - Parameters: `tenant_id`
   - Returns: List of all buckets with creation dates

3. **`minio_create_bucket`** - Create Bucket
   - Parameters: `tenant_id`, `bucket_name`, `region` (optional)

4. **`minio_delete_bucket`** - Delete Bucket
   - Parameters: `tenant_id`, `bucket_name`
   - Note: Bucket must be empty

5. **`minio_bucket_exists`** - Check Bucket Exists
   - Parameters: `tenant_id`, `bucket_name`
   - Returns: Boolean indicating existence

6. **`minio_list_objects`** - List Objects
   - Parameters: `tenant_id`, `bucket_name`, `prefix` (optional), `recursive` (optional, default: true)
   - Returns: List of objects with metadata

7. **`minio_upload_object`** - Upload Object
   - Parameters: `tenant_id`, `bucket_name`, `object_name`, `data` (string), `content_type` (optional)

8. **`minio_download_object`** - Download Object
   - Parameters: `tenant_id`, `bucket_name`, `object_name`
   - Returns: Object data as string

9. **`minio_delete_object`** - Delete Object
   - Parameters: `tenant_id`, `bucket_name`, `object_name`

#### Configuration via Environment Variables

```bash
export MINIO_TENANT_1_ENDPOINT="localhost:9000"
export MINIO_TENANT_1_ACCESS_KEY="minioadmin"
export MINIO_TENANT_1_SECRET_KEY="minioadmin123"
export MINIO_TENANT_1_SECURE="false"
```

#### Features

- Multi-tenant: Each tenant connects to their own MinIO instance
- S3-compatible: Works with any S3-compatible storage
- Redis persistence: Tenant configurations persist across restarts (Redis DB 2)
- Full CRUD operations: Create, read, update, and delete buckets and objects

---

## Content Generation

### 4. PDF Generator MCP Server

#### Overview

The PDF Generator MCP server provides PDF report generation from HTML templates with multi-tenant support. It supports variable substitution in templates and can return PDFs as base64 data or temporary file URLs.

#### Connection

**Remote (HTTPS):**
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

**Local Development:**
```bash
docker compose up -d mcp-pdf-generator-server
# Server available at http://localhost:8003
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "storage_path": "/custom/path"
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`pdf_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `storage_path` (optional)

2. **`pdf_generate_pdf`** - Generate PDF
   - Parameters: `tenant_id`, `template` (HTML string), `content` (dict), `filename` (optional), `return_format` (optional: "base64" or "url")
   - Template variables: Use `{{variable_name}}` syntax
   - Returns: PDF as base64 or temporary URL

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
</body>
</html>
```

**Content Dictionary:**
```json
{
  "report_title": "Monthly Invoice",
  "customer_name": "John Doe",
  "amount": "1,234.56"
}
```

#### Features

- Multi-tenant: Each tenant can have custom storage paths
- HTML templates: Use standard HTML with CSS styling
- Variable substitution: Use `{{variable}}` syntax for dynamic content
- Multiple output formats: Base64 data stream or temporary file URLs
- Redis persistence: Tenant configurations persist across restarts (Redis DB 3)
- Automatic cleanup: Temporary files are cleaned up after retention period

---

### 5. FFmpeg MCP Server

#### Overview

The FFmpeg MCP server provides comprehensive video and audio processing capabilities using FFmpeg. It supports format conversion, editing, merging, and analysis operations.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "ffmpeg-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/ffmpeg/mcp",
      "description": "FFmpeg MCP Server - Video and audio processing"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-ffmpeg-server
# Server available at http://localhost:8004
```

#### Available Tools

All tools accept video/audio data as base64-encoded strings and return processed media as base64-encoded output.

1. **`ffmpeg_convert_video`** - Convert Video Format
   - Parameters: `input_data` (base64), `output_format` (optional), `video_codec` (optional), `audio_codec` (optional), `quality` (optional), `resolution` (optional), `bitrate` (optional), `fps` (optional)

2. **`ffmpeg_extract_audio`** - Extract Audio
   - Parameters: `input_data` (base64), `output_format` (optional), `audio_codec` (optional), `bitrate` (optional)

3. **`ffmpeg_merge_videos`** - Merge Videos
   - Parameters: `video_data_list` (list of base64), `output_format` (optional)

4. **`ffmpeg_add_subtitles`** - Add Subtitles
   - Parameters: `input_data` (base64), `subtitle_text`, `start_time`, `duration`, `position` (optional), `font_size` (optional), `output_format` (optional)

5. **`ffmpeg_trim_video`** - Trim Video
   - Parameters: `input_data` (base64), `start_time`, `duration` (optional), `end_time` (optional), `output_format` (optional)

6. **`ffmpeg_get_video_info_tool`** - Get Video Information
   - Parameters: `input_data` (base64)
   - Returns: Detailed video information (format, duration, resolution, codecs, bitrate, etc.)

7. **`ffmpeg_resize_video`** - Resize Video
   - Parameters: `input_data` (base64), `width`, `height`, `maintain_aspect` (optional), `output_format` (optional)

8. **`ffmpeg_extract_frame`** - Extract Frame
   - Parameters: `input_data` (base64), `timestamp`, `output_format` (optional)
   - Returns: Base64-encoded image (PNG/JPG)

#### Notes

- All input and output data must be base64-encoded
- Supported video formats: mp4, avi, mov, webm, mkv, and more
- Supported audio formats: mp3, wav, aac, ogg, and more
- Quality presets: low (CRF 23), medium (CRF 20), high (CRF 18), veryhigh (CRF 16)
- Time formats: Use HH:MM:SS (e.g., "00:01:30") or seconds (e.g., "90")
- Temporary files are automatically cleaned up after processing

---

### 6. GenImage MCP Server

#### Overview

The GenImage MCP server provides AI image generation using Runware API with multi-tenant support. Each tenant provides their own Runware API key.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "genimage-mcp-remote": {
      "url": "https://mcp.baisoln.com/genimage/mcp",
      "description": "GenImage MCP Server - AI image generation with Runware API"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-genimage-server
# Server available at http://localhost:8008
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "runware_api_key": "your-runware-api-key",
  "base_url": "https://api.runware.ai/v1",
  "max_concurrent_requests": 10
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`gi_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `runware_api_key`, `base_url` (optional), `max_concurrent_requests` (optional)

2. **`gi_generate_image`** - Generate Image
   - Parameters: `tenant_id`, `prompt`, `width` (optional, default: 1024), `height` (optional, default: 1024), `model` (optional), `steps` (optional, default: 40), `cfg_scale` (optional, default: 5.0), `output_path` (optional)
   - Default model: `civitai:943001@1055701` (SDXL-based)
   - Returns: Generated image as base64 or file path

3. **`gi_upscale_image`** - Upscale Image
   - Parameters: `tenant_id`, `image_data` (base64 or file path), `scale` (optional, default: 2), `output_path` (optional)
   - Returns: Upscaled image as base64 or file path

4. **`gi_remove_background`** - Remove Background
   - Parameters: `tenant_id`, `image_data` (base64 or file path), `output_path` (optional)
   - Returns: Image with background removed as base64 or file path

#### Configuration via Environment Variables

```bash
export GENIMAGE_TENANT_1_RUNWARE_API_KEY="your-api-key"
export GENIMAGE_TENANT_1_BASE_URL="https://api.runware.ai/v1"
export GENIMAGE_TENANT_1_MAX_CONCURRENT="10"
```

#### Features

- Multi-tenant: Each tenant uses their own Runware API key
- Redis persistence: Tenant configurations persist across restarts (Redis DB 7)
- Image generation: Create images from text prompts using various models
- Image processing: Upscale images and remove backgrounds
- Concurrency control: Configurable max concurrent requests per tenant

---

### 7. AI MCP Server

#### Overview

The AI MCP Server provides comprehensive AI capabilities including LLM chat/completions, audio processing (speech-to-text, text-to-speech), embeddings, video generation and recognition, and more. It supports multi-tenant configurations with provider routing:

- **"global" tenant** → Uses GPU-AI API at `192.168.0.10:8000`
- **Other tenants** → Routes to:
  - LLM/STT → OpenRouter (requires `openrouter_api_key`)
  - TTS → Eleven Labs (requires `elevenlabs_api_key`)
  - Embeddings → OpenAI (requires `openai_api_key`)

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "ai-mcp-server-remote": {
      "url": "https://mcp.baisoln.com/ai-mcp-server/mcp",
      "description": "AI MCP Server - GPU-AI tools (OpenAI-compatible) - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-ai-mcp-server
# Server available at http://localhost:8009
```

#### Tenant Registration

**Register Global Tenant (GPU-AI API):**
```json
{
  "tenant_id": "global",
  "api_base_url": "http://192.168.0.10:8000",
  "api_key": "optional-api-key"
}
```

**Register Custom Tenant (Multi-Provider):**
```json
{
  "tenant_id": "my-tenant",
  "openrouter_api_key": "sk-or-v1-...",
  "elevenlabs_api_key": "...",
  "openai_api_key": "sk-...",
  "timeout": 300,
  "max_concurrent_requests": 10
}
```

#### Available Tools (31 Total)

**Tenant Management:**
- `ai_register_tenant` - Register tenant with provider-specific API keys

**LLM Tools:**
- `ai_list_models` - List available AI models
- `ai_chat_completion` - Create chat completions
- `ai_text_completion` - Create text completions

**Audio Tools:**
- `ai_audio_speech_to_text` - Convert speech to text
- `ai_audio_text_to_speech` - Convert text to speech
- `ai_audio_list_models` - List audio models
- `ai_audio_voice_clone_xtts_v2` - Voice clone using XTTS v2
- `ai_xtts_v2_list_models` - List XTTS v2 models
- `ai_create_audio_transcription` - Audio transcription (OpenAI-compatible)
- `ai_create_audio_translation` - Audio translation (OpenAI-compatible)
- `ai_text_to_speech_prompt` - Text-to-speech from natural language prompt

**Embeddings Tools:**
- `ai_create_embeddings` - Create embeddings for text
- `ai_embeddings_get_status` - Get embeddings generation status
- `ai_embeddings_analysis_prompt` - Embeddings analysis from prompt

**Video Tools:**
- `ai_generate_video` - Generate video from text prompt
- `ai_video_get_status` - Get video generation status
- `ai_recognize_video` - Recognize and analyze video content
- `ai_video_synopsis` - Generate video synopsis
- `ai_video_qa` - Video question answering
- `ai_video_recognition_get_status` - Get video recognition status
- `ai_video_generation_prompt` - Video generation from prompt
- `ai_video_analysis_prompt` - Video analysis from prompt

**WAN2 Tools:**
- `ai_wan2_text_to_video` - WAN2 text to video
- `ai_wan2_image_to_video` - WAN2 image to video
- `ai_wan2_compress_video` - WAN2 compress video
- `ai_wan2_get_status` - Get WAN2 task status

**Other Tools:**
- `ai_create_image` - Generate image from prompt (OpenAI-compatible)
- `ai_create_moderation` - Content moderation (OpenAI-compatible)
- `ai_get_mcp_tools` - Get additional MCP tools from GPU-AI API
- `ai_proxy_service_request` - Proxy request to any GPU-AI service

#### Multi-Tenant Provider Routing

| Service Type | Global Tenant | Other Tenants |
|-------------|---------------|---------------|
| **LLM** (Chat/Text Completions) | GPU-AI API | OpenRouter |
| **STT** (Speech-to-Text) | GPU-AI API | OpenRouter |
| **TTS** (Text-to-Speech) | GPU-AI API | Eleven Labs |
| **Embeddings** | GPU-AI API | OpenAI |
| **Video** | GPU-AI API | GPU-AI API |
| **Audio** | GPU-AI API | GPU-AI API |
| **WAN2** | GPU-AI API | GPU-AI API |

#### Features

- Multi-tenant: Support for multiple tenants with provider-specific routing
- Redis persistence: Tenant configurations persist across restarts (Redis DB 8)
- Provider routing: Automatic routing to appropriate AI provider based on tenant
- 31 tools: Comprehensive AI capabilities covering LLM, audio, embeddings, video, and more
- OpenAI-compatible: Many endpoints follow OpenAI API format for compatibility

---

## Communication & Collaboration

### 8. Mail MCP Server

#### Overview

The Mail MCP server provides email sending operations with multi-tenant support. Each tenant connects to their own mail service API.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "mail-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/mail/mcp",
      "description": "Mail Service MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-mail-server
# Server available at http://localhost:8005
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "api_key": "your-jwt-token-here",
  "mail_api_url": "http://mail-service.mail:8000",
  "default_from_email": "noreply@example.com",
  "default_from_name": "My App"
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`mail_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `api_key`, `mail_api_url` (optional), `default_from_email` (optional), `default_from_name` (optional)

2. **`mail_send_email`** - Send Single Email
   - Parameters: `tenant_id`, `to` (list), `subject`, `body`, `cc` (optional), `bcc` (optional), `body_type` (optional: "text" or "html"), `from_email` (optional), `from_name` (optional), `reply_to` (optional)

3. **`mail_send_email_with_attachments`** - Send Email with Attachments
   - Parameters: `tenant_id`, `to` (list), `subject`, `body`, `attachments` (list of objects with `filename`, `content` (base64), `content_type`), `cc` (optional), `bcc` (optional), `body_type` (optional), `from_email` (optional), `from_name` (optional), `reply_to` (optional)

4. **`mail_send_bulk_emails`** - Send Bulk Emails
   - Parameters: `tenant_id`, `emails` (list of email objects)
   - Returns: Summary with total, successful, and failed counts

#### Configuration via Environment Variables

```bash
export MAIL_TENANT_1_API_KEY="your-jwt-token"
export MAIL_TENANT_1_MAIL_API_URL="http://mail-service.mail:8000"
export MAIL_TENANT_1_DEFAULT_FROM_EMAIL="noreply@example.com"
export MAIL_TENANT_1_DEFAULT_FROM_NAME="My App"
```

#### Features

- Multi-tenant: Each tenant connects to their own mail service API
- HTML and text emails: Support for both plain text and HTML email bodies
- Attachments: Send emails with file attachments (base64-encoded)
- Bulk sending: Send multiple emails concurrently
- Default sender: Configure default from email and name per tenant
- Redis persistence: Tenant configurations persist across restarts (Redis DB 4)

---

### 9. OpenProject MCP Server

#### Overview

The OpenProject MCP server provides comprehensive project management operations through the OpenProject API. It supports projects, work packages, users, attachments, and more.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "openproject-mcp-remote": {
      "url": "https://mcp.baisoln.com/openproject/mcp",
      "description": "OpenProject MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-openproject-server
# Server available at http://localhost:8006
```

#### Configuration

The OpenProject server requires environment variables:

```bash
export OPENPROJECT_URL="https://your-openproject-instance.com"
export OPENPROJECT_API_KEY="your-api-key"
```

#### Available Tools

**Connection & Testing:**
- `test_connection` - Test API connection

**Projects:**
- `list_projects` - List all projects
- `get_project` - Get project details
- `create_project` - Create new project
- `update_project` - Update project
- `delete_project` - Delete project

**Work Packages:**
- `list_work_packages` - List work packages with filtering
- `get_work_package` - Get work package details
- `create_work_package` - Create new work package
- `update_work_package` - Update work package
- `delete_work_package` - Delete work package
- `query_work_packages` - Advanced query with flexible filtering
- `search_work_packages` - Search work packages by subject text

**Work Package Types & Statuses:**
- `list_types` - List work package types
- `list_statuses` - List all statuses
- `list_priorities` - List all priorities
- `get_work_package_schema` - Get schema with available transitions

**Users:**
- `list_users` - List all users
- `get_user` - Get user details
- `get_available_assignees` - Get users who can be assigned

**Attachments:**
- `list_work_package_attachments` - List attachments for work package
- `add_work_package_attachment` - Add attachment (base64-encoded file)
- `delete_attachment` - Delete attachment

**Work Package Relations:**
- `create_work_package_relation` - Create relation between work packages
- `list_work_package_relations` - List relations
- `delete_work_package_relation` - Delete relation

**Hierarchy Management:**
- `set_work_package_parent` - Set parent work package
- `remove_work_package_parent` - Remove parent relationship
- `get_work_package_children` - Get child work packages
- `get_work_package_hierarchy` - Get full hierarchy (ancestors and descendants)

**Comments & Activities:**
- `add_work_package_comment` - Add comment to work package
- `list_work_package_activities` - List activities (comments and changes)

**Watchers:**
- `add_work_package_watcher` - Add watcher to work package
- `remove_work_package_watcher` - Remove watcher
- `list_work_package_watchers` - List all watchers

**Bulk Operations:**
- `bulk_create_work_packages` - Create multiple work packages in batch
- `bulk_update_work_packages` - Update multiple work packages in batch

**Time Tracking:**
- `log_time` - Log time spent on work package
- `list_time_entries` - List time entries with filters
- `list_time_entry_activities` - List available time entry activities

**Custom Fields:**
- `list_custom_fields` - List all custom fields
- `update_work_package_custom_fields` - Update custom field values

**Status Management:**
- `update_work_package_status` - Update status with optional comment

**Assignment:**
- `assign_work_package` - Assign or reassign work package

#### Notes

- The server requires `OPENPROJECT_URL` and `OPENPROJECT_API_KEY` environment variables
- Work package IDs and project IDs can be provided as integers or strings
- Attachment content must be base64-encoded
- Filter syntax follows OpenProject API filter format
- Bulk operations support transaction-like behavior with `continue_on_error`
- Relations support various types: relates, duplicates, blocks, precedes, follows, etc.

---

## Search & Discovery

### 10. MeiliSearch MCP Server

#### Overview

The MeiliSearch MCP server provides search engine operations with multi-tenant support. Each tenant can connect to their own MeiliSearch instance.

#### Connection

**Remote (HTTPS):**
```json
{
  "mcpServers": {
    "meilisearch-mcp-remote": {
      "url": "https://mcp.baisoln.com/meilisearch/mcp",
      "description": "MeiliSearch MCP Server - External access via HTTPS"
    }
  }
}
```

**Local Development:**
```bash
docker compose up -d mcp-meilisearch-server
# Server available at http://localhost:8007
```

#### Getting Started

**Step 1: Register a Tenant**

```json
{
  "tenant_id": "my-tenant",
  "url": "http://meilisearch.meilisearch:7700",
  "api_key": "your-master-key",
  "timeout": 5
}
```

**Step 2: Use the Tools**

#### Available Tools

1. **`ms_register_tenant`** - Register Tenant
   - Parameters: `tenant_id`, `url`, `api_key` (optional), `timeout` (optional, default: 5)

2. **`ms_list_indexes`** - List Indexes
   - Parameters: `tenant_id`
   - Returns: List of all indexes with metadata

3. **`ms_get_index`** - Get Index Information
   - Parameters: `tenant_id`, `index_uid`
   - Returns: Detailed index information

4. **`ms_create_index`** - Create Index
   - Parameters: `tenant_id`, `index_uid`, `primary_key` (optional)

5. **`ms_delete_index`** - Delete Index
   - Parameters: `tenant_id`, `index_uid`

6. **`ms_add_documents`** - Add Documents
   - Parameters: `tenant_id`, `index_uid`, `documents` (JSON string array), `primary_key` (optional)
   - Returns: Task object for monitoring

7. **`ms_search`** - Search Documents
   - Parameters: `tenant_id`, `index_uid`, `query`, `limit` (optional), `offset` (optional), `filter` (optional), `sort` (optional)
   - Returns: Search results with hits, estimated total, and processing time

8. **`ms_get_document`** - Get Document
   - Parameters: `tenant_id`, `index_uid`, `document_id`
   - Returns: Single document by ID

9. **`ms_delete_documents`** - Delete Documents
   - Parameters: `tenant_id`, `index_uid`, `document_ids` (JSON string array)
   - Returns: Task object for monitoring

#### Configuration via Environment Variables

```bash
export MEILISEARCH_TENANT_1_URL="http://meilisearch.meilisearch:7700"
export MEILISEARCH_TENANT_1_API_KEY="your-master-key"
```

#### Features

- Multi-tenant: Each tenant connects to their own MeiliSearch instance
- Full-text search: Powerful search capabilities with typo tolerance
- Index management: Create, list, and delete indexes
- Document operations: Add, get, search, and delete documents
- Filtering and sorting: Advanced search with filters and sorting
- Redis persistence: Tenant configurations persist across restarts (Redis DB 5)

#### Notes

- Documents must be provided as JSON string arrays
- Search supports typo tolerance and ranking
- Filter expressions follow MeiliSearch filter syntax
- Sort fields should be provided as JSON string arrays (e.g., `"[\"price:asc\", \"name:desc\"]"`)
- Task-based operations (add/delete) return task objects that can be monitored
- The server supports both master keys and search keys for authentication

---

## Multi-Tenant Architecture

### Overview

Most MCP servers support multi-tenancy, allowing multiple tenants to use the same server instance with isolated configurations and data.

### Multi-Tenant Servers

The following servers support multi-tenancy:

- PostgreSQL (Redis DB 1)
- MinIO (Redis DB 2)
- PDF Generator (Redis DB 3)
- Mail (Redis DB 4)
- MeiliSearch (Redis DB 5)
- GenImage (Redis DB 7)
- AI MCP Server (Redis DB 8)

### Tenant Registration

Each multi-tenant server provides a registration tool (e.g., `pg_register_tenant`, `minio_register_tenant`) that:

1. Accepts tenant-specific configuration (connection details, API keys, etc.)
2. Stores the configuration in Redis for persistence
3. Creates client instances for the tenant
4. Manages connection pools and resources per tenant

### Configuration Methods

**Method 1: Runtime Registration (via MCP tools)**
```json
{
  "tenant_id": "my-tenant",
  "config_param_1": "value1",
  "config_param_2": "value2"
}
```

**Method 2: Environment Variables**
```bash
export SERVER_TENANT_1_PARAM1="value1"
export SERVER_TENANT_1_PARAM2="value2"
```

### Redis Persistence

- Tenant configurations are stored in Redis with keys like: `mcp:{server-name}:tenant:{tenant-id}`
- Each server uses a different Redis database number for isolation
- Configurations persist across server restarts
- Servers automatically load tenants from Redis on startup

### Tenant Isolation

- Each tenant has isolated:
  - Connection pools (databases, storage, etc.)
  - API credentials
  - Configuration settings
  - Data access (enforced by tenant ID in all operations)

---

## Quick Reference

### Server Summary

| Server | Multi-Tenant | Tools Count | Redis DB | Port |
|--------|-------------|-------------|----------|------|
| Calculator | No | 7 | N/A | 8000 |
| PostgreSQL | Yes | 4 | 1 | 8001 |
| MinIO | Yes | 9 | 2 | 8002 |
| PDF Generator | Yes | 2 | 3 | 8003 |
| FFmpeg | No | 8 | N/A | 8004 |
| Mail | Yes | 4 | 4 | 8005 |
| OpenProject | No | 40+ | N/A | 8006 |
| MeiliSearch | Yes | 9 | 5 | 8007 |
| GenImage | Yes | 4 | 7 | 8008 |
| AI MCP Server | Yes | 31 | 8 | 8009 |

### Common Patterns

**1. Register Tenant (Multi-tenant servers):**
```python
register_tenant(
    tenant_id="my-tenant",
    # ... tenant-specific configuration
)
```

**2. Use Tool with Tenant:**
```python
tool_name(
    tenant_id="my-tenant",
    # ... tool-specific parameters
)
```

**3. Base64 Encoding:**
- File uploads (attachments, images, videos, audio) require base64-encoded content
- Use `base64.b64encode(file_content).decode('utf-8')` in Python

**4. Error Handling:**
- All tools return a `success` field (boolean)
- Errors include an `error` field with description
- Check `success` before using results

**5. Health Checks:**
```bash
curl https://mcp.baisoln.com/{server-name}/health
```

### Best Practices

1. **Register tenants before use** - Multi-tenant servers require tenant registration
2. **Use parameterized queries** - For PostgreSQL, always use parameterized queries to prevent SQL injection
3. **Handle base64 encoding** - Ensure proper encoding/decoding for binary data
4. **Check health endpoints** - Verify server availability before making requests
5. **Monitor task status** - For async operations (video generation, embeddings), use status check tools
6. **Use appropriate timeouts** - Configure timeouts based on operation complexity
7. **Leverage bulk operations** - Use bulk tools when processing multiple items for better performance

---

## Support

For detailed information about each server, refer to the individual documentation files in the `docs/` directory:

- `calculator.md`
- `postgres.md`
- `minio.md`
- `pdf-generator.md`
- `ffmpeg.md`
- `mail.md`
- `openproject.md`
- `meilisearch.md`
- `ai-mcp-server.md`

For troubleshooting and advanced configuration, see:
- `STATELESS_MULTI_TENANT.md` - Multi-tenant architecture details
- `TENANT_PERSISTENCE.md` - Redis persistence implementation
- `CURSOR_TROUBLESHOOTING.md` - Cursor IDE integration troubleshooting
- `SSL_CERTIFICATE_FIX.md` - SSL certificate configuration

---

*Last Updated: January 2025*
