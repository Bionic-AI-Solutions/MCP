# MCP Server Tools Reference

Complete reference for all MCP servers deployed at `mcp.baisoln.com`. Last updated: 2026-03-20.

---

## Protocol & Connection

All servers use the **MCP JSON-RPC 2.0** protocol over HTTP (Streamable HTTP transport).

### Endpoint Pattern

```
POST https://mcp.baisoln.com/{server}/mcp
```

### Connection Flow

```
1. POST /mcp  →  method: "initialize"    →  Get session ID from Mcp-Session-Id header
2. POST /mcp  →  method: "tools/list"    →  Discover available tools (with Mcp-Session-Id header)
3. POST /mcp  →  method: "tools/call"    →  Call a tool (with Mcp-Session-Id header)
```

### Required Headers

```
Content-Type: application/json
Accept: application/json, text/event-stream
Mcp-Session-Id: <session-id>    # Required after initialize
```

### Tool Call Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": { "param1": "value1" }
  }
}
```

---

## Multi-Tenant Architecture

All servers (except Calculator) are **multi-tenant**. Every tool call requires a `tenant_id` parameter to scope operations.

### Tenant Lifecycle

1. **Register** a tenant using the server's `*_register_tenant` tool (provides credentials, connection info)
2. **Use** any tool by passing the registered `tenant_id`
3. Tenants are persisted in Redis with automatic reconnection

### Pre-registered Tenants

Tenants are pre-configured via `/etc/mcp/tenants.json` (Kubernetes Secret). These are available immediately without calling `register_tenant`.

### Key Isolation Rules

- **PostgreSQL**: Each tenant connects to its own database with its own credentials
- **Redis**: Keys are automatically namespaced per tenant (transparent to the caller)
- **MinIO**: Each tenant connects to its own MinIO instance with its own credentials
- **Letta**: Each tenant connects to its own Letta server; `lt_user_memory` additionally isolates by `user_id`

---

## Server Index

| # | Server | Path | Tools | Tenant Required | Description |
|---|--------|------|-------|-----------------|-------------|
| 1 | [PostgreSQL](#1-postgresql-server) | `/postgres/mcp` | 7 | Yes | SQL queries, schema inspection, transactions |
| 2 | [Redis](#2-redis-server) | `/redis/mcp` | 46 | Yes | Full Redis data structure operations, pub/sub |
| 3 | [MinIO](#3-minio-server) | `/minio/mcp` | 9 | Yes | S3-compatible object storage |
| 4 | [Letta AI](#4-letta-ai-server) | `/letta/mcp` | 19 | Yes | AI agent platform — agents, memory, RAG, conversations |
| 5 | [AI/GPU](#5-aigpu-server) | `/ai/mcp` | 30 | Yes | LLM chat, embeddings, TTS/STT, image/video gen |
| 6 | [MeiliSearch](#6-meilisearch-server) | `/meilisearch/mcp` | 9 | Yes | Full-text search engine |
| 7 | [Mail](#7-mail-server) | `/mail/mcp` | 4 | Yes | Send emails with attachments |
| 8 | [PDF Generator](#8-pdf-generator-server) | `/pdf/mcp` | 3 | Yes | Generate PDFs from HTML templates |
| 9 | [FFmpeg](#9-ffmpeg-server) | `/ffmpeg/mcp` | 8 | No | Video/audio conversion and editing |
| 10 | [GenImage](#10-genimage-server) | `/genimage/mcp` | 4 | Yes | AI image generation (Runware) |
| 11 | [Langfuse](#11-langfuse-server) | `/langfuse/mcp` | 8 | Yes | LLM observability — traces, spans, scores |
| 12 | [OpenProject](#12-openproject-server) | `/openproject/mcp` | 38 | No* | Project management — work packages, time tracking |
| 13 | [Calculator](#13-calculator-server) | `/calculator/mcp` | 7 | No | Basic arithmetic |
| 14 | [Search](#14-search-server) | `/search/mcp` | 4 | No | Web search (SearXNG) and web crawling (Crawl4AI) |

**Total: 196 tools across 14 servers**

\* OpenProject uses a single pre-configured connection rather than dynamic tenant registration.

---

## 1. PostgreSQL Server

**Path**: `POST https://mcp.baisoln.com/postgres/mcp`
**Tools**: 7 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `pg_execute_query` | Execute any SQL (SELECT, INSERT, UPDATE, DELETE, DDL) | `tenant_id`, `query` |
| `pg_list_tables` | List tables and views in a schema | `tenant_id` |
| `pg_describe_table` | Get column metadata for a table | `tenant_id`, `table_name` |
| `pg_begin_transaction` | Begin a multi-statement transaction | `tenant_id` |
| `pg_commit_transaction` | Commit a transaction | `tenant_id`, `transaction_id` |
| `pg_rollback_transaction` | Roll back a transaction | `tenant_id`, `transaction_id` |
| `pg_register_tenant` | Register a new database connection | `tenant_id`, `host`, `database`, `user`, `password` |

