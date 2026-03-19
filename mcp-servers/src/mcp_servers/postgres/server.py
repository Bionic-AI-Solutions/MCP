"""
PostgreSQL MCP Server (Multi-tenant)

A FastMCP server providing PostgreSQL database operations with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

try:
    from mcp_servers.postgres.tenant_manager import PostgresTenantManager
except ImportError:
    from .tenant_manager import PostgresTenantManager

# Initialize tenant manager
tenant_manager = PostgresTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all connection pools and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Postgres Server", lifespan=lifespan)


# ============================================================================
# Request/Response Models
# ============================================================================

class QueryRequest(BaseModel):
    """Request model for SQL queries."""

    tenant_id: str = Field(..., description="Tenant identifier")
    query: str = Field(..., description="SQL query to execute")
    params: Optional[List[Any]] = Field(default=None, description="Query parameters")


class TableInfoRequest(BaseModel):
    """Request model for table information."""

    tenant_id: str = Field(..., description="Tenant identifier")
    schema: Optional[str] = Field(default="public", description="Schema name")
    table_name: Optional[str] = Field(default=None, description="Table name (optional)")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def pg_execute_query(
    tenant_id: str,
    query: str,
    params: Optional[List[Any]] = None,
    role: Optional[str] = None,
    transaction_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute an arbitrary SQL query against a tenant's PostgreSQL database and return
    the results.

    Use this tool to run any SQL statement -- SELECT, INSERT, UPDATE, DELETE, CREATE,
    ALTER, DROP, or any other valid PostgreSQL SQL. For SELECT queries the full result
    set is returned as a list of row dictionaries. For non-SELECT statements (INSERT,
    UPDATE, DELETE, DDL, etc.) the number of affected rows is returned instead.

    Prefer pg_list_tables or pg_describe_table when you only need schema metadata, as
    those tools are purpose-built and safer for introspection.

    SECURITY WARNING: This tool executes arbitrary SQL against the database. The
    ``query`` parameter is passed directly to the database engine. Callers are
    responsible for ensuring that user-supplied input is never interpolated into the
    query string. Always use the ``params`` argument for parameterized queries to
    prevent SQL injection. Passing unsanitized user input in the ``query`` string
    can lead to data leakage, data corruption, or full database compromise.

    Args:
        tenant_id (str): Tenant identifier whose PostgreSQL database to query. The
            tenant must already be registered via pg_register_tenant or pre-configured
            in the environment/Redis.
        query (str): The SQL query to execute. Supports any valid PostgreSQL SQL
            statement. Use ``%s`` placeholders for parameterized values and pass
            the corresponding values in ``params``.
        params (Optional[List[Any]], default=None): Positional parameters to bind to
            ``%s`` placeholders in the query. When provided, the query is executed as
            a parameterized statement, which protects against SQL injection. Each
            element corresponds to a ``%s`` placeholder in left-to-right order.
        role (Optional[str], default=None): PostgreSQL role to assume via SET ROLE for
            this query. The tenant's primary database user must be a member of this
            role. Enables RLS policy testing where different roles see different data.
            Roles can be created dynamically via CREATE ROLE + GRANT statements.
        transaction_id (Optional[str], default=None): If provided, execute within an
            active transaction started by pg_begin_transaction. The query will use the
            pinned connection for that transaction. If not provided, the query runs in
            auto-commit mode on a fresh connection from the pool.
        ctx (Optional[Context], default=None): MCP context for logging. Automatically
            provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the query executed without error.
        For SELECT queries:
            - row_count (int): Number of rows returned.
            - columns (List[str]): Column names in result order.
            - rows (List[Dict[str, Any]]): Result rows as column-name-keyed dicts.
        For non-SELECT queries:
            - row_count (int): Number of rows affected by the statement.
            - message (str): Confirmation message ("Query executed successfully").
    """
    if ctx:
        await ctx.info(f"Executing query for tenant: {tenant_id}" +
                       (f" as role: {role}" if role else "") +
                       (f" in transaction: {transaction_id}" if transaction_id else ""))

    async with tenant_manager.get_connection(tenant_id, role=role, transaction_id=transaction_id) as conn:
        async with conn.cursor() as cur:
            if params:
                await cur.execute(query, params)
            else:
                await cur.execute(query)

            # Try to fetch results (for SELECT queries)
            try:
                rows = await cur.fetchall()
                columns = [desc[0] for desc in cur.description] if cur.description else []
                return {
                    "success": True,
                    "row_count": len(rows),
                    "columns": columns,
                    "rows": [dict(zip(columns, row)) for row in rows],
                }
            except Exception:
                # For non-SELECT queries, return affected rows
                return {
                    "success": True,
                    "row_count": cur.rowcount,
                    "message": "Query executed successfully",
                }


