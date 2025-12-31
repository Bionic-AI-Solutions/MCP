"""
Calculator MCP Client

Example client for interacting with the Calculator MCP server.
"""

import asyncio
from fastmcp import Client


async def main():
    """Example usage of the Calculator MCP client."""
    # Connect to the calculator server
    async with Client("src/mcp_servers/calculator/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")
        
        # Perform calculations
        print("\n=== Calculator Operations ===")
        
        # Addition
        result = await client.call_tool("add", {"a": 10, "b": 5})
        print(f"10 + 5 = {result.content[0].text}")
        
        # Subtraction
        result = await client.call_tool("subtract", {"a": 10, "b": 3})
        print(f"10 - 3 = {result.content[0].text}")
        
        # Multiplication
        result = await client.call_tool("multiply", {"a": 6, "b": 7})
        print(f"6 * 7 = {result.content[0].text}")
        
        # Division
        result = await client.call_tool("divide", {"a": 20, "b": 4})
        print(f"20 / 4 = {result.content[0].text}")
        
        # Power
        result = await client.call_tool("power", {"base": 2, "exponent": 8})
        print(f"2^8 = {result.content[0].text}")
        
        # Square root
        result = await client.call_tool("sqrt", {"value": 64})
        print(f"√64 = {result.content[0].text}")
        
        # Modulo
        result = await client.call_tool("modulo", {"a": 17, "b": 5})
        print(f"17 % 5 = {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())