### pg_execute_query

```json
{
  "tenant_id": "vc-livekit",
  "query": "SELECT id, name FROM users WHERE active = $1 LIMIT 10",
  "params": [true],
  "role": "readonly"
}
```

Optional: `params` (parameterized query values), `role` (execution role), `transaction_id` (for multi-statement transactions).

### Transactions

```json
// Step 1: Begin
{"name": "pg_begin_transaction", "arguments": {"tenant_id": "t1", "timeout_seconds": 30}}
// → Returns {"transaction_id": "tx-abc123"}

// Step 2: Execute within transaction
{"name": "pg_execute_query", "arguments": {"tenant_id": "t1", "query": "UPDATE ...", "transaction_id": "tx-abc123"}}

// Step 3: Commit or rollback
{"name": "pg_commit_transaction", "arguments": {"tenant_id": "t1", "transaction_id": "tx-abc123"}}
```

### pg_register_tenant

```json
{
  "tenant_id": "my-app",
  "host": "pg-ceph-rw.pg.svc.cluster.local",
  "database": "my_app_db",
  "user": "my_app_user",
  "password": "secret",
  "port": 5432,
  "ssl": false,
  "min_pool_size": 2,
  "max_pool_size": 10,
  "max_concurrent_requests": 20
}
```

---

## 2. Redis Server

**Path**: `POST https://mcp.baisoln.com/redis/mcp`
**Tools**: 46 | **Tenant**: Required

Keys are **automatically namespaced** per tenant. Use plain key names without prefixes.

### Tool Categories

#### Strings (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_get` | Get string value | `tenant_id`, `key` |
| `redis_set` | Set string value with optional TTL | `tenant_id`, `key`, `value` |
| `redis_mget` | Get multiple keys | `tenant_id`, `keys` (array) |
| `redis_mset` | Set multiple key-value pairs atomically | `tenant_id`, `mapping` (object) |
| `redis_incr` | Increment integer value | `tenant_id`, `key` |
| `redis_append` | Append to string value | `tenant_id`, `key`, `value` |
| `redis_delete` | Delete one or more keys | `tenant_id`, `keys` (array) |

#### Key Management (8 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_exists` | Check if keys exist | `tenant_id`, `keys` (array) |
| `redis_keys` | List keys matching glob pattern | `tenant_id` |
| `redis_scan` | Cursor-based key iteration (production-safe) | `tenant_id` |
| `redis_type` | Get data type of a key | `tenant_id`, `key` |
| `redis_ttl` | Get remaining TTL in seconds | `tenant_id`, `key` |
| `redis_expire` | Set TTL on a key | `tenant_id`, `key`, `seconds` |
| `redis_persist` | Remove TTL (make key permanent) | `tenant_id`, `key` |
| `redis_rename` | Rename a key | `tenant_id`, `key`, `new_key` |

#### Hashes (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_hset` | Set hash field(s) | `tenant_id`, `key`, `mapping` (object) |
| `redis_hget` | Get a hash field | `tenant_id`, `key`, `field` |
| `redis_hgetall` | Get all hash fields | `tenant_id`, `key` |
| `redis_hdel` | Delete hash field(s) | `tenant_id`, `key`, `fields` (array) |
| `redis_hexists` | Check if hash field exists | `tenant_id`, `key`, `field` |
| `redis_hkeys` | List all hash field names | `tenant_id`, `key` |
| `redis_hincrby` | Increment hash field value | `tenant_id`, `key`, `field` |

#### Lists (6 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_lpush` | Push to head of list | `tenant_id`, `key`, `values` (array) |
| `redis_rpush` | Push to tail of list | `tenant_id`, `key`, `values` (array) |
| `redis_lpop` | Pop from head | `tenant_id`, `key` |
| `redis_rpop` | Pop from tail | `tenant_id`, `key` |
| `redis_lrange` | Get range of elements | `tenant_id`, `key` |
| `redis_llen` | Get list length | `tenant_id`, `key` |
| `redis_lset` | Set element at index | `tenant_id`, `key`, `index`, `value` |

