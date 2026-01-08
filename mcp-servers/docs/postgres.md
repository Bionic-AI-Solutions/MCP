# PostgreSQL MCP Server - Usage Guide

## Overview

The PostgreSQL MCP server provides database operations with multi-tenant support. Each tenant can connect to their own PostgreSQL database instance.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "postgres-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/postgres/mcp",
      "description": "PostgreSQL MCP Server - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-postgres-server

# Server will be available at http://localhost:8001
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your PostgreSQL connection details:

**Tool:** `pg_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `host` (required): PostgreSQL host address
- `database` (required): Database name
- `user` (required): Database username
- `password` (required): Database password
- `port` (optional): Database port (default: `5432`)
- `min_pool_size` (optional): Minimum connection pool size (default: `2`)
- `max_pool_size` (optional): Maximum connection pool size (default: `10`)
- `ssl` (optional): Use SSL/TLS connection (default: `false`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "host": "localhost",
  "database": "mydb",
  "user": "postgres",
  "password": "password",
  "port": 5432,
  "min_pool_size": 2,
  "max_pool_size": 10,
  "ssl": false
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `pg_execute_query` - Execute SQL Query

Execute a SQL query and return results.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `query` (required): SQL query string
- `params` (optional): List of parameters for parameterized queries

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "query": "SELECT * FROM users WHERE age > %s",
  "params": [18]
}
```

**Response:**
```json
{
  "success": true,
  "row_count": 5,
  "columns": ["id", "name", "age", "email"],
  "rows": [
    {"id": 1, "name": "John", "age": 25, "email": "john@example.com"},
    ...
  ]
}
```

### 2. `pg_list_tables` - List Tables

List all tables in a schema.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `schema` (optional): Schema name (default: `"public"`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "schema": "public"
}
```

**Response:**
```json
{
  "success": true,
  "schema": "public",
  "tables": [
    {"name": "users", "type": "BASE TABLE"},
    {"name": "orders", "type": "BASE TABLE"}
  ]
}
```

### 3. `pg_describe_table` - Describe Table

Get detailed information about a table structure.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `table_name` (required): Name of the table
- `schema` (optional): Schema name (default: `"public"`)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "table_name": "users",
  "schema": "public"
}
```

**Response:**
```json
{
  "success": true,
  "schema": "public",
  "table": "users",
  "columns": [
    {
      "name": "id",
      "type": "integer",
      "nullable": false,
      "default": "nextval('users_id_seq'::regclass)",
      "max_length": null
    },
    {
      "name": "name",
      "type": "character varying",
      "nullable": false,
      "default": null,
      "max_length": 255
    }
  ]
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: POSTGRES_TENANT_{TENANT_ID}_HOST
export POSTGRES_TENANT_1_HOST="localhost"
export POSTGRES_TENANT_1_PORT="5432"
export POSTGRES_TENANT_1_DATABASE="mydb"
export POSTGRES_TENANT_1_USER="postgres"
export POSTGRES_TENANT_1_PASSWORD="password"
export POSTGRES_TENANT_1_SSL="false"
```

## Features

- **Multi-tenant**: Each tenant connects to their own PostgreSQL database
- **Connection pooling**: Configurable connection pool per tenant
- **Redis persistence**: Tenant configurations persist across restarts
- **Parameterized queries**: Support for safe parameterized SQL queries
- **Schema introspection**: List tables and describe table structures

## Resources

Access tenant information as resources:

- `postgres://{tenant_id}/tables` - Get list of tables for a tenant
- `postgres://info` - Get information about the PostgreSQL MCP server

## Example Workflow

1. Register your tenant:
   ```
   pg_register_tenant(tenant_id="my-tenant", host="localhost", database="mydb", user="postgres", password="password")
   ```

2. List tables:
   ```
   pg_list_tables(tenant_id="my-tenant")
   ```

3. Describe a table:
   ```
   pg_describe_table(tenant_id="my-tenant", table_name="users")
   ```

4. Execute a query:
   ```
   pg_execute_query(tenant_id="my-tenant", query="SELECT * FROM users LIMIT 10")
   ```

## Notes

- Tenant configurations are stored in Redis (DB 1)
- Connection pools are managed per tenant
- Use parameterized queries to prevent SQL injection
- The server supports both SELECT and non-SELECT queries
- For non-SELECT queries, the response includes `row_count` indicating affected rows

