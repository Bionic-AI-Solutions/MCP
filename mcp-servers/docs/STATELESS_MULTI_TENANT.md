# Stateless HTTP Mode in Multi-Tenant Gateway

## Overview

Stateless HTTP mode (`stateless_http=True`) is **perfectly fine** for multi-tenant deployments, including when the calculator server is part of a multi-tenant MCP gateway. Here's why:

## How Stateless Mode Works

### What "Stateless" Means

- **Stateless mode**: Each request creates a fresh transport context
- **No server-side session storage**: No in-memory session state maintained
- **Session IDs still available**: Can be extracted from HTTP headers (`mcp-session-id` or `Mcp-Session-Id`)

### Session ID Handling

Even in stateless mode, FastMCP can extract session IDs from headers:

```python
# FastMCP automatically extracts session ID from headers
# Priority order:
# 1. Session attributes (if available)
# 2. HTTP header: "mcp-session-id" or "Mcp-Session-Id"
# 3. Generate new UUID if not found
```

## Multi-Tenant Gateway Architecture

### Recommended Pattern

```
┌─────────────┐
│   Gateway   │  ← Manages sessions, tenant identification
│  (Kong/     │     Passes context via headers
│   Nginx)    │
└──────┬──────┘
       │ Headers: Mcp-Session-Id, X-Tenant-Id, X-User-Id
       │
       ▼
┌─────────────┐
│  Calculator │  ← Stateless backend
│   Server    │     Reads tenant context from headers
└─────────────┘
```

### Gateway Responsibilities

1. **Session Management**: Gateway maintains session state (if needed)
2. **Tenant Identification**: Gateway identifies tenant/user from auth token
3. **Header Injection**: Gateway passes context via HTTP headers:
   - `Mcp-Session-Id`: For session tracking (optional)
   - `X-Tenant-Id`: For tenant identification (recommended)
   - `X-User-Id`: For user identification (optional)
   - `Authorization`: For authentication

### Backend Server Responsibilities

1. **Read Headers**: Extract tenant/user context from headers
2. **Process Request**: Handle request with tenant context
3. **Return Response**: No session state needed

## Calculator Server - Why Stateless is Perfect

The calculator server is **inherently stateless**:
- ✅ No per-user state needed
- ✅ No per-tenant configuration
- ✅ Pure function operations (add, subtract, etc.)
- ✅ No database connections
- ✅ No shared state between requests

**Conclusion**: Stateless mode is ideal for calculator!

## Adding Tenant Identification (If Needed)

If you need tenant identification in the calculator server:

```python
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.context import Context

mcp = FastMCP("Calculator Server")

@mcp.tool
async def add(a: float, b: float, ctx: Context) -> float:
    """Add two numbers together."""
    # Get tenant ID from headers (set by gateway)
    headers = get_http_headers()
    tenant_id = headers.get("x-tenant-id") or headers.get("x-user-id")
    
    # Optional: Log with tenant context
    if tenant_id:
        await ctx.info(f"Processing request for tenant: {tenant_id}")
    
    # Get session ID (available even in stateless mode)
    session_id = ctx.session_id
    
    # Process request (stateless operation)
    result = a + b
    
    return result
```

## Gateway Configuration Example

### Kong Plugin for Tenant Identification

```yaml
apiVersion: configuration.konghq.com/v1
kind: KongPlugin
metadata:
  name: tenant-identification
  namespace: mcp
config:
  add:
    headers:
      - "X-Tenant-Id:$(headers['X-User-Id'])"  # Extract from auth token
      - "Mcp-Session-Id:$(headers['Mcp-Session-Id'])"  # Pass through
plugin: request-transformer
```

### Nginx Configuration

```nginx
location /calculator/mcp {
    # Extract tenant from auth token and pass as header
    set $tenant_id $http_x_user_id;
    proxy_set_header X-Tenant-Id $tenant_id;
    proxy_set_header Mcp-Session-Id $mcp_session_id;
    
    proxy_pass http://mcp-calculator-server:8000/mcp;
}
```

## Benefits of Stateless Mode

1. **Horizontal Scaling**: Any instance can handle any request
2. **No Session Affinity**: No need for sticky sessions
3. **Load Balancer Friendly**: Works with any load balancer
4. **Simpler Deployment**: No shared session storage needed
5. **Better Performance**: No session lookup overhead

## When to Use Stateful Mode

Use stateful mode (default) only if:
- You need server-side state between requests
- You're using features like elicitation or sampling
- You have a single-instance deployment
- You need session-based features

## Summary

✅ **Stateless mode is safe for multi-tenant calculator server**
✅ **Session IDs can still be passed via headers**
✅ **Gateway manages sessions and tenant identification**
✅ **Backend reads tenant context from headers**
✅ **Perfect for horizontal scaling**

The calculator server doesn't need server-side sessions - it's a pure stateless service. The gateway can manage all session and tenant context, passing it via headers to the backend.

