#### Sets (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_sadd` | Add members to set | `tenant_id`, `key`, `members` (array) |
| `redis_srem` | Remove members from set | `tenant_id`, `key`, `members` (array) |
| `redis_smembers` | Get all set members | `tenant_id`, `key` |
| `redis_sismember` | Check membership | `tenant_id`, `key`, `member` |
| `redis_scard` | Get set size | `tenant_id`, `key` |
| `redis_sunion` | Union of multiple sets | `tenant_id`, `keys` (array) |
| `redis_sinter` | Intersection of multiple sets | `tenant_id`, `keys` (array) |
| `redis_sdiff` | Difference of sets | `tenant_id`, `keys` (array) |

#### Sorted Sets (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_zadd` | Add members with scores | `tenant_id`, `key`, `members` (object: member→score) |
| `redis_zrem` | Remove members | `tenant_id`, `key`, `members` (array) |
| `redis_zrange` | Get range by rank | `tenant_id`, `key` |
| `redis_zscore` | Get member's score | `tenant_id`, `key`, `member` |
| `redis_zrank` | Get member's rank | `tenant_id`, `key`, `member` |
| `redis_zcard` | Get sorted set size | `tenant_id`, `key` |
| `redis_zrangebyscore` | Get range by score | `tenant_id`, `key` |
| `redis_zincrby` | Increment member's score | `tenant_id`, `key`, `member` |

#### Pub/Sub (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_publish` | Publish message to channel | `tenant_id`, `channel`, `message` |
| `redis_subscribe` | Subscribe to channel | `tenant_id`, `channel` |
| `redis_poll` | Poll buffered messages | `subscription_id` |
| `redis_unsubscribe` | Unsubscribe from channel | `subscription_id` |

#### Server (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `redis_ping` | Test connectivity | `tenant_id` |
| `redis_info` | Get server stats | `tenant_id` |
| `redis_dbsize` | Count tenant's keys | `tenant_id` |
| `redis_flushdb` | Delete ALL tenant keys (destructive) | `tenant_id`, `confirm` (must be true) |
| `redis_execute_command` | Execute arbitrary Redis command | `tenant_id`, `command` |

### redis_register_tenant

```json
{
  "tenant_id": "my-cache",
  "host": "redis-cluster.redis.svc.cluster.local",
  "port": 6379,
  "cluster_mode": true,
  "decode_responses": true,
  "max_concurrent_requests": 50
}
```

---

## 3. MinIO Server

**Path**: `POST https://mcp.baisoln.com/minio/mcp`
**Tools**: 9 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `minio_list_buckets` | List all buckets | `tenant_id` |
| `minio_create_bucket` | Create a bucket | `tenant_id`, `bucket_name` |
| `minio_delete_bucket` | Delete empty bucket | `tenant_id`, `bucket_name` |
| `minio_bucket_exists` | Check if bucket exists | `tenant_id`, `bucket_name` |
| `minio_list_objects` | List objects (with prefix filter) | `tenant_id`, `bucket_name` |
| `minio_upload_object` | Upload string data as object | `tenant_id`, `bucket_name`, `object_name`, `data` |
| `minio_download_object` | Download object content | `tenant_id`, `bucket_name`, `object_name` |
| `minio_delete_object` | Delete an object | `tenant_id`, `bucket_name`, `object_name` |
| `minio_register_tenant` | Register MinIO connection | `tenant_id`, `endpoint`, `access_key`, `secret_key` |

### Example

```json
{
  "name": "minio_upload_object",
  "arguments": {
    "tenant_id": "vc-livekit",
    "bucket_name": "vc-livekit",
    "object_name": "docs/report.txt",
    "data": "Report content here...",
    "content_type": "text/plain"
  }
}
```

---

## 4. Letta AI Server

**Path**: `POST https://mcp.baisoln.com/letta/mcp`
**Tools**: 19 | **Tenant**: Required
**Version**: 3.1.0

### Important: Letta Scoping Protocol

Letta has a hierarchical entity model. Correct scoping is critical:

