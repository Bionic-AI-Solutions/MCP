"""
Calculator MCP Server

A simple FastMCP server providing basic arithmetic operations.
"""

from fastmcp import FastMCP

# Create server
mcp = FastMCP("Calculator Server")


@mcp.tool
def calc_add(a: float, b: float) -> float:
    """Add two numbers together and return their sum.

    Performs standard floating-point addition of two numeric values. Both
    integers and floating-point numbers are accepted; integer inputs are
    automatically promoted to floats.

    Args:
        a: The first addend (float). The left-hand operand of the addition.
        b: The second addend (float). The right-hand operand of the addition.

    Returns:
        float: The arithmetic sum of a and b (i.e., a + b).

    Notes:
        Results are subject to standard IEEE 754 floating-point precision
        limitations. For example, 0.1 + 0.2 may not equal exactly 0.3.
    """
    return a + b


@mcp.tool
def calc_subtract(a: float, b: float) -> float:
    """Subtract one number from another and return the difference.

    Computes the result of subtracting b from a. The order of operands
    matters: calc_subtract(10, 3) returns 7, while calc_subtract(3, 10)
    returns -7.

    Args:
        a: The minuend (float). The number to subtract from.
        b: The subtrahend (float). The number to subtract.

    Returns:
        float: The arithmetic difference of a and b (i.e., a - b). The result
            may be negative if b is greater than a.

    Notes:
        Results are subject to standard IEEE 754 floating-point precision
        limitations.
    """
    return a - b


@mcp.tool
def calc_multiply(a: float, b: float) -> float:
    """Multiply two numbers together and return their product.

    Performs standard floating-point multiplication. Both integers and
    floating-point numbers are accepted. Multiplying by zero always returns
    zero; multiplying by one returns the other operand unchanged (identity).

    Args:
        a: The first factor (float). The left-hand operand of the
            multiplication.
        b: The second factor (float). The right-hand operand of the
            multiplication.

    Returns:
        float: The arithmetic product of a and b (i.e., a * b).

    Notes:
        Very large or very small results may lose precision due to IEEE 754
        floating-point representation. Multiplying extremely large numbers
        may produce float('inf').
    """
    return a * b


@mcp.tool
def calc_divide(a: float, b: float) -> float:
    """Divide one number by another and return the quotient.

    Performs standard floating-point division of a by b. Always returns a
    float result, even when both operands are whole numbers (e.g.,
    calc_divide(10, 2) returns 5.0, not 5).

    Args:
        a: The dividend (float). The number to be divided.
        b: The divisor (float). The number to divide by. Must not be zero.

    Returns:
        float: The arithmetic quotient of a and b (i.e., a / b).

    Raises:
        ValueError: If b is zero, since division by zero is mathematically
            undefined.

    Notes:
        This performs true division (not floor/integer division). For the
        remainder after division, use calc_modulo instead.
    """
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return a / b


@mcp.tool
def calc_power(base: float, exponent: float) -> float:
    """Raise a base number to the power of an exponent.

    Computes base raised to the power of exponent using Python's built-in
    exponentiation operator. Supports integer and fractional exponents.
    For example, calc_power(2, 3) returns 8.0, and calc_power(9, 0.5)
    returns 3.0 (equivalent to the square root of 9).

    Args:
        base: The base number (float). The number to be raised to a power.
        exponent: The exponent (float). The power to raise the base to. Can
            be negative (returns the reciprocal), zero (returns 1.0), positive,
            or fractional.

    Returns:
        float: The result of base ** exponent.

    Notes:
        Raising a negative base to a fractional exponent will produce a
        complex number, which Python may raise a ValueError for. Use
        calc_sqrt for simple square root operations on non-negative values.
        Very large exponents may result in float('inf') due to overflow.
    """
    return base ** exponent


@mcp.tool
def calc_sqrt(value: float) -> float:
    """Calculate the square root of a non-negative number.

    Computes the principal (non-negative) square root of the given value.
    This is equivalent to raising the value to the power of 0.5, but
    includes explicit validation that the input is non-negative.

    Args:
        value: The number to compute the square root of (float). Must be
            greater than or equal to zero.

    Returns:
        float: The principal square root of value (i.e., value ** 0.5). The
            result is always non-negative.

    Raises:
        ValueError: If value is negative, since the square root of a negative
            number is not a real number.

    Notes:
        For computing arbitrary roots (e.g., cube roots), use calc_power with
        a fractional exponent instead (e.g., calc_power(27, 1/3) for the cube
        root of 27).
    """
    if value < 0:
        raise ValueError("Square root of negative number is not allowed")
    return value ** 0.5


@mcp.tool
def calc_modulo(a: float, b: float) -> float:
    """Calculate the remainder of dividing one number by another (modulo operation).

    Computes a modulo b, which is the remainder left over after dividing a by
    b. This uses Python's modulo operator, which always returns a result with
    the same sign as the divisor b. For example, calc_modulo(7, 3) returns 1.0,
    and calc_modulo(-7, 3) returns 2.0 (Python convention).

    Args:
        a: The dividend (float). The number to be divided.
        b: The divisor (float). The number to divide by to find the remainder.
            Must not be zero.

    Returns:
        float: The remainder of a divided by b (i.e., a % b). The sign of the
            result matches the sign of b (Python's modulo convention).

    Raises:
        ValueError: If b is zero, since modulo by zero is mathematically
            undefined.

    Notes:
        Python's modulo operation differs from some other languages (e.g., C or
        Java) in how it handles negative operands. In Python, the result always
        has the same sign as the divisor. This operation also works with
        floating-point numbers (e.g., calc_modulo(5.5, 2.0) returns 1.5).
    """
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
