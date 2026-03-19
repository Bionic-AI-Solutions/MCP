---
name: calc
description: Perform arithmetic calculations using the Calculator MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<operation> <args>"
---

# Calculator MCP Server

Server: `calculator` at `calculator/mcp` (stateful transport)
No tenant_id required. No session management needed.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `calc_add` | `a: float, b: float` | Add two numbers |
| `calc_subtract` | `a: float, b: float` | Subtract b from a |
| `calc_multiply` | `a: float, b: float` | Multiply two numbers |
| `calc_divide` | `a: float, b: float` | Divide a by b |
| `calc_power` | `base: float, exponent: float` | Raise base to power |
| `calc_sqrt` | `a: float` | Square root |
| `calc_modulo` | `a: float, b: float` | Remainder of a / b |

## Usage Examples

Add two numbers:
```bash
~/.claude/bin/mcp-rpc call calculator calc_add '{"a": 10, "b": 25}'
```

Raise 2 to the 8th power:
```bash
~/.claude/bin/mcp-rpc call calculator calc_power '{"base": 2, "exponent": 8}'
```

Square root of 144:
```bash
~/.claude/bin/mcp-rpc call calculator calc_sqrt '{"a": 144}'
```

## Notes

- This server has no tenants -- all tools are called without a `tenant_id`.
- Division by zero returns an error.
- All values are IEEE 754 floats; very large or small results may lose precision.
