# Calculator MCP Server - Usage Guide

## Overview

The Calculator MCP server provides basic arithmetic operations. It's a simple, stateless server that performs mathematical calculations.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "calculator-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/calculator/mcp",
      "description": "Calculator MCP Server - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-calculator-server

# Server will be available at http://localhost:8000
```

## Available Tools

The Calculator server provides the following arithmetic operations:

### 1. `calc_add` - Addition

Add two numbers together.

**Parameters:**
- `a` (float, required): First number
- `b` (float, required): Second number

**Example:**
```json
{
  "a": 10,
  "b": 5
}
```

**Response:**
```
15.0
```

### 2. `calc_subtract` - Subtraction

Subtract b from a.

**Parameters:**
- `a` (float, required): First number
- `b` (float, required): Second number

**Example:**
```json
{
  "a": 10,
  "b": 3
}
```

**Response:**
```
7.0
```

### 3. `calc_multiply` - Multiplication

Multiply two numbers.

**Parameters:**
- `a` (float, required): First number
- `b` (float, required): Second number

**Example:**
```json
{
  "a": 6,
  "b": 7
}
```

**Response:**
```
42.0
```

### 4. `calc_divide` - Division

Divide a by b. Raises error if b is zero.

**Parameters:**
- `a` (float, required): Dividend
- `b` (float, required): Divisor

**Example:**
```json
{
  "a": 20,
  "b": 4
}
```

**Response:**
```
5.0
```

### 5. `calc_power` - Exponentiation

Raise base to the power of exponent.

**Parameters:**
- `base` (float, required): Base number
- `exponent` (float, required): Exponent

**Example:**
```json
{
  "base": 2,
  "exponent": 8
}
```

**Response:**
```
256.0
```

### 6. `calc_sqrt` - Square Root

Calculate the square root of a value.

**Parameters:**
- `value` (float, required): Number to calculate square root of

**Example:**
```json
{
  "value": 64
}
```

**Response:**
```
8.0
```

### 7. `calc_modulo` - Modulo

Calculate a modulo b (remainder after division).

**Parameters:**
- `a` (float, required): Dividend
- `b` (float, required): Divisor

**Example:**
```json
{
  "a": 17,
  "b": 5
}
```

**Response:**
```
2.0
```

## Resources

Access server information as a resource:

- `calculator://info` - Get information about the calculator server

## Example Workflow

```python
# Add two numbers
result = calc_add(a=10, b=5)  # Returns 15.0

# Calculate power
result = calc_power(base=2, exponent=8)  # Returns 256.0

# Calculate square root
result = calc_sqrt(value=64)  # Returns 8.0
```

## Notes

- All operations return floating-point numbers
- Division by zero raises a `ValueError`
- Square root of negative numbers raises a `ValueError`
- Modulo by zero raises a `ValueError`
- The server is stateless and requires no configuration


