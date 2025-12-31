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
async def execute_query(
    tenant_id: str,
    query: str,
    params: Optional[List[Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a SQL query and return results."""
    if ctx:
        await ctx.info(f"Executing query for tenant: {tenant_id}")

    async with tenant_manager.get_connection(tenant_id) as conn:
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
async def list_tables(
    tenant_id: str,
    schema: str = "public",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all tables in a schema."""
    if ctx:
        await ctx.info(f"Listing tables for tenant: {tenant_id}, schema: {schema}")

    query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = %s
        ORDER BY table_name
    """

    async with tenant_manager.get_connection(tenant_id) as conn:
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
async def describe_table(
    tenant_id: str,
    table_name: str,
    schema: str = "public",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a table."""
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

    async with tenant_manager.get_connection(tenant_id) as conn:
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


@mcp.tool
async def register_tenant(
    tenant_id: str,
    host: str,
    database: str,
    user: str,
    password: str,
    port: int = 5432,
    min_pool_size: int = 2,
    max_pool_size: int = 10,
    ssl: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration."""
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
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("postgres://{tenant_id}/tables")
async def get_tables_resource(tenant_id: str) -> str:
    """Get list of tables for a tenant as a resource."""
    result = await list_tables(tenant_id)
    return json.dumps(result, indent=2)


@mcp.resource("postgres://info")
def postgres_info() -> str:
    """Get information about the Postgres MCP server."""
    return "PostgreSQL MCP Server - Multi-tenant database operations"


def main():
    """Run the Postgres server."""
    mcp.run()


if __name__ == "__main__":
    main()

