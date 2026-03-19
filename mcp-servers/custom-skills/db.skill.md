---
name: db
description: Execute SQL queries and manage transactions on PostgreSQL via the Postgres MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<query|action> [--tenant <id>]"
---

# PostgreSQL MCP Server

Server: `postgres` at `postgres/mcp` (stateful transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `pg_execute_query` | `tenant_id, query, params?, role?` | Execute a SQL query |
| `pg_list_tables` | `tenant_id, schema` | List tables in a schema |
| `pg_describe_table` | `tenant_id, table_name, schema` | Get column definitions for a table |
| `pg_begin_transaction` | `tenant_id` | Begin a transaction, returns txn_id |
| `pg_commit_transaction` | `tenant_id, transaction_id` | Commit a transaction |
| `pg_rollback_transaction` | `tenant_id, transaction_id` | Rollback a transaction |
| `pg_register_tenant` | `tenant_id, host, port, database, user, password` | Register a new DB connection |

## Usage Examples

Run a SELECT query:
```bash
~/.claude/bin/mcp-rpc call postgres pg_execute_query '{"tenant_id": "base", "query": "SELECT current_database(), current_user"}'
```

List tables in the public schema:
```bash
~/.claude/bin/mcp-rpc call postgres pg_list_tables '{"tenant_id": "base", "schema": "public"}'
```

Transaction workflow (begin, execute, commit):
```bash
~/.claude/bin/mcp-rpc call postgres pg_begin_transaction '{"tenant_id": "base"}'
# Use the returned transaction_id in subsequent calls
~/.claude/bin/mcp-rpc call postgres pg_execute_query '{"tenant_id": "base", "query": "INSERT INTO users (name) VALUES ($1)", "params": ["Alice"]}'
~/.claude/bin/mcp-rpc call postgres pg_commit_transaction '{"tenant_id": "base", "transaction_id": "<txn_id>"}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default connection.
- Register additional tenants with `pg_register_tenant` or via K8s secret `mcp-postgres-tenants`.
- Use parameterized queries (`params` array with `$1`, `$2` placeholders) to avoid SQL injection.
