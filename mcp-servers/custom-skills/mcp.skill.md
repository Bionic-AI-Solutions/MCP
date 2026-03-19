---
name: mcp
description: Universal MCP gateway — discover servers, list tools, call any tool, and health-check infrastructure.
allowed-tools: Bash, TodoWrite
argument-hint: "<servers|tools <server>|call <server> <tool> [args]|health [server|all]|discover>"
---

# MCP Universal Gateway

Discover, inspect, and call any MCP server tool without needing a specific skill.

## Commands

Parse `$ARGUMENTS` to determine the subcommand:

### `servers` — List All Servers

```bash
~/.claude/bin/mcp-rpc servers
```

Shows all 13 configured MCP servers with transport type and description.

### `tools <server>` — List Tools (Live Query)

```bash
~/.claude/bin/mcp-rpc tools <server-name>
```

Queries the server endpoint live and returns all available tools with descriptions.

### `call <server> <tool> [args-json]` — Call Any Tool

```bash
~/.claude/bin/mcp-rpc call <server-name> <tool-name> '<json-arguments>'
```

Calls the specified tool with JSON arguments. Handles session management automatically.

### `health [server|all]` — Health Check

```bash
~/.claude/bin/mcp-rpc health <server-name|all>
```

Tests connectivity and returns status, tool count, and endpoint URL.

### `discover` — Live Discovery

```bash
~/.claude/bin/mcp-rpc discover all
```

Queries all servers live and shows which are up, down, and their tool counts.

## Server Registry

| Name | Transport | Tenant | Description |
|------|-----------|--------|-------------|
| calculator | stateful | none | Math operations |
| postgres | stateful | multi | SQL database |
| minio | stateful | multi | S3 object storage |
| pdf-generator | stateful | multi | HTML to PDF |
| ffmpeg | stateless | multi | Video/audio processing |
| mail | stateful | multi | Email sending |
| openproject | stateless | single | Project management |
| meilisearch | stateful | multi | Full-text search |
| genimage | stateful | multi | AI image generation |
| ai-mcp-server | stateless | multi | GPU AI inference |
| redis | stateful | multi | Redis data structures |
| langfuse | stateless | multi | LLM observability |
| letta | stateful | multi | AI agent platform |

## Examples

```bash
# List all servers
~/.claude/bin/mcp-rpc servers

# Check which servers are online
~/.claude/bin/mcp-rpc health all

# See what tools postgres has
~/.claude/bin/mcp-rpc tools postgres

# Call calculator directly
~/.claude/bin/mcp-rpc call calculator calc_add '{"a":10,"b":20}'

# Query a database
~/.claude/bin/mcp-rpc call postgres pg_execute_query '{"tenant_id":"base","query":"SELECT version()"}'

# List Redis keys
~/.claude/bin/mcp-rpc call redis redis_keys '{"tenant_id":"base","pattern":"*"}'
```

## When to Use This Skill

- User doesn't know which specific skill to invoke
- Need to discover what tools are available
- Quick ad-hoc tool call without loading a full skill
- Health checking infrastructure
- For deeper usage of a specific server, suggest the dedicated skill (e.g., `/db`, `/cache`)
