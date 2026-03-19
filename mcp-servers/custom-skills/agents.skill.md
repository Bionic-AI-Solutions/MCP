---
name: agents
description: Manage Letta AI agents, memory, tools, conversations, and multi-agent groups via the mega-tool pattern.
allowed-tools: Bash, TodoWrite
argument-hint: "<agent|memory|tool|conversation|group|...> <operation> [args] [--tenant <id>]"
---

# Letta Agent MCP Server

Server: `letta` at `letta/mcp` (stateful transport)
Multi-tenant. Default tenant: `base`.

Uses the "mega-tool" pattern: each tool is a dispatcher with an `operation` parameter that selects the action. Operation-specific arguments are passed as additional JSON fields.

## Tool Inventory

| Tool | Operations | Description |
|------|-----------|-------------|
| `lt_register_tenant` | (direct) | Register a Letta tenant with base_url and credentials |
| `lt_list_tenants` | (direct) | List all registered tenants |
| `lt_agent` | `create, update, delete, list, get, run, clone, migrate` | Agent lifecycle: create, configure, run messages, clone |
| `lt_memory` | `get, update, attach, detach, list, create, delete, search` | Agent memory blocks: read/write core memory, attach/detach blocks |
| `lt_tool_manager` | `list, get, create, update, delete, attach, detach` | Manage tools available to agents |
| `lt_source_manager` | `create, upload, list, attach, detach` | Data sources: create, upload files, attach to agents |
| `lt_job_monitor` | `list, get, wait, cancel` | Monitor background jobs (uploads, migrations) |
| `lt_file_folder_ops` | (various) | File and folder management |
| `lt_mcp_ops` | (various) | MCP integration management |
| `lt_temporal_memory` | `search, list, update, delete` | Episodic/temporal memory: search and manage time-based memories |
| `lt_conversation` | (various) | Conversation and message history management |
| `lt_group` | (various) | Multi-agent groups: create, manage, run group conversations |
| `lt_identity` | (various) | Agent identity management |
| `lt_run` | (various) | Execution session management |
| `lt_archive` | (various) | Archive and retrieve agent data |
| `lt_model_provider` | (various) | LLM provider and model configuration |
| `lt_sandbox` | (various) | Sandbox environment management |
| `lt_misc` | `health, version, config` | System utilities: health check, version info, config |

## Calling Convention

All tools take `tenant_id` and `operation` as main parameters. Additional operation-specific arguments are passed as top-level JSON fields:

```
{"tenant_id": "base", "operation": "<op>", "key1": "val1", "key2": "val2"}
```

## Usage Examples

Create an agent:
```bash
~/.claude/bin/mcp-rpc call letta lt_agent '{"tenant_id": "base", "operation": "create", "name": "my-assistant", "model": "openai/gpt-4o", "embedding": "openai/text-embedding-3-small", "instructions": "You are a helpful assistant."}'
```

Send a message to an agent:
```bash
~/.claude/bin/mcp-rpc call letta lt_agent '{"tenant_id": "base", "operation": "run", "agent_id": "<agent-id>", "message": "Hello, what can you help me with?"}'
```

Read an agent's core memory:
```bash
~/.claude/bin/mcp-rpc call letta lt_memory '{"tenant_id": "base", "operation": "get", "agent_id": "<agent-id>"}'
```

## Notes

- Use `lt_agent` with `operation: "list"` to discover agent IDs before other operations.
- The `run` operation on `lt_agent` sends a message and returns the agent's response.
- Memory blocks are the agent's persistent context (persona, human info, custom blocks).
- `lt_temporal_memory` accesses the Graphiti-backed episodic memory system.
- Background operations (uploads, migrations) return a `job_id` -- use `lt_job_monitor` to track progress.
- `lt_misc` with `operation: "health"` is useful for connectivity verification.
