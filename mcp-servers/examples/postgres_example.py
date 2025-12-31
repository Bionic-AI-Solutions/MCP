"""
Example: Using the Postgres MCP Server

This example demonstrates how to use the Postgres MCP client with multi-tenant support.

Before running, set environment variables:
    export POSTGRES_TENANT_1_HOST=localhost
    export POSTGRES_TENANT_1_PORT=5432
    export POSTGRES_TENANT_1_DB=mydb
    export POSTGRES_TENANT_1_USER=postgres
    export POSTGRES_TENANT_1_PASSWORD=password
"""

import asyncio
from fastmcp import Client


async def main():
    """Run postgres examples."""
    print("=== Postgres MCP Server Example ===\n")
    
    # Connect to the postgres server
    async with Client("src/mcp_servers/postgres/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}\n")
        
        tenant_id = "1"
        
        # Option 1: Register tenant programmatically (if not configured via env)
        print(f"=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "register_tenant",
            {
                "tenant_id": tenant_id,
                "host": "localhost",
                "port": 5432,
                "database": "mydb",
                "user": "postgres",
                "password": "password",
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # List tables
        print(f"=== Listing tables for tenant: {tenant_id} ===")
        result = await client.call_tool("list_tables", {"tenant_id": tenant_id})
        print(f"Tables: {result.content[0].text}\n")
        
        # Execute a query
        print("=== Executing query: SELECT version() ===")
        result = await client.call_tool(
            "execute_query",
            {
                "tenant_id": tenant_id,
                "query": "SELECT version();",
            },
        )
        print(f"Query result: {result.content[0].text}\n")
        
        # Describe a table (if exists)
        print("=== Describing table 'users' (if exists) ===")
        result = await client.call_tool(
            "describe_table",
            {"tenant_id": tenant_id, "table_name": "users"},
        )
        print(f"Table info: {result.content[0].text}\n")


if __name__ == "__main__":
    asyncio.run(main())