```
Tenant (tenant_id)                    ← Letta server instance + org identity
├── Identity (identity_id)            ← Users, orgs, entities
│   └── Agent (agent_id)              ← AI agents with memory
│       ├── Core Memory (blocks)      ← Key-value pairs (preferences, persona)
│       ├── Archival Memory (passages) ← Long-term RAG storage (vector search)
│       └── Conversations             ← Message history
├── Group (group_id)                  ← Multi-agent groups
│   └── Group Conversation            ← Multi-agent chat
├── Archive (archive_id)              ← Shared archival stores
└── Source (source_id)                ← Data sources (file uploads)
```

**For user-scoped operations**, use `lt_user_memory` — it auto-resolves users to dedicated agents.
**For agent-level operations**, use `lt_agent` and `lt_memory` with explicit `agent_id`.

### Registration

```json
{
  "name": "lt_register_tenant",
  "arguments": {
    "tenant_id": "vc-livekit",
    "base_url": "http://letta-server.letta.svc.cluster.local:8283",
    "org_identity_id": "identity-3bb74d4b-fb60-4252-9906-a48f3f8026a2"
  }
}
```

Optional: `password`, `timeout`, `max_concurrency`, `graphiti_url`.

### Tools Overview

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `lt_register_tenant` | Register Letta server connection | `tenant_id`, `base_url` |
| `lt_list_tenants` | List all registered tenants | — |
| `lt_user_memory` | **High-level** user-scoped memory (auto agent resolution) | `tenant_id`, `user_id`, `operation` |
| `lt_agent` | Agent lifecycle, messaging, context | `tenant_id`, `operation` |
| `lt_memory` | Core memory blocks and archival passages | `tenant_id`, `operation` |
| `lt_identity` | User/org identity management | `tenant_id`, `operation` |
| `lt_group` | Agent group CRUD and membership | `tenant_id`, `operation` |
| `lt_conversation` | Multi-agent group conversations | `tenant_id`, `operation` |
| `lt_archive` | Shared archival memory stores | `tenant_id`, `operation` |
| `lt_tool_manager` | Create, list, attach tools to agents | `tenant_id`, `operation` |
| `lt_source_manager` | Data source upload and attachment | `tenant_id`, `operation` |
| `lt_file_folder_ops` | File session and folder management | `tenant_id`, `operation` |
| `lt_mcp_ops` | Connect external MCP servers to agents | `tenant_id`, `operation` |
| `lt_temporal_memory` | Graphiti knowledge graph memory | `tenant_id`, `operation` |
| `lt_run` | Agent run traces, steps, feedback | `tenant_id`, `operation` |
| `lt_job_monitor` | Background job status | `tenant_id`, `operation` |
| `lt_model_provider` | LLM model and provider management | `tenant_id`, `operation` |
| `lt_sandbox` | Sandbox execution environments | `tenant_id`, `operation` |
| `lt_misc` | Tags, global search, health, chat completions | `tenant_id`, `operation` |

### lt_user_memory (Recommended for User-Scoped RAG)

Auto-resolves `user_id` to a dedicated RAG agent. Creates identity + agent on first use.

**Operations:**

| Operation | Description | Additional Params |
|-----------|-------------|-------------------|
| `store_archival` | Store a passage in user's archival memory | `content` (required), `source` (optional tag) |
| `search` | Semantic search across user's archival memory | `query` (required), `limit` |
| `get_core` | Get user's core memory blocks | — |
| `update_core` | Update a core memory block | `key`, `value` |
| `delete_by_source` | Delete passages by source tag | `source` |

```json
// Store a document chunk for a user
{
  "name": "lt_user_memory",
  "arguments": {
    "tenant_id": "vc-livekit",
    "user_id": "user_2abc123",
    "operation": "store_archival",
    "content": "The quarterly report shows 15% revenue growth.",
    "source": "doc:quarterly-report-q1"
  }
}

// Search user's memory
{
  "name": "lt_user_memory",
  "arguments": {
    "tenant_id": "vc-livekit",
    "user_id": "user_2abc123",
    "operation": "search",
    "query": "revenue growth",
    "limit": 5
  }
}
```

### lt_agent Operations

