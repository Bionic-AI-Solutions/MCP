# Available MCP Tools

This document lists all available tools for each MCP server.

## Calculator Server

The Calculator server provides basic arithmetic operations. **No tenant_id required** - it's a simple stateless server.

### Tools (7 total)

1. **`add`**
   - **Description**: Add two numbers together
   - **Parameters**:
     - `a` (float): First number
     - `b` (float): Second number
   - **Returns**: `float` - Sum of a and b
   - **Example**: `add(10, 5)` → `15.0`

2. **`subtract`**
   - **Description**: Subtract b from a
   - **Parameters**:
     - `a` (float): Number to subtract from
     - `b` (float): Number to subtract
   - **Returns**: `float` - Result of a - b
   - **Example**: `subtract(10, 3)` → `7.0`

3. **`multiply`**
   - **Description**: Multiply two numbers
   - **Parameters**:
     - `a` (float): First number
     - `b` (float): Second number
   - **Returns**: `float` - Product of a and b
   - **Example**: `multiply(6, 7)` → `42.0`

4. **`divide`**
   - **Description**: Divide a by b. Raises error if b is zero
   - **Parameters**:
     - `a` (float): Dividend
     - `b` (float): Divisor (must not be zero)
   - **Returns**: `float` - Result of a / b
   - **Example**: `divide(20, 4)` → `5.0`
   - **Error**: Raises `ValueError` if b is zero

5. **`power`**
   - **Description**: Raise base to the power of exponent
   - **Parameters**:
     - `base` (float): Base number
     - `exponent` (float): Exponent
   - **Returns**: `float` - Result of base^exponent
   - **Example**: `power(2, 8)` → `256.0`

6. **`sqrt`**
   - **Description**: Calculate the square root of a value
   - **Parameters**:
     - `value` (float): Number to take square root of (must be >= 0)
   - **Returns**: `float` - Square root of value
   - **Example**: `sqrt(64)` → `8.0`
   - **Error**: Raises `ValueError` if value is negative

7. **`modulo`**
   - **Description**: Calculate a modulo b (remainder after division)
   - **Parameters**:
     - `a` (float): Dividend
     - `b` (float): Divisor (must not be zero)
   - **Returns**: `float` - Remainder of a / b
   - **Example**: `modulo(17, 5)` → `2.0`
   - **Error**: Raises `ValueError` if b is zero

### Resources

- **`calculator://info`** - Get information about the calculator server

### Prompts

- **`calculate`** - Generate a prompt for performing a calculation
  - Parameters: `operation` (str), `numbers` (str)

---

## PostgreSQL Server (Multi-tenant)

The PostgreSQL server provides database operations with multi-tenant support. **All tools require `tenant_id`** to identify which database to connect to.

### Tools (4 total)

1. **`execute_query`**
   - **Description**: Execute a SQL query and return results
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `query` (str, **required**): SQL query to execute
     - `params` (List[Any], optional): Query parameters for parameterized queries
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether query executed successfully
     - `row_count` (int): Number of rows affected/returned
     - `columns` (List[str]): Column names (for SELECT queries)
     - `rows` (List[Dict]): Row data (for SELECT queries)
     - `message` (str): Status message (for non-SELECT queries)
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "query": "SELECT * FROM users LIMIT 10;"
     }
     ```

2. **`list_tables`**
   - **Description**: List all tables in a schema
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `schema` (str, optional): Schema name (default: "public")
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `schema` (str): Schema name
     - `tables` (List[Dict]): List of tables with `name` and `type`
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "schema": "public"
     }
     ```

3. **`describe_table`**
   - **Description**: Get detailed information about a table (column names, types, constraints)
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `table_name` (str, **required**): Name of the table
     - `schema` (str, optional): Schema name (default: "public")
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `schema` (str): Schema name
     - `table` (str): Table name
     - `columns` (List[Dict]): Column information with:
       - `name` (str): Column name
       - `type` (str): Data type
       - `nullable` (bool): Whether column allows NULL
       - `default` (str): Default value
       - `max_length` (int): Maximum length (for string types)
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "table_name": "users",
       "schema": "public"
     }
     ```

4. **`register_tenant`**
   - **Description**: Register a new tenant configuration (or update existing)
   - **Parameters**:
     - `tenant_id` (str, **required**): Unique tenant identifier
     - `host` (str, **required**): PostgreSQL host
     - `database` (str, **required**): Database name
     - `user` (str, **required**): Username
     - `password` (str, **required**): Password
     - `port` (int, optional): Port number (default: 5432)
     - `min_pool_size` (int, optional): Minimum connection pool size (default: 2)
     - `max_pool_size` (int, optional): Maximum connection pool size (default: 10)
     - `ssl` (bool, optional): Use SSL/TLS (default: false)
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "host": "localhost",
       "database": "mydb",
       "user": "postgres",
       "password": "password",
       "port": 5432
     }
     ```