@mcp.tool
async def pg_list_tables(
    tenant_id: str,
    schema: str = "public",
    role: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all tables and views in a PostgreSQL schema for a given tenant.

    Use this tool to discover what tables exist in a database before querying them.
    This is typically the first step when exploring an unfamiliar database. The
    results include both regular tables (BASE TABLE) and views (VIEW), sorted
    alphabetically by name.

    The query reads from ``information_schema.tables``, so the connected user must
    have access to the target schema for results to appear.

    Args:
        tenant_id (str): Tenant identifier whose PostgreSQL database to query. The
            tenant must already be registered via pg_register_tenant or pre-configured
            in the environment/Redis.
        schema (str, default="public"): The PostgreSQL schema to list tables from.
            Defaults to ``"public"``, which is the default schema for most PostgreSQL
            databases.
        role (Optional[str], default=None): PostgreSQL role to assume via SET ROLE.
            See pg_execute_query for details.
        ctx (Optional[Context], default=None): MCP context for logging. Automatically
            provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - schema (str): The schema that was queried.
        - tables (List[Dict]): List of table descriptors, each containing:
            - name (str): The table or view name.
            - type (str): The table type, e.g. "BASE TABLE" or "VIEW".
    """
    if ctx:
        await ctx.info(f"Listing tables for tenant: {tenant_id}, schema: {schema}")

    query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = %s
        ORDER BY table_name
    """

    async with tenant_manager.get_connection(tenant_id, role=role) as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, (schema,))
            rows = await cur.fetchall()
            return {
                "success": True,
                "schema": schema,
                "tables": [
                    {"name": row[0], "type": row[1]} for row in rows
                ],
            }


@mcp.tool
async def pg_describe_table(
    tenant_id: str,
    table_name: str,
    schema: str = "public",
    role: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed column-level metadata for a specific PostgreSQL table.

    Use this tool to inspect the structure of a table before constructing queries
    against it. Returns every column in ordinal position order, including data types,
    nullability, defaults, and maximum character lengths. This is the equivalent of
    running ``\\d <table>`` in psql.

    The query reads from ``information_schema.columns``, so the connected user must
    have access to the target schema and table for results to appear. If the table
    does not exist or the user lacks permission, the columns list will be empty.

    Note: This tool does not return index, constraint, or foreign-key information.
    Use pg_execute_query with appropriate system-catalog queries if you need those
    details.

    Args:
        tenant_id (str): Tenant identifier whose PostgreSQL database to query. The
            tenant must already be registered via pg_register_tenant or pre-configured
            in the environment/Redis.
        table_name (str): The name of the table to describe. Must be an exact,
            case-sensitive match of the table name as stored in PostgreSQL.
        schema (str, default="public"): The PostgreSQL schema containing the table.
            Defaults to ``"public"``.
        role (Optional[str], default=None): PostgreSQL role to assume via SET ROLE.
            See pg_execute_query for details.
        ctx (Optional[Context], default=None): MCP context for logging. Automatically
            provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - schema (str): The schema that was queried.
        - table (str): The table name that was described.
        - columns (List[Dict]): List of column descriptors in ordinal order, each
          containing:
            - name (str): Column name.
            - type (str): PostgreSQL data type (e.g. "integer", "character varying").
            - nullable (bool): True if the column allows NULL values.
            - default (str | None): Default value expression, or None if no default.
            - max_length (int | None): Maximum character length for character types,
              or None for non-character types.
    """
    if ctx:
        await ctx.info(f"Describing table {schema}.{table_name} for tenant: {tenant_id}")

    query = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """

    async with tenant_manager.get_connection(tenant_id, role=role) as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, (schema, table_name))
            rows = await cur.fetchall()
            return {
                "success": True,
                "schema": schema,
                "table": table_name,
                "columns": [
                    {
                        "name": row[0],
                        "type": row[1],
                        "nullable": row[2] == "YES",
                        "default": row[3],
                        "max_length": row[4],
                    }
                    for row in rows
                ],
            }


