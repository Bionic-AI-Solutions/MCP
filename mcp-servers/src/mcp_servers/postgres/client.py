"""
PostgreSQL MCP Client

Example client for interacting with the Postgres MCP server.
"""

import asyncio
from fastmcp import Client


async def main():
    """Example usage of the Postgres MCP client."""
    # Connect to the postgres server
    async with Client("src/mcp_servers/postgres/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")
        
        # Register a tenant (if not already configured via env vars)
        tenant_id = "1"
        print(f"\n=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "pg_register_tenant",
            {
                "tenant_id": tenant_id,
                "host": "localhost",
                "port": 5432,
                "database": "mydb",
                "user": "postgres",
                "password": "password",
            },
        )
        print(f"Result: {result.content[0].text}")
        
        # List tables
        print(f"\n=== Listing tables for tenant: {tenant_id} ===")
        result = await client.call_tool("pg_list_tables", {"tenant_id": tenant_id})
        print(f"Tables: {result.content[0].text}")
        
        # Describe a table (if exists)
        print(f"\n=== Describing table 'users' ===")
        result = await client.call_tool(
            "pg_describe_table",
            {"tenant_id": tenant_id, "table_name": "users"},
        )
        print(f"Table info: {result.content[0].text}")
        
        # Execute a query
        print(f"\n=== Executing query ===")
        result = await client.call_tool(
            "pg_execute_query",
            {
                "tenant_id": tenant_id,
                "query": "SELECT version();",
            },
        )
        print(f"Query result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())