### Resources

- **`postgres://{tenant_id}/tables`** - Get list of tables for a tenant as a resource
- **`postgres://info`** - Get information about the Postgres MCP server

---

## MinIO Server (Multi-tenant)

The MinIO server provides S3-compatible object storage operations with multi-tenant support. **All tools require `tenant_id`** to identify which MinIO instance to connect to.

### Tools (9 total)

#### Bucket Operations

1. **`list_buckets`**
   - **Description**: List all buckets for a tenant
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `buckets` (List[Dict]): List of buckets with `name` and `creation_date`
   - **Example**:
     ```json
     {
       "tenant_id": "1"
     }
     ```

2. **`create_bucket`**
   - **Description**: Create a new bucket
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket to create
     - `region` (str, optional): S3 region (default: None)
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message or error
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket",
       "region": "us-east-1"
     }
     ```

3. **`delete_bucket`**
   - **Description**: Delete a bucket (must be empty)
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket to delete
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message or error
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket"
     }
     ```

4. **`bucket_exists`**
   - **Description**: Check if a bucket exists
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket to check
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `exists` (bool): Whether the bucket exists
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket"
     }
     ```

#### Object Operations

5. **`list_objects`**
   - **Description**: List objects in a bucket
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket
     - `prefix` (str, optional): Object name prefix to filter by
     - `recursive` (bool, optional): List recursively (default: true)
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `objects` (List[Dict]): List of objects with:
       - `name` (str): Object name/path
       - `size` (int): Object size in bytes
       - `last_modified` (str): ISO format timestamp
       - `etag` (str): Object ETag
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket",
       "prefix": "documents/",
       "recursive": true
     }
     ```

6. **`upload_object`**
   - **Description**: Upload an object to a bucket
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket
     - `object_name` (str, **required**): Object name/path
     - `data` (str, **required**): Object data (as string, will be UTF-8 encoded)
     - `content_type` (str, optional): Content type (default: "application/octet-stream")
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message or error
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket",
       "object_name": "file.txt",
       "data": "Hello, MinIO!",
       "content_type": "text/plain"
     }
     ```

7. **`download_object`**
   - **Description**: Download an object from a bucket
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket
     - `object_name` (str, **required**): Object name/path
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, Any]` with:
     - `success` (bool): Whether operation succeeded
     - `data` (str): Object content (decoded as UTF-8)
     - `size` (int): Object size in bytes
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket",
       "object_name": "file.txt"
     }
     ```

8. **`delete_object`**
   - **Description**: Delete an object from a bucket
   - **Parameters**:
     - `tenant_id` (str, **required**): Tenant identifier
     - `bucket_name` (str, **required**): Name of the bucket
     - `object_name` (str, **required**): Object name/path
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message or error
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "bucket_name": "my-bucket",
       "object_name": "file.txt"
     }
     ```

#### Tenant Management

9. **`register_tenant`**
   - **Description**: Register a new tenant configuration (or update existing)
   - **Parameters**:
     - `tenant_id` (str, **required**): Unique tenant identifier
     - `endpoint` (str, **required**): MinIO endpoint (e.g., "localhost:9000")
     - `access_key` (str, **required**): MinIO access key
     - `secret_key` (str, **required**): MinIO secret key
     - `secure` (bool, optional): Use HTTPS/TLS (default: true)
     - `region` (str, optional): S3 region (default: None)
     - `ctx` (Context, optional): MCP context for logging
   - **Returns**: `Dict[str, str]` with success message
   - **Example**:
     ```json
     {
       "tenant_id": "1",
       "endpoint": "localhost:9000",
       "access_key": "minioadmin",
       "secret_key": "minioadmin123",
       "secure": false
     }
     ```

### Resources

- **`minio://{tenant_id}/buckets`** - Get list of buckets for a tenant as a resource
- **`minio://info`** - Get information about the MinIO MCP server

---

## Summary

| Server | Total Tools | Tenant Required | Notes |
|--------|------------|-----------------|-------|
| **Calculator** | 7 | No | Simple arithmetic operations |
| **Postgres** | 4 | Yes | Database operations with connection pooling |
| **MinIO** | 9 | Yes | S3-compatible object storage operations |

## Usage Examples

### Calculator
```json
{
  "tool": "add",
  "arguments": {"a": 10, "b": 5}
}
```

### Postgres
```json
{
  "tool": "execute_query",
  "arguments": {
    "tenant_id": "1",
    "query": "SELECT * FROM users LIMIT 10;"
  }
}
```

### MinIO
```json
{
  "tool": "list_buckets",
  "arguments": {
    "tenant_id": "1"
  }
}
```

