# MeiliSearch MCP Server - Usage Guide

## Overview

The MeiliSearch MCP server provides search engine operations with multi-tenant support. Each tenant can connect to their own MeiliSearch instance.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

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

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-meilisearch-server

# Server will be available at http://localhost:8007
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your MeiliSearch connection details:

**Tool:** `ms_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `url` (required): MeiliSearch server URL (e.g., `"http://meilisearch.meilisearch:7700"`)
- `api_key` (optional): MeiliSearch master key or search key
- `timeout` (optional): Request timeout in seconds (default: `5`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "url": "http://meilisearch.meilisearch:7700",
  "api_key": "your-master-key",
  "timeout": 5
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `ms_list_indexes` - List Indexes

List all indexes for a tenant.

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
  "tenant_id": "my-tenant",
  "count": 2,
  "indexes": [
    {
      "uid": "products",
      "primaryKey": "id",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 2. `ms_get_index` - Get Index Information

Get information about a specific index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "index": {
    "uid": "products",
    "primaryKey": "id",
    "createdAt": "2024-01-01T00:00:00Z",
    "updatedAt": "2024-01-01T00:00:00Z"
  }
}
```

### 3. `ms_create_index` - Create Index

Create a new index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID to create
- `primary_key` (optional): Primary key field name

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products",
  "primary_key": "id"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "index": {
    "uid": "products",
    "primaryKey": "id"
  }
}
```

### 4. `ms_delete_index` - Delete Index

Delete an index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID to delete

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Index 'products' deleted successfully"
}
```

### 5. `ms_add_documents` - Add Documents

Add documents to an index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID
- `documents` (required): JSON string array of documents to add
- `primary_key` (optional): Primary key field name

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products",
  "documents": "[{\"id\": 1, \"name\": \"Product 1\", \"price\": 99.99}, {\"id\": 2, \"name\": \"Product 2\", \"price\": 149.99}]"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "task": {
    "uid": 1,
    "indexUid": "products",
    "status": "enqueued",
    "type": "documentAddition"
  }
}
```

### 6. `ms_search` - Search Documents

Search documents in an index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID to search
- `query` (required): Search query string
- `limit` (optional): Maximum number of results (default: `20`)
- `offset` (optional): Offset for pagination (default: `0`)
- `filter` (optional): Filter expression
- `sort` (optional): JSON string array of sort fields

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products",
  "query": "laptop",
  "limit": 10,
  "offset": 0,
  "sort": "[\"price:asc\"]"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "query": "laptop",
  "hits": [
    {
      "id": 1,
      "name": "Laptop Computer",
      "price": 999.99
    }
  ],
  "estimated_total_hits": 1,
  "limit": 10,
  "offset": 0,
  "processing_time_ms": 5
}
```

### 7. `ms_get_document` - Get Document

Get a single document by ID.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID
- `document_id` (required): Document ID

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products",
  "document_id": "1"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "document": {
    "id": 1,
    "name": "Product 1",
    "price": 99.99
  }
}
```

### 8. `ms_delete_documents` - Delete Documents

Delete documents from an index.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `index_uid` (required): Index UID
- `document_ids` (required): JSON string array of document IDs

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "index_uid": "products",
  "document_ids": "[\"1\", \"2\"]"
}
```

**Response:**
```json
{
  "success": true,
  "tenant_id": "my-tenant",
  "task": {
    "uid": 2,
    "indexUid": "products",
    "status": "enqueued",
    "type": "documentDeletion"
  }
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: MEILISEARCH_TENANT_{TENANT_ID}_URL
export MEILISEARCH_TENANT_1_URL="http://meilisearch.meilisearch:7700"
export MEILISEARCH_TENANT_1_API_KEY="your-master-key"
```

## Features

- **Multi-tenant**: Each tenant connects to their own MeiliSearch instance
- **Full-text search**: Powerful search capabilities with typo tolerance
- **Index management**: Create, list, and delete indexes
- **Document operations**: Add, get, search, and delete documents
- **Filtering and sorting**: Advanced search with filters and sorting
- **Redis persistence**: Tenant configurations persist across restarts

## Resources

Access tenant information as resources:

- `meilisearch://{tenant_id}/info` - Get tenant-specific information including index count
- `meilisearch://info` - Get information about the MeiliSearch MCP server

## Example Workflow

1. Register your tenant:
   ```
   ms_register_tenant(tenant_id="my-tenant", url="http://meilisearch:7700", api_key="master-key")
   ```

2. Create an index:
   ```
   ms_create_index(tenant_id="my-tenant", index_uid="products", primary_key="id")
   ```

3. Add documents:
   ```
   ms_add_documents(tenant_id="my-tenant", index_uid="products", documents="[{\"id\": 1, \"name\": \"Product\"}]")
   ```

4. Search documents:
   ```
   ms_search(tenant_id="my-tenant", index_uid="products", query="product", limit=10)
   ```

5. Get a document:
   ```
   ms_get_document(tenant_id="my-tenant", index_uid="products", document_id="1")
   ```

## Notes

- Tenant configurations are stored in Redis (DB 5)
- Documents must be provided as JSON string arrays
- Search supports typo tolerance and ranking
- Filter expressions follow MeiliSearch filter syntax
- Sort fields should be provided as JSON string arrays (e.g., `"[\"price:asc\", \"name:desc\"]"`)
- Task-based operations (add/delete) return task objects that can be monitored
- The server supports both master keys and search keys for authentication