| Operation | Description | Key Params |
|-----------|-------------|------------|
| `list` | List all agents | `limit`, `offset` |
| `get` | Get agent details | `agent_id` |
| `create` | Create an agent | `name`, `model`, `embedding_model`, `system_prompt` |
| `update` | Update agent config | `agent_id`, (fields to update) |
| `delete` | Delete an agent | `agent_id` |
| `send_message` | Send message to agent | `agent_id`, `message`, `role` |
| `get_context` | Get agent's context window | `agent_id` |
| `get_messages` | Get message history | `agent_id`, `limit` |
| `attach_identity` | Attach identity to agent | `agent_id`, `identity_id` |
| `detach_identity` | Detach identity | `agent_id`, `identity_id` |
| `attach_tool` | Attach tool to agent | `agent_id`, `tool_id` |
| `detach_tool` | Detach tool | `agent_id`, `tool_id` |
| `import` | Import agent from data | `import_data` |
| `export` | Export agent data | `agent_id` |
| `version` | Get agent version | `agent_id` |

### lt_memory Operations

| Operation | Description | Key Params |
|-----------|-------------|------------|
| `get_core` | Get core memory | `agent_id` |
| `list_blocks` | List memory blocks | `agent_id` |
| `get_block` | Get a block by ID | `block_id` |
| `update_block` | Update block value | `block_id`, `value` |
| `create_block` | Create new block | `label`, `value` |
| `attach_block` | Attach block to agent | `agent_id`, `block_id` |
| `detach_block` | Detach block | `agent_id`, `block_id` |
| `list_passages` | List archival passages | `agent_id` |
| `insert_passage` | Insert archival passage | `agent_id`, `text` |
| `update_passage` | Update passage text | `passage_id`, `text` |
| `delete_passage` | Delete a passage | `passage_id` |
| `search_archival` | Semantic search passages | `agent_id`, `query` |

### lt_identity Operations

| Operation | Description | Key Params |
|-----------|-------------|------------|
| `list` | List identities | `limit`, `offset` |
| `get` | Get identity by ID | `identity_id` |
| `create` | Create identity | `name`, `identifier`, `identity_type` |
| `update` | Update identity | `identity_id`, (fields) |
| `delete` | Delete identity | `identity_id` |
| `upsert` | Create or update identity | `identifier`, `name`, `identity_type` |

---

## 5. AI/GPU Server

**Path**: `POST https://mcp.baisoln.com/ai/mcp`
**Tools**: 30 | **Tenant**: Required

### Tool Categories

#### LLM (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_list_models` | List available models | `tenant_id` |
| `ai_chat_completion` | Chat with an LLM | `tenant_id`, `model`, `messages` |
| `ai_text_completion` | Text completion from prompt | `tenant_id`, `model`, `prompt` |

#### Embeddings (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_create_embeddings` | Generate vector embeddings | `tenant_id`, `model`, `input_text` |
| `ai_embeddings_get_status` | Check async embedding task | `tenant_id` |
| `ai_embeddings_analysis_prompt` | Natural language embedding analysis | `tenant_id`, `prompt` |

#### Audio/Speech (7 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_create_audio_transcription` | Transcribe audio (Whisper) | `tenant_id`, `file_data`, `filename` |
| `ai_create_audio_translation` | Translate audio to English | `tenant_id`, `file_data`, `filename` |
| `ai_audio_speech_to_text` | Speech to text (multi-provider) | `tenant_id`, `audio_data` |
| `ai_audio_text_to_speech` | Text to speech (GPU-AI/ElevenLabs) | `tenant_id`, `text` |
| `ai_text_to_speech_prompt` | Natural language TTS control | `tenant_id`, `prompt` |
| `ai_audio_list_models` | List audio models | `tenant_id` |
| `ai_audio_voice_clone_xtts_v2` | Clone voice with XTTS v2 | `tenant_id`, `text`, `voice_id` |
| `ai_xtts_v2_list_models` | List XTTS v2 models | `tenant_id` |

#### Image (2 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_create_image` | Generate image from prompt | `tenant_id`, `prompt` |
| `ai_create_moderation` | Content moderation | `tenant_id`, `input_text` |

#### Video (8 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_generate_video` | Generate video from text | `tenant_id`, `prompt` |
| `ai_recognize_video` | Analyze video content | `tenant_id`, `video_data` |
| `ai_video_synopsis` | Generate video summary | `tenant_id`, `video_data` |
| `ai_video_qa` | Q&A about video content | `tenant_id`, `video_data`, `question` |
| `ai_video_get_status` | Check async video task | `tenant_id` |
| `ai_video_recognition_get_status` | Check async recognition task | `tenant_id` |
| `ai_video_generation_prompt` | Natural language video gen | `tenant_id`, `prompt` |
| `ai_video_analysis_prompt` | Natural language video analysis | `tenant_id`, `video_data`, `prompt` |

