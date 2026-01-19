# Langfuse MCP Server - Usage Guide

## Overview

The Langfuse MCP server provides observability and tracing operations with multi-tenant support. Each tenant uses their own Langfuse API keys, allowing you to manage traces, spans, generations, events, and scores across multiple Langfuse projects through a single MCP server.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "langfuse-mcp-remote": {
      "url": "https://mcp.baisoln.com/langfuse/mcp",
      "description": "Langfuse MCP Server - Observability and tracing with multi-tenant support - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-langfuse-server

# Server will be available at http://localhost:8011
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your Langfuse API keys:

**Tool:** `lf_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "project-123")
- `secret_key` (required): Langfuse secret key (starts with `sk-lf-...`)
- `public_key` (required): Langfuse public key (starts with `pk-lf-...`)
- `base_url` (optional): Langfuse base URL (default: `https://langfuse.bionicaisolutions.com`)
- `max_concurrent_requests` (optional): Maximum concurrent requests per tenant (default: `100`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "secret_key": "sk-lf-...",
  "public_key": "pk-lf-...",
  "base_url": "https://langfuse.bionicaisolutions.com",
  "max_concurrent_requests": 100
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `lf_register_tenant` - Register Tenant

Register a new Langfuse tenant configuration with concurrency control.

**Parameters:**
- `tenant_id` (required): Unique identifier for this tenant
- `secret_key` (required): Langfuse secret key (sk-lf-...)
- `public_key` (required): Langfuse public key (pk-lf-...)
- `base_url` (optional): Langfuse base URL (default: https://langfuse.bionicaisolutions.com)
- `max_concurrent_requests` (optional): Maximum concurrent requests per tenant (default: 100)

### 2. `lf_create_trace` - Create Trace

Create a new trace in Langfuse. Traces represent a single execution flow.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `name` (required): Name of the trace
- `user_id` (optional): User ID associated with the trace
- `session_id` (optional): Session ID for grouping related traces
- `metadata` (optional): Metadata dictionary
- `tags` (optional): List of tags

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "name": "user-query-processing",
  "user_id": "user-123",
  "session_id": "session-456",
  "metadata": {
    "environment": "production",
    "version": "1.0.0"
  },
  "tags": ["api", "query"]
}
```

**Response:**
```json
{
  "success": true,
  "trace": {
    "id": "trace-abc123",
    "name": "user-query-processing",
    ...
  }
}
```

### 3. `lf_create_span` - Create Span

Create a span within a trace. Spans represent operations within a trace.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `trace_id` (required): Trace ID to attach span to
- `name` (required): Name of the span
- `start_time` (optional): Start time in ISO format
- `end_time` (optional): End time in ISO format
- `metadata` (optional): Metadata dictionary

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "trace_id": "trace-abc123",
  "name": "database-query",
  "start_time": "2024-01-01T10:00:00Z",
  "end_time": "2024-01-01T10:00:01Z",
  "metadata": {
    "query": "SELECT * FROM users",
    "duration_ms": 1000
  }
}
```

**Response:**
```json
{
  "success": true,
  "span": {
    "id": "span-xyz789",
    "name": "database-query",
    ...
  }
}
```

### 4. `lf_create_generation` - Create Generation

Create a generation (LLM call) observation. Used for tracking AI model calls.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `trace_id` (required): Trace ID to attach generation to
- `name` (required): Name of the generation
- `model` (optional): Model name (e.g., "gpt-4", "claude-3")
- `model_parameters` (optional): Model parameters dictionary
- `input` (optional): Input data
- `output` (optional): Output data
- `metadata` (optional): Metadata dictionary

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "trace_id": "trace-abc123",
  "name": "llm-completion",
  "model": "gpt-4",
  "model_parameters": {
    "temperature": 0.7,
    "max_tokens": 1000
  },
  "input": "What is the capital of France?",
  "output": "The capital of France is Paris.",
  "metadata": {
    "provider": "openai",
    "cost": 0.001
  }
}
```

**Response:**
```json
{
  "success": true,
  "generation": {
    "id": "gen-123456",
    "name": "llm-completion",
    ...
  }
}
```

### 5. `lf_create_event` - Create Event

Create an event observation. Events represent discrete occurrences in a trace.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `trace_id` (required): Trace ID to attach event to
- `name` (required): Name of the event
- `metadata` (optional): Metadata dictionary

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "trace_id": "trace-abc123",
  "name": "user-click",
  "metadata": {
    "button": "submit",
    "page": "/checkout"
  }
}
```

**Response:**
```json
{
  "success": true,
  "event": {
    "id": "event-789",
    "name": "user-click",
    ...
  }
}
```

### 6. `lf_create_score` - Create Score

Create a score for a trace or observation. Scores represent evaluations or ratings.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `name` (required): Name of the score
- `value` (required): Score value (float)
- `trace_id` (optional): Trace ID to attach score to
- `observation_id` (optional): Observation ID to attach score to
- `comment` (optional): Comment about the score

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "name": "quality-score",
  "value": 0.95,
  "trace_id": "trace-abc123",
  "comment": "High quality response"
}
```

**Response:**
```json
{
  "success": true,
  "score": {
    "id": "score-456",
    "name": "quality-score",
    "value": 0.95,
    ...
  }
}
```

### 7. `lf_get_trace` - Get Trace

Retrieve a trace by ID with all its observations.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `trace_id` (required): Trace ID to retrieve

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "trace_id": "trace-abc123"
}
```

