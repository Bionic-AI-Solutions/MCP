# Cursor MCP Client Troubleshooting Guide

## Calculator MCP Server Status

### Server Verification ✅

The calculator server is **fully operational** and responding correctly:

- **Endpoint**: `https://mcp.baisoln.com/calculator/mcp`
- **Transport**: HTTP (stateless mode)
- **Tools Available**: 7 tools (add, subtract, multiply, divide, power, sqrt, modulo)
- **Protocol**: MCP 2024-11-05
- **Response Format**: JSON (not SSE)

### Test Results

```bash
# Direct endpoint test
curl -k -X POST https://mcp.baisoln.com/calculator/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'

# Returns: 7 tools correctly formatted
```

## Cursor Configuration

Your `mcp.json` is correctly configured:

```json
{
  "calculator": {
    "url": "https://mcp.baisoln.com/calculator/mcp",
    "transport": "http",
    "description": "Calculator MCP Server - Remote access via Kong proxy"
  }
}
```

## Troubleshooting Steps

### 1. Restart Cursor

**Most Common Fix**: Cursor caches MCP server connections. A full restart is required:

1. **Completely quit Cursor** (not just close the window)
   - On macOS: `Cmd + Q`
   - On Linux/Windows: Close all Cursor windows and ensure the process is terminated

2. **Restart Cursor**

3. **Wait for MCP servers to initialize** (check the status in Cursor's MCP panel)

### 2. Check Cursor's MCP Logs

Cursor provides detailed logs for MCP server connections:

1. Open **View > Output**
2. Select **"MCP"** from the dropdown
3. Look for errors related to the calculator server
4. Common issues to look for:
   - Connection timeouts
   - SSL certificate errors
   - JSON parsing errors
   - Protocol version mismatches

### 3. Verify Network Connectivity

Ensure Cursor can reach the server:

```bash
# Test from your machine
curl -k https://mcp.baisoln.com/calculator/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

### 4. Check Cursor's MCP Server Status Panel

1. Open Cursor's settings
2. Navigate to **MCP Servers** section
3. Check the calculator server status:
   - **Green dot**: Connected and working
   - **Yellow dot**: Loading or connection issue
   - **Red dot**: Connection failed

### 5. Clear Cursor's MCP Cache (if available)

Some Cursor versions cache MCP server state:

1. Close Cursor completely
2. Clear Cursor's cache directory (location varies by OS)
3. Restart Cursor

### 6. Verify SSL Certificate

If you see SSL errors in the logs:

- The server uses a self-signed certificate
- Cursor should accept it, but you may need to:
  - Add an exception for `mcp.baisoln.com`
  - Or configure Cursor to accept self-signed certificates

### 7. Test with a Different MCP Client

To verify the server is working, test with a Python client:

```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

async def test():
    transport = StreamableHttpTransport(
        url="https://mcp.baisoln.com/calculator/mcp"
    )
    async with Client(transport) as client:
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}")

# Run: python -c "import asyncio; asyncio.run(test())"
```

## Common Issues and Solutions

### Issue: "Loading tools" status persists

**Cause**: Cursor is unable to fetch the tools list

**Solutions**:
1. Check Cursor's MCP logs for errors
2. Verify the server is accessible from your network
3. Try restarting Cursor
4. Check if firewall/proxy is blocking the connection

### Issue: Tools appear but don't work

**Cause**: Tools are listed but calls fail

**Solutions**:
1. Check Cursor's MCP logs for tool call errors
2. Verify the server is responding to tool calls
3. Test a tool call directly:
   ```bash
   curl -k -X POST https://mcp.baisoln.com/calculator/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"add","arguments":{"a":5,"b":3}},"id":1}'
   ```

### Issue: Connection timeout

**Cause**: Network or firewall blocking

**Solutions**:
1. Verify network connectivity
2. Check firewall rules
3. Verify Kong ingress is accessible
4. Check if VPN is interfering

## Server-Side Verification

To verify the server is working correctly:

```bash
# 1. Check pod status
kubectl get pods -n mcp -l app=mcp-calculator-server

# 2. Check pod logs
kubectl logs -n mcp -l app=mcp-calculator-server --tail=50

# 3. Test endpoint directly
curl -k https://mcp.baisoln.com/calculator/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'

# 4. Check Kong ingress
kubectl get ingress -n mcp mcp-calculator-ingress
```

## Next Steps

If the server is working (verified by curl tests) but Cursor still shows "Loading tools":

1. **Restart Cursor completely** (most common fix)
2. **Check Cursor's MCP logs** for specific errors
3. **Verify network connectivity** from your machine
4. **Try a different MCP client** to verify server functionality
5. **Check Cursor version** - ensure you're using a recent version that supports HTTP transport

## Server Configuration Summary

- **Transport**: HTTP (stateless mode)
- **Response Format**: JSON (not SSE)
- **Protocol**: MCP 2024-11-05
- **Endpoint**: `/calculator/mcp`
- **Discovery Endpoint**: `/calculator/` (also works)
- **Tools**: 7 arithmetic operations
- **Status**: ✅ Fully operational

The server is correctly configured and responding. If Cursor still shows "Loading tools", the issue is likely with Cursor's connection or caching. A full restart usually resolves this.
















