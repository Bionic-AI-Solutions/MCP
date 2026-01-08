# MinIO MCP Server - Usage Guide

## Overview

The MinIO MCP server provides object storage operations with multi-tenant support. Each tenant can connect to their own MinIO instance or S3-compatible storage.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

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

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-minio-server

# Server will be available at http://localhost:8002
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your MinIO connection details:

**Tool:** `minio_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `endpoint` (required): MinIO server endpoint (e.g., "localhost:9000")
- `access_key` (required): MinIO access key
- `secret_key` (required): MinIO secret key
- `secure` (optional): Use HTTPS (default: `true`)
- `region` (optional): AWS region (default: `None`)

**Example:**
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

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `minio_list_buckets` - List Buckets

List all buckets for a tenant.

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
  "buckets": [
    {
      "name": "my-bucket",
      "creation_date": "2024-01-01T00:00:00"
    }
  ]
}
```

### 2. `minio_create_bucket` - Create Bucket

Create a new bucket.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket to create
- `region` (optional): AWS region for the bucket

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-new-bucket",
  "region": null
}
```

**Response:**
```json
{
  "success": true,
  "message": "Bucket 'my-new-bucket' created successfully"
}
```

### 3. `minio_delete_bucket` - Delete Bucket

Delete a bucket (must be empty).

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket to delete

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket"
}
```

### 4. `minio_bucket_exists` - Check Bucket Exists

Check if a bucket exists.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket to check

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket"
}
```

**Response:**
```json
{
  "success": true,
  "exists": true
}
```

### 5. `minio_list_objects` - List Objects

List objects in a bucket.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket
- `prefix` (optional): Object name prefix filter
- `recursive` (optional): List recursively (default: `true`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket",
  "prefix": "documents/",
  "recursive": true
}
```

**Response:**
```json
{
  "success": true,
  "objects": [
    {
      "name": "documents/file1.pdf",
      "size": 1024,
      "last_modified": "2024-01-01T00:00:00",
      "etag": "abc123"
    }
  ]
}
```

### 6. `minio_upload_object` - Upload Object

Upload an object to a bucket.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket
- `object_name` (required): Object name/path
- `data` (required): Object data as string
- `content_type` (optional): MIME type of the object

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket",
  "object_name": "test.txt",
  "data": "Hello, MinIO!",
  "content_type": "text/plain"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Object 'test.txt' uploaded successfully"
}
```

### 7. `minio_download_object` - Download Object

Download an object from a bucket.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket
- `object_name` (required): Object name/path

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket",
  "object_name": "test.txt"
}
```

**Response:**
```json
{
  "success": true,
  "data": "Hello, MinIO!",
  "size": 13
}
```

### 8. `minio_delete_object` - Delete Object

Delete an object from a bucket.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `bucket_name` (required): Name of the bucket
- `object_name` (required): Object name/path

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "bucket_name": "my-bucket",
  "object_name": "test.txt"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Object 'test.txt' deleted successfully"
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: MINIO_TENANT_{TENANT_ID}_ENDPOINT
export MINIO_TENANT_1_ENDPOINT="localhost:9000"
export MINIO_TENANT_1_ACCESS_KEY="minioadmin"
export MINIO_TENANT_1_SECRET_KEY="minioadmin123"
export MINIO_TENANT_1_SECURE="false"
```

## Features

- **Multi-tenant**: Each tenant connects to their own MinIO instance
- **S3-compatible**: Works with any S3-compatible storage
- **Redis persistence**: Tenant configurations persist across restarts
- **Full CRUD operations**: Create, read, update, and delete buckets and objects

## Resources

Access tenant information as resources:

- `minio://{tenant_id}/buckets` - Get list of buckets for a tenant
- `minio://info` - Get information about the MinIO MCP server

## Example Workflow

1. Register your tenant:
   ```
   minio_register_tenant(tenant_id="my-tenant", endpoint="localhost:9000", access_key="minioadmin", secret_key="minioadmin123")
   ```

2. Create a bucket:
   ```
   minio_create_bucket(tenant_id="my-tenant", bucket_name="my-bucket")
   ```

3. Upload an object:
   ```
   minio_upload_object(tenant_id="my-tenant", bucket_name="my-bucket", object_name="test.txt", data="Hello, MinIO!")
   ```

4. List objects:
   ```
   minio_list_objects(tenant_id="my-tenant", bucket_name="my-bucket")
   ```

5. Download an object:
   ```
   minio_download_object(tenant_id="my-tenant", bucket_name="my-bucket", object_name="test.txt")
   ```

## Notes

- Tenant configurations are stored in Redis (DB 2)
- Buckets must be empty before deletion
- Object data is sent as UTF-8 strings
- The server is compatible with AWS S3 and other S3-compatible storage services
- Use `prefix` parameter to filter objects by path prefix