**Response:**
```json
{
  "success": true,
  "trace": {
    "id": "trace-abc123",
    "name": "user-query-processing",
    "observations": [...],
    ...
  }
}
```

### 8. `lf_get_project` - Get Project Information

Get information about the Langfuse project.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID

**Example:**
```json
{
  "tenant_id": "my-tenant"
}
```

**Response:**
```json
{
  "success": true,
  "project": {
    "id": "project-123",
    "name": "My Project",
    ...
  }
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: LANGFUSE_TENANT_{TENANT_ID}_SECRET_KEY
export LANGFUSE_TENANT_1_SECRET_KEY="sk-lf-..."
export LANGFUSE_TENANT_1_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_TENANT_1_BASE_URL="https://langfuse.bionicaisolutions.com"
export LANGFUSE_TENANT_1_MAX_CONCURRENT="100"
```

## Features

- **Multi-tenant**: Each tenant uses their own Langfuse API keys
- **Redis persistence**: Tenant configurations persist across restarts (Redis DB 9)
- **Concurrency control**: Configurable max concurrent requests per tenant
- **Full observability**: Traces, spans, generations, events, and scores
- **LLM tracking**: Track AI model calls with detailed metadata
- **Project management**: Get project information and statistics
- **Flexible metadata**: Attach custom metadata to all observations

## Resources

Access tenant information as resources:

- `langfuse://{tenant_id}/project` - Get project information for a tenant
- `langfuse://info` - Get information about the Langfuse MCP server

## Example Workflow

1. Register your tenant:
   ```
   lf_register_tenant(tenant_id="my-tenant", secret_key="sk-lf-...", public_key="pk-lf-...")
   ```

2. Create a trace:
   ```
   lf_create_trace(tenant_id="my-tenant", name="api-request", user_id="user-123")
   ```

3. Add a span:
   ```
   lf_create_span(tenant_id="my-tenant", trace_id="trace-abc123", name="database-query")
   ```

4. Track an LLM call:
   ```
   lf_create_generation(tenant_id="my-tenant", trace_id="trace-abc123", name="llm-call", model="gpt-4", input="Hello", output="Hi there!")
   ```

5. Add a score:
   ```
   lf_create_score(tenant_id="my-tenant", name="quality", value=0.95, trace_id="trace-abc123")
   ```

6. Retrieve the trace:
   ```
   lf_get_trace(tenant_id="my-tenant", trace_id="trace-abc123")
   ```

## Notes

- Tenant configurations are stored in Redis (DB 9)
- Each tenant maintains its own Langfuse client connection
- Traces can contain multiple observations (spans, generations, events)
- Scores can be attached to traces or individual observations
- All timestamps should be in ISO 8601 format
- Metadata can contain any JSON-serializable data
- The server automatically handles rate limiting and connection pooling
- Use `max_concurrent_requests` to control throughput per tenant

## Best Practices

1. **Trace Structure**: Create a trace at the start of a request, then add spans and generations as operations occur
2. **Naming**: Use descriptive names for traces, spans, and generations (e.g., "user-query-processing", "database-lookup")
3. **Metadata**: Include relevant context in metadata (environment, version, user info, etc.)
4. **Scores**: Use scores to track quality, latency, cost, or other metrics
5. **Session IDs**: Use session IDs to group related traces from the same user session
6. **User IDs**: Include user IDs to track per-user analytics
