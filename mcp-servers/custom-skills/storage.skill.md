---
name: storage
description: Manage S3-compatible object storage buckets and objects via the MinIO MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<action> [bucket] [object] [--tenant <id>]"
---

# MinIO Object Storage MCP Server

Server: `minio` at `minio/mcp` (stateful transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `minio_list_buckets` | `tenant_id` | List all buckets |
| `minio_create_bucket` | `tenant_id, bucket_name` | Create a bucket |
| `minio_delete_bucket` | `tenant_id, bucket_name` | Delete a bucket (must be empty) |
| `minio_bucket_exists` | `tenant_id, bucket_name` | Check if a bucket exists |
| `minio_list_objects` | `tenant_id, bucket_name, prefix?, recursive?` | List objects in a bucket |
| `minio_upload_object` | `tenant_id, bucket_name, object_name, data (base64), content_type` | Upload an object |
| `minio_download_object` | `tenant_id, bucket_name, object_name` | Download an object (returns base64) |
| `minio_delete_object` | `tenant_id, bucket_name, object_name` | Delete an object |
| `minio_register_tenant` | `tenant_id, endpoint, access_key, secret_key, secure?` | Register a MinIO connection |

## Usage Examples

List all buckets:
```bash
~/.claude/bin/mcp-rpc call minio minio_list_buckets '{"tenant_id": "base"}'
```

Upload a file (data must be base64-encoded):
```bash
~/.claude/bin/mcp-rpc call minio minio_upload_object '{"tenant_id": "base", "bucket_name": "my-bucket", "object_name": "hello.txt", "data": "SGVsbG8gV29ybGQ=", "content_type": "text/plain"}'
```

List objects with a prefix filter:
```bash
~/.claude/bin/mcp-rpc call minio minio_list_objects '{"tenant_id": "base", "bucket_name": "my-bucket", "prefix": "logs/", "recursive": true}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default connection.
- Register additional tenants with `minio_register_tenant` or via K8s secret `mcp-minio-tenants`.
- Bucket names must be at least 3 characters (S3 naming rules).
- Upload data must be base64-encoded; downloads return base64-encoded content.
