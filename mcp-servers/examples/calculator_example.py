"""
Example: Using the Calculator MCP Server

This example demonstrates how to use the Calculator MCP client.
"""

import asyncio
from fastmcp import Client


async def main():
    """Run calculator examples."""
    print("=== Calculator MCP Server Example ===\n")
    
    # Connect to the calculator server
    async with Client("src/mcp_servers/calculator/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}\n")
        
        # Perform various calculations
        calculations = [
            ("add", {"a": 15, "b": 27}, "15 + 27"),
            ("subtract", {"a": 100, "b": 42}, "100 - 42"),
            ("multiply", {"a": 7, "b": 8}, "7 × 8"),
            ("divide", {"a": 144, "b": 12}, "144 ÷ 12"),
            ("power", {"base": 2, "exponent": 10}, "2^10"),
            ("sqrt", {"value": 256}, "√256"),
            ("modulo", {"a": 23, "b": 5}, "23 % 5"),
        ]
        
        for tool_name, args, description in calculations:
            result = await client.call_tool(tool_name, args)
            print(f"{description} = {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())

