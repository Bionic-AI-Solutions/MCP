---
name: search
description: Index, search, and manage documents in MeiliSearch via the MeiliSearch MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<action> [index] [query] [--tenant <id>]"
---

# MeiliSearch MCP Server

Server: `meilisearch` at `meilisearch/mcp` (stateful transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `ms_register_tenant` | `tenant_id, host, api_key?` | Register a MeiliSearch connection |
| `ms_list_indexes` | `tenant_id` | List all indexes |
| `ms_get_index` | `tenant_id, index_uid` | Get index details |
| `ms_create_index` | `tenant_id, index_uid, primary_key?` | Create a new index |
| `ms_delete_index` | `tenant_id, index_uid` | Delete an index |
| `ms_add_documents` | `tenant_id, index_uid, documents (list)` | Add or update documents |
| `ms_search` | `tenant_id, index_uid, query, limit?, offset?, filter?, sort?` | Full-text search with filters |
| `ms_get_document` | `tenant_id, index_uid, document_id` | Retrieve a single document by ID |
| `ms_delete_documents` | `tenant_id, index_uid, document_ids?` | Delete documents by ID list |

## Usage Examples

Create an index and add documents:
```bash
~/.claude/bin/mcp-rpc call meilisearch ms_create_index '{"tenant_id": "base", "index_uid": "products", "primary_key": "id"}'
~/.claude/bin/mcp-rpc call meilisearch ms_add_documents '{"tenant_id": "base", "index_uid": "products", "documents": [{"id": 1, "name": "Widget", "price": 9.99}, {"id": 2, "name": "Gadget", "price": 24.99}]}'
```

Search with a filter:
```bash
~/.claude/bin/mcp-rpc call meilisearch ms_search '{"tenant_id": "base", "index_uid": "products", "query": "widget", "limit": 10, "filter": "price < 20"}'
```

List all indexes:
```bash
~/.claude/bin/mcp-rpc call meilisearch ms_list_indexes '{"tenant_id": "base"}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default connection.
- Register additional tenants with `ms_register_tenant` or via K8s secret `mcp-meilisearch-tenants`.
- Filter and sort fields must be configured in index settings before use in search queries.
- An empty query string with a filter is valid for browsing/filtering without full-text search.