#### WAN2 Video (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_wan2_text_to_video` | Text to video (WAN2) | `tenant_id`, `prompt` |
| `ai_wan2_image_to_video` | Image to video (WAN2) | `tenant_id`, `image_data` |
| `ai_wan2_compress_video` | Compress video (WAN2) | `tenant_id`, `video_data` |
| `ai_wan2_get_status` | Check WAN2 task status | `tenant_id` |

#### Utility (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ai_get_mcp_tools` | Discover GPU-AI MCP tools | `tenant_id` |
| `ai_proxy_service_request` | Raw HTTP proxy to GPU-AI | `tenant_id`, `service_name`, `path` |
| `ai_register_tenant` | Register AI tenant | `tenant_id` |

### Example: Chat Completion

```json
{
  "name": "ai_chat_completion",
  "arguments": {
    "tenant_id": "vc-livekit",
    "model": "openai/gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Summarize the benefits of RAG."}
    ],
    "temperature": 0.7,
    "max_tokens": 500
  }
}
```

---

## 6. MeiliSearch Server

**Path**: `POST https://mcp.baisoln.com/meilisearch/mcp`
**Tools**: 9 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ms_register_tenant` | Register MeiliSearch instance | `tenant_id`, `url` |
| `ms_list_indexes` | List all indexes | `tenant_id` |
| `ms_get_index` | Get index details and stats | `tenant_id`, `index_uid` |
| `ms_create_index` | Create a search index | `tenant_id`, `index_uid` |
| `ms_delete_index` | Delete an index | `tenant_id`, `index_uid` |
| `ms_add_documents` | Add/replace documents | `tenant_id`, `index_uid`, `documents` (JSON string) |
| `ms_search` | Full-text search | `tenant_id`, `index_uid`, `query` |
| `ms_get_document` | Get document by ID | `tenant_id`, `index_uid`, `document_id` |
| `ms_delete_documents` | Delete documents by IDs | `tenant_id`, `index_uid`, `document_ids` (JSON string) |

### Example: Search

```json
{
  "name": "ms_search",
  "arguments": {
    "tenant_id": "vc-livekit",
    "index_uid": "products",
    "query": "wireless headphones",
    "limit": 10,
    "filter": "price < 100",
    "sort": "price:asc"
  }
}
```

---

## 7. Mail Server

**Path**: `POST https://mcp.baisoln.com/mail/mcp`
**Tools**: 4 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `mail_register_tenant` | Register mail service credentials | `tenant_id`, `api_key` |
| `mail_send_email` | Send a single email | `tenant_id`, `to`, `subject`, `body` |
| `mail_send_email_with_attachments` | Send email with attachments | `tenant_id`, `to`, `subject`, `body`, `attachments` |
| `mail_send_bulk_emails` | Send batch emails | `tenant_id`, `emails` (array) |

### Example

```json
{
  "name": "mail_send_email",
  "arguments": {
    "tenant_id": "vc-livekit",
    "to": ["user@example.com"],
    "subject": "Meeting Notes",
    "body": "<h1>Notes</h1><p>Key decisions from today's meeting...</p>",
    "body_type": "html",
    "from_name": "VC LiveKit"
  }
}
```

---

## 8. PDF Generator Server

**Path**: `POST https://mcp.baisoln.com/pdf/mcp`
**Tools**: 3 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `pdf_register_tenant` | Register tenant | `tenant_id` |
| `pdf_generate_pdf` | Generate PDF from HTML template | `tenant_id`, `template`, `content` |
| `pdf_get_pdf_file` | Retrieve generated PDF by ID | `file_id` |

### Example

```json
{
  "name": "pdf_generate_pdf",
  "arguments": {
    "tenant_id": "vc-livekit",
    "template": "<html><body><h1>{{title}}</h1><p>{{body}}</p></body></html>",
    "content": {"title": "Monthly Report", "body": "Revenue grew 15% this quarter."},
    "filename": "report-q1.pdf",
    "return_format": "base64"
  }
}
```

---

## 9. FFmpeg Server

**Path**: `POST https://mcp.baisoln.com/ffmpeg/mcp`
**Tools**: 8 | **Tenant**: Not required

