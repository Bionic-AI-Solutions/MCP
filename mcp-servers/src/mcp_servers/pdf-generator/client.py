"""
Example: Using the pdf-generator MCP Server

This example demonstrates how to use the pdf-generator MCP client with multi-tenant support.

Before running, set environment variables:
    export pdf-generator_TENANT_1_API_KEY=your_api_key
    export pdf-generator_TENANT_1_API_URL=https://api.example.com
"""

import asyncio
from fastmcp import Client


async def main():
    """Run pdf-generator examples."""
    print("=== pdf-generator MCP Server Example ===\n")
    
    # Connect to the server
    async with Client("src/mcp_servers/pdf-generator/server.py") as client:
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
                # Add your tenant configuration parameters here
                # "api_key": "your_api_key",
                # "api_url": "https://api.example.com",
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # Example: Call a tool
        print(f"=== Calling example_tool for tenant: {tenant_id} ===")
        result = await client.call_tool(
            "example_tool",
            {
                "tenant_id": tenant_id,
                # Add your tool parameters here
            },
        )
        print(f"Result: {result.content[0].text}\n")


if __name__ == "__main__":
    asyncio.run(main())

