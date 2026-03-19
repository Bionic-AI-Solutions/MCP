---
name: observe
description: Create traces, spans, generations, events, and scores in Langfuse for LLM observability.
allowed-tools: Bash, TodoWrite
argument-hint: "<trace|span|generation|event|score|project> [args] [--tenant <id>]"
---

# Langfuse Observability MCP Server

Server: `langfuse` at `langfuse/mcp` (stateless transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `lf_register_tenant` | `tenant_id, host, public_key, secret_key` | Register a new Langfuse tenant |
| `lf_create_trace` | `tenant_id, name, input?, output?, metadata?, session_id?, user_id?, tags?` | Create a new trace (top-level unit of observation) |
| `lf_create_span` | `tenant_id, trace_id, name, input?, output?, metadata?, parent_span_id?` | Create a span within a trace (timed operation) |
| `lf_create_generation` | `tenant_id, trace_id, name, model, prompt?, completion?, usage?, metadata?` | Log an LLM generation with model, tokens, and cost |
| `lf_create_event` | `tenant_id, trace_id, name, input?, output?, metadata?` | Create a point-in-time event within a trace |
| `lf_create_score` | `tenant_id, trace_id, name, value (float), comment?` | Attach a numeric score to a trace for evaluation |
| `lf_get_trace` | `tenant_id, trace_id` | Retrieve a trace and its nested observations |
| `lf_get_project` | `tenant_id` | Get project info for the tenant |

## Usage Examples

Create a trace and log a generation:
```bash
~/.claude/bin/mcp-rpc call langfuse lf_create_trace '{"tenant_id": "base", "name": "chat-request", "tags": ["production"], "user_id": "user-42"}'
```

Log an LLM generation within a trace:
```bash
~/.claude/bin/mcp-rpc call langfuse lf_create_generation '{"tenant_id": "base", "trace_id": "<trace-id>", "name": "gpt-4-call", "model": "gpt-4", "prompt": "Summarize this article", "completion": "The article discusses...", "usage": {"prompt_tokens": 150, "completion_tokens": 80}}'
```

Attach a quality score to a trace:
```bash
~/.claude/bin/mcp-rpc call langfuse lf_create_score '{"tenant_id": "base", "trace_id": "<trace-id>", "name": "relevance", "value": 0.95, "comment": "Highly relevant response"}'
```

## Notes

- Traces are the top-level container. Spans, generations, and events are nested within traces.
- The `usage` parameter on `lf_create_generation` accepts `{"prompt_tokens": N, "completion_tokens": N}`.
- Use `session_id` on traces to group multiple traces into a session (e.g., a conversation).
- Use `tags` on traces for filtering in the Langfuse UI (e.g., `["production", "v2"]`).
- Scores can be used for evaluation pipelines -- attach multiple named scores to the same trace.
- `metadata` on any tool accepts arbitrary JSON for custom context.