# ============================================================================
# Transaction Tools
# ============================================================================

@mcp.tool
async def pg_begin_transaction(
    tenant_id: str,
    timeout_seconds: float = 30.0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Begin a multi-statement transaction.

    Opens a dedicated database connection that is pinned to the returned
    ``transaction_id``. All subsequent ``pg_execute_query`` calls that include
    this ``transaction_id`` will run on the same connection, allowing
    multi-statement transactions with full ACID guarantees.

    The transaction is automatically rolled back if no activity occurs within
    ``timeout_seconds`` (default 30). This prevents connection leaks from
    abandoned transactions.

    Workflow::

        1. pg_begin_transaction  →  {transaction_id: "abc123"}
        2. pg_execute_query(transaction_id="abc123", query="INSERT ...")
        3. pg_execute_query(transaction_id="abc123", query="UPDATE ...")
        4. pg_commit_transaction(transaction_id="abc123")
           — or pg_rollback_transaction(transaction_id="abc123")

    Args:
        tenant_id (str): Tenant identifier.
        timeout_seconds (float, default=30.0): Seconds of inactivity before the
            transaction is automatically rolled back. Maximum recommended: 120.
        ctx (Optional[Context], default=None): MCP context for logging.

    Returns:
        Dict with:
        - success (bool): Whether the transaction was started.
        - transaction_id (str): Token to pass to subsequent queries.
        - timeout_seconds (float): The configured timeout.
    """
    if ctx:
        await ctx.info(f"Beginning transaction for tenant: {tenant_id}")

    transaction_id = await tenant_manager.begin_transaction(tenant_id, timeout_seconds)
    return {
        "success": True,
        "transaction_id": transaction_id,
        "timeout_seconds": timeout_seconds,
        "message": "Transaction started. Pass this transaction_id to subsequent queries.",
    }


@mcp.tool
async def pg_commit_transaction(
    tenant_id: str,
    transaction_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Commit a multi-statement transaction.

    Commits all changes made within the transaction and returns the pinned
    connection to the pool. After this call, the ``transaction_id`` is invalid
    and cannot be reused.

    Args:
        tenant_id (str): Tenant identifier (must match the transaction's tenant).
        transaction_id (str): The transaction token from pg_begin_transaction.
        ctx (Optional[Context], default=None): MCP context for logging.

    Returns:
        Dict with:
        - success (bool): Whether the commit succeeded.
        - message (str): Confirmation message.
    """
    if ctx:
        await ctx.info(f"Committing transaction {transaction_id} for tenant: {tenant_id}")

    # Verify tenant ownership before committing
    await tenant_manager.get_transaction_connection(transaction_id, tenant_id)
    await tenant_manager.end_transaction(transaction_id, action="commit")
    return {"success": True, "message": "Transaction committed successfully."}


@mcp.tool
async def pg_rollback_transaction(
    tenant_id: str,
    transaction_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Roll back a multi-statement transaction.

    Discards all changes made within the transaction and returns the pinned
    connection to the pool. After this call, the ``transaction_id`` is invalid
    and cannot be reused.

    Args:
        tenant_id (str): Tenant identifier (must match the transaction's tenant).
        transaction_id (str): The transaction token from pg_begin_transaction.
        ctx (Optional[Context], default=None): MCP context for logging.

    Returns:
        Dict with:
        - success (bool): Whether the rollback succeeded.
        - message (str): Confirmation message.
    """
    if ctx:
        await ctx.info(f"Rolling back transaction {transaction_id} for tenant: {tenant_id}")

    # Verify tenant ownership before rolling back
    await tenant_manager.get_transaction_connection(transaction_id, tenant_id)
    await tenant_manager.end_transaction(transaction_id, action="rollback")
    return {"success": True, "message": "Transaction rolled back successfully."}


@mcp.tool
async def pg_register_tenant(
    tenant_id: str,
    host: str,
    database: str,
    user: str,
    password: str,
    port: int = 5432,
    min_pool_size: int = 2,
    max_pool_size: int = 10,
    ssl: bool = False,
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant's PostgreSQL connection configuration at runtime.

    Use this tool to dynamically add a new tenant to the server so that subsequent
    calls to pg_execute_query, pg_list_tables, and pg_describe_table can target
    the new tenant's database. The configuration is stored in the tenant manager
    and a connection pool is created with the specified sizing parameters.

    If a tenant with the same ``tenant_id`` already exists, its configuration will
    be replaced with the new values. The caller is responsible for ensuring that
    connection credentials are correct; invalid credentials will cause connection
    errors on first use rather than at registration time.

    Note: Connection credentials (host, user, password) are held in memory for
    the lifetime of the server process. Treat tenant registration requests with
    the same security posture as any credential-handling operation.

    Args:
        tenant_id (str): Unique identifier for this tenant. Used in all other tools
            to route operations to the correct database. Must be unique across all
            registered tenants.
        host (str): PostgreSQL server hostname or IP address
            (e.g. "db.example.com" or "10.0.1.5").
        database (str): Name of the PostgreSQL database to connect to.
        user (str): PostgreSQL username for authentication.
        password (str): PostgreSQL password for authentication.
        port (int, default=5432): TCP port the PostgreSQL server is listening on.
        min_pool_size (int, default=2): Minimum number of connections to keep open
            in the connection pool. A higher value reduces latency for bursty
            workloads at the cost of idle connections.
        max_pool_size (int, default=10): Maximum number of connections the pool is
            allowed to open. Requests beyond this limit will wait for a connection
            to become available.
        ssl (bool, default=False): Whether to require SSL/TLS for the connection.
            Set to True when connecting over untrusted networks or when the server
            mandates encrypted connections.
        max_concurrent_requests (int, default=100): Maximum number of concurrent
            in-flight requests allowed for this tenant. Acts as a per-tenant rate
            limiter to prevent any single tenant from monopolising server resources.
        ctx (Optional[Context], default=None): MCP context for logging. Automatically
            provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the tenant was registered successfully.
        - message (str): Confirmation message including the tenant_id.
    """
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        from mcp_servers.postgres.tenant_manager import PostgresTenantConfig
    except ImportError:
        from .tenant_manager import PostgresTenantConfig

    config = PostgresTenantConfig(
        tenant_id=tenant_id,
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        min_pool_size=min_pool_size,
        max_pool_size=max_pool_size,
        ssl=ssl,
        max_concurrent_requests=max_concurrent_requests,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("postgres://{tenant_id}/tables")
async def get_tables_resource(tenant_id: str) -> str:
    """Get list of tables for a tenant as a resource."""
    result = await pg_list_tables(tenant_id)
    return json.dumps(result, indent=2)


@mcp.resource("postgres://info")
def postgres_info() -> str:
    """Get information about the Postgres MCP server."""
    return "PostgreSQL MCP Server - Multi-tenant database operations"


def main():
    """Run the Postgres server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8001"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    # This allows each request to work independently without session management
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    # JSON format returns plain JSON instead of SSE format
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()