All tools accept `input_data` as **base64-encoded** media.

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `ffmpeg_convert_video` | Convert video format | `input_data` |
| `ffmpeg_extract_audio` | Extract audio track from video | `input_data` |
| `ffmpeg_merge_videos` | Concatenate multiple videos | `video_data_list` (array of base64) |
| `ffmpeg_add_subtitles` | Burn subtitles onto video | `input_data`, `subtitle_text`, `start_time`, `duration` |
| `ffmpeg_trim_video` | Trim video to time range | `input_data`, `start_time` |
| `ffmpeg_get_video_info_tool` | Get video metadata | `input_data` |
| `ffmpeg_resize_video` | Resize video dimensions | `input_data`, `width`, `height` |
| `ffmpeg_extract_frame` | Extract single frame as image | `input_data`, `timestamp` |

### Example

```json
{
  "name": "ffmpeg_trim_video",
  "arguments": {
    "input_data": "<base64-encoded-video>",
    "start_time": "00:01:30",
    "duration": "00:00:45",
    "output_format": "mp4"
  }
}
```

---

## 10. GenImage Server

**Path**: `POST https://mcp.baisoln.com/genimage/mcp`
**Tools**: 4 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `gi_register_tenant` | Register Runware API credentials | `tenant_id`, `runware_api_key` |
| `gi_generate_image` | Generate image from text prompt | `tenant_id`, `prompt` |
| `gi_upscale_image` | Upscale image resolution | `tenant_id`, `image_data` |
| `gi_remove_background` | Remove image background | `tenant_id`, `image_data` |

### Example

```json
{
  "name": "gi_generate_image",
  "arguments": {
    "tenant_id": "vc-livekit",
    "prompt": "A futuristic city skyline at sunset, photorealistic",
    "width": 1024,
    "height": 768,
    "steps": 30
  }
}
```

---

## 11. Langfuse Server

**Path**: `POST https://mcp.baisoln.com/langfuse/mcp`
**Tools**: 8 | **Tenant**: Required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `lf_register_tenant` | Register Langfuse project | `tenant_id`, `secret_key`, `public_key` |
| `lf_create_trace` | Create observability trace | `tenant_id`, `name` |
| `lf_create_span` | Create span within trace | `tenant_id`, `trace_id`, `name` |
| `lf_create_generation` | Log LLM generation | `tenant_id`, `trace_id`, `name` |
| `lf_create_event` | Log event in trace | `tenant_id`, `trace_id`, `name` |
| `lf_create_score` | Score a trace/observation | `tenant_id`, `name`, `value` |
| `lf_get_trace` | Retrieve full trace | `tenant_id`, `trace_id` |
| `lf_get_project` | Get project info | `tenant_id` |

### Observability Hierarchy

```
Trace (top-level execution)
├── Span (timed work unit — retrieval, preprocessing)
├── Generation (LLM call — model, tokens, latency)
├── Event (point-in-time — cache hit, error)
└── Score (evaluation — relevance, quality)
```

### Example

```json
{
  "name": "lf_create_trace",
  "arguments": {
    "tenant_id": "vc-livekit",
    "name": "chat-completion",
    "user_id": "user_2abc123",
    "session_id": "sess_xyz",
    "metadata": {"model": "gpt-4o", "temperature": 0.7},
    "tags": ["production", "chat"]
  }
}
```

---

## 12. OpenProject Server

**Path**: `POST https://mcp.baisoln.com/openproject/mcp`
**Tools**: 38 | **Tenant**: Pre-configured (no tenant_id needed)

### Tool Categories

#### Projects (5 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `list_projects` | List all projects | — |
| `get_project` | Get project details | `project_id` |
| `create_project` | Create project | `name`, `identifier` |
| `update_project` | Update project | `project_id` |
| `delete_project` | Delete project | `project_id` |

#### Work Packages (13 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `list_work_packages` | List with filters | — |
| `get_work_package` | Get details | `work_package_id` |
| `create_work_package` | Create task/story/bug | `project_id`, `subject`, `type_id` |
| `update_work_package` | Update fields | `work_package_id` |
| `delete_work_package` | Delete work package | `work_package_id` |
| `update_work_package_status` | Change status | `work_package_id`, `status_id` |
| `assign_work_package` | Assign to user | `work_package_id` |
| `query_work_packages` | Advanced query with filters | — |
| `search_work_packages` | Text search on subjects | `query` |
| `bulk_create_work_packages` | Batch create | `project_id`, `work_packages` |
| `bulk_update_work_packages` | Batch update | `updates` |
| `get_work_package_schema` | Get allowed transitions | `work_package_id` |
| `get_available_assignees` | List possible assignees | `project_id` |

