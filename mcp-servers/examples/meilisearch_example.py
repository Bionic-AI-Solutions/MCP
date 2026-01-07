"""
Example: Using the meilisearch MCP Server

This example demonstrates how to use the meilisearch MCP client with multi-tenant support.
"""

import asyncio
from fastmcp import Client


async def main():
    """Run meilisearch examples."""
    print("=== meilisearch MCP Server Example ===\n")
    
    # Connect to the server
    async with Client("src/mcp_servers/meilisearch/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}\n")
        
        tenant_id = "example-tenant"
        
        # Register tenant
        print(f"=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "register_tenant",
            {
                "tenant_id": tenant_id,
                # Add your tenant configuration parameters here
                # Example:
                # "api_key": "your_api_key_here",
                # "api_url": "https://api.example.com",
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # Use a tool
        print(f"=== Using example_tool for tenant: {tenant_id} ===")
        result = await client.call_tool(
            "example_tool",
            {
                "tenant_id": tenant_id,
                # Add your tool parameters here
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # Access a resource
        print(f"=== Accessing resource for tenant: {tenant_id} ===")
        resource = await client.read_resource(f"meilisearch://{tenant_id}/info")
        print(f"Resource: {resource.contents[0].text}\n")


if __name__ == "__main__":
    asyncio.run(main())

