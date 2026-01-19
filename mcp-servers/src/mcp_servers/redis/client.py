"""
Redis MCP Client

Example client for interacting with the Redis MCP server.
"""

import asyncio
from fastmcp import Client


async def main():
    """Example usage of the Redis MCP client."""
    # Connect to the redis server
    async with Client("src/mcp_servers/redis/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")
        
        # Register a tenant (if not already configured via env vars)
        tenant_id = "1"
        print(f"\n=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "redis_register_tenant",
            {
                "tenant_id": tenant_id,
                "host": "localhost",
                "port": 6379,
                "db": 0,
            },
        )
        print(f"Result: {result.content[0].text}")
        
        # Ping Redis
        print(f"\n=== Pinging Redis for tenant: {tenant_id} ===")
        result = await client.call_tool("redis_ping", {"tenant_id": tenant_id})
        print(f"Ping result: {result.content[0].text}")
        
        # Set a key
        print(f"\n=== Setting key 'test:key' ===")
        result = await client.call_tool(
            "redis_set",
            {
                "tenant_id": tenant_id,
                "key": "test:key",
                "value": "Hello, Redis!",
                "ttl": 3600,
            },
        )
        print(f"Set result: {result.content[0].text}")
        
        # Get a key
        print(f"\n=== Getting key 'test:key' ===")
        result = await client.call_tool(
            "redis_get",
            {"tenant_id": tenant_id, "key": "test:key"},
        )
        print(f"Get result: {result.content[0].text}")
        
        # List keys
        print(f"\n=== Listing keys matching 'test:*' ===")
        result = await client.call_tool(
            "redis_keys",
            {"tenant_id": tenant_id, "pattern": "test:*"},
        )
        print(f"Keys result: {result.content[0].text}")
        
        # Get Redis info
        print(f"\n=== Getting Redis info ===")
        result = await client.call_tool(
            "redis_info",
            {"tenant_id": tenant_id, "section": "server"},
        )
        print(f"Info result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