#### Hierarchy (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `set_work_package_parent` | Set parent | `work_package_id`, `parent_id` |
| `remove_work_package_parent` | Remove parent | `work_package_id` |
| `get_work_package_children` | Get children | `parent_id` |
| `get_work_package_hierarchy` | Full ancestor/descendant tree | `work_package_id` |

#### Relations (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `create_work_package_relation` | Create typed relation | `from_work_package_id`, `to_work_package_id`, `relation_type` |
| `list_work_package_relations` | List relations | — |
| `delete_work_package_relation` | Delete relation | `relation_id` |

#### Comments & Watchers (5 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `add_work_package_comment` | Add comment | `work_package_id`, `comment` |
| `list_work_package_activities` | Get activity log | `work_package_id` |
| `add_work_package_watcher` | Add watcher | `work_package_id`, `user_id` |
| `remove_work_package_watcher` | Remove watcher | `work_package_id`, `user_id` |
| `list_work_package_watchers` | List watchers | `work_package_id` |

#### Attachments (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `list_work_package_attachments` | List attachments | `work_package_id` |
| `add_work_package_attachment` | Upload file | `work_package_id`, `file_data`, `filename` |
| `delete_attachment` | Delete attachment | `attachment_id` |

#### Custom Fields (2 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `list_custom_fields` | List all custom fields | — |
| `update_work_package_custom_fields` | Update custom field values | `work_package_id`, `custom_fields` |

#### Time Tracking (3 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `log_time` | Log hours on work package | `work_package_id`, `hours` |
| `list_time_entries` | List time entries | — |
| `list_time_entry_activities` | List activity categories | — |

#### Reference Data (4 tools)

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `test_connection` | Verify API connectivity | — |
| `list_users` | List all users | — |
| `get_user` | Get user details | `user_id` |
| `list_statuses` | List work package statuses | — |
| `list_priorities` | List priorities | — |
| `list_types` | List work package types | — |

---

## 13. Calculator Server

**Path**: `POST https://mcp.baisoln.com/calculator/mcp`
**Tools**: 7 | **Tenant**: Not required

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `calc_add` | Add two numbers | `a`, `b` |
| `calc_subtract` | Subtract b from a | `a`, `b` |
| `calc_multiply` | Multiply two numbers | `a`, `b` |
| `calc_divide` | Divide a by b | `a`, `b` |
| `calc_power` | Raise base to exponent | `base`, `exponent` |
| `calc_sqrt` | Square root | `value` |
| `calc_modulo` | Remainder of a / b | `a`, `b` |

---

## 14. Search Server

**Path**: `POST https://mcp.baisoln.com/search/mcp`
**Tools**: 4 | **Tenant**: Not required

Backends: SearXNG (meta-search) + Crawl4AI (web crawling). Results are cached in Redis.

### Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `web_search` | Search the web via SearXNG | `query` |
| `web_crawl` | Deep crawl and extract webpage content | `url` |
| `extract_content` | Extract specific content via CSS selectors | `url` |
| `analyze_search_results` | Score and rank search results | `query`, `results` |

### web_search

```json
{
  "name": "web_search",
  "arguments": {
    "query": "kubernetes horizontal pod autoscaler best practices",
    "engines": "google,duckduckgo,brave",
    "categories": "general",
    "language": "en",
    "max_results": 10
  }
}
```

### web_crawl

```json
{
  "name": "web_crawl",
  "arguments": {
    "url": "https://docs.example.com/api-reference",
    "extraction_strategy": "markdown",
    "screenshot": false,
    "timeout": 30
  }
}
```

---

## Quick Start

### 1. Initialize a session

```bash
curl -s -D - -X POST https://mcp.baisoln.com/letta/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
    "protocolVersion":"2024-11-05",
    "capabilities":{},
    "clientInfo":{"name":"my-client","version":"1.0"}
  }}'
# Extract Mcp-Session-Id from response headers
```

### 2. Call a tool

```bash
curl -s -X POST https://mcp.baisoln.com/letta/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: <session-id>" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{
    "name":"lt_user_memory",
    "arguments":{
      "tenant_id":"vc-livekit",
      "user_id":"user_123",
      "operation":"search",
      "query":"meeting notes"
    }
  }}'
```

### 3. Response format

Responses use **Server-Sent Events** (SSE):
```
event: message
data: {"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{...}"}]}}
```

Parse the `data:` line as JSON. Tool results are in `result.content[0].text`.
