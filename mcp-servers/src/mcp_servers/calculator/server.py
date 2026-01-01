"""
Calculator MCP Server

A simple FastMCP server providing basic arithmetic operations.
"""

from fastmcp import FastMCP

# Create server
mcp = FastMCP("Calculator Server")


@mcp.tool
def add(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


@mcp.tool
def subtract(a: float, b: float) -> float:
    """Subtract b from a."""
    return a - b


@mcp.tool
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@mcp.tool
def divide(a: float, b: float) -> float:
    """Divide a by b. Raises error if b is zero."""
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return a / b


@mcp.tool
def power(base: float, exponent: float) -> float:
    """Raise base to the power of exponent."""
    return base ** exponent


@mcp.tool
def sqrt(value: float) -> float:
    """Calculate the square root of a value."""
    if value < 0:
        raise ValueError("Square root of negative number is not allowed")
    return value ** 0.5


@mcp.tool
def modulo(a: float, b: float) -> float:
    """Calculate a modulo b (remainder after division)."""
    if b == 0:
        raise ValueError("Modulo by zero is not allowed")
    return a % b


@mcp.resource("calculator://info")
def calculator_info() -> str:
    """Get information about the calculator server."""
    return "Calculator MCP Server - Provides basic arithmetic operations"


@mcp.prompt("calculate")
def calculate_prompt(operation: str, numbers: str) -> str:
    """Generate a prompt for performing a calculation."""
    return f"Please calculate {operation} for the numbers: {numbers}"


def main():
    """Run the calculator server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8000"))
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

