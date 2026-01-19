"""
Redis MCP Server (Multi-tenant)

A FastMCP server providing Redis operations with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

try:
    from mcp_servers.redis.tenant_manager import RedisTenantManager
except ImportError:
    from .tenant_manager import RedisTenantManager

# Initialize tenant manager
tenant_manager = RedisTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all Redis connections
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Redis Server", lifespan=lifespan)


# ============================================================================
# Request/Response Models
# ============================================================================

class KeyOperationRequest(BaseModel):
    """Request model for key operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    key: str = Field(..., description="Redis key")


class SetOperationRequest(BaseModel):
    """Request model for set operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    key: str = Field(..., description="Redis key")
    value: str = Field(..., description="Value to set")
    ttl: Optional[int] = Field(default=None, description="Time to live in seconds")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def redis_execute_command(
    tenant_id: str,
    command: str,
    args: Optional[List[str]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute a Redis command and return results.
    
    Args:
        tenant_id: Tenant identifier
        command: Redis command (e.g., 'GET', 'SET', 'DEL', 'KEYS', 'INFO')
        args: Command arguments (optional)
    """
    if ctx:
        await ctx.info(f"Executing Redis command '{command}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            if args:
                result = await client.execute_command(command, *args)
            else:
                result = await client.execute_command(command)
            
            # Convert result to JSON-serializable format
            if isinstance(result, bytes):
                result = result.decode('utf-8')
            elif isinstance(result, (list, tuple)):
                result = [item.decode('utf-8') if isinstance(item, bytes) else item for item in result]
            
            return {
                "success": True,
                "result": result,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_get(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a value from Redis by key."""
    if ctx:
        await ctx.info(f"Getting key '{key}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            value = await client.get(key)
        
        return {
            "success": True,
            "key": key,
            "value": value,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_set(
    tenant_id: str,
    key: str,
    value: str,
    ttl: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set a value in Redis with optional TTL."""
    if ctx:
        await ctx.info(f"Setting key '{key}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            if ttl:
                await client.setex(key, ttl, value)
            else:
                await client.set(key, value)
        
        return {
            "success": True,
            "message": f"Key '{key}' set successfully",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_delete(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete a key from Redis."""
    if ctx:
        await ctx.info(f"Deleting key '{key}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            deleted = await client.delete(key)
        
        return {
            "success": True,
            "deleted": bool(deleted),
            "message": f"Key '{key}' {'deleted' if deleted else 'not found'}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_keys(
    tenant_id: str,
    pattern: str = "*",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List keys matching a pattern."""
    if ctx:
        await ctx.info(f"Listing keys matching '{pattern}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            keys = await client.keys(pattern)
        
        return {
            "success": True,
            "pattern": pattern,
            "keys": keys,
            "count": len(keys),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_exists(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Check if a key exists in Redis."""
    if ctx:
        await ctx.info(f"Checking if key '{key}' exists for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            exists = await client.exists(key)
        
        return {
            "success": True,
            "key": key,
            "exists": bool(exists),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_ttl(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the time to live (TTL) of a key in seconds."""
    if ctx:
        await ctx.info(f"Getting TTL for key '{key}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            ttl = await client.ttl(key)
        
        return {
            "success": True,
            "key": key,
            "ttl": ttl,
            "expires_in_seconds": ttl if ttl > 0 else None,
            "persistent": ttl == -1,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_info(
    tenant_id: str,
    section: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get Redis server information."""
    if ctx:
        await ctx.info(f"Getting Redis info for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            info = await client.info(section)
        
        return {
            "success": True,
            "section": section or "all",
            "info": info,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_ping(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Ping Redis server to test connection."""
    if ctx:
        await ctx.info(f"Pinging Redis for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]
        
        async with semaphore:
            result = await client.ping()
        
        return {
            "success": True,
            "pong": result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_register_tenant(
    tenant_id: str,
    host: str,
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    ssl: bool = False,
    decode_responses: bool = True,
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration with concurrency control.
    
    Args:
        tenant_id: Unique identifier for this tenant
        host: Redis host
        port: Redis port (default: 6379)
        password: Redis password (optional)
        db: Redis database number (0-15, default: 0)
        ssl: Use SSL/TLS (default: False)
        decode_responses: Decode responses as strings (default: True)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 100)
    """
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        from mcp_servers.redis.tenant_manager import RedisTenantConfig
    except ImportError:
        from .tenant_manager import RedisTenantConfig

    config = RedisTenantConfig(
        tenant_id=tenant_id,
        host=host,
        port=port,
        password=password,
        db=db,
        ssl=ssl,
        decode_responses=decode_responses,
        max_concurrent_requests=max_concurrent_requests,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("redis://{tenant_id}/keys")
async def get_keys_resource(tenant_id: str) -> str:
    """Get list of keys for a tenant as a resource."""
    result = await redis_keys(tenant_id)
    return json.dumps(result, indent=2)


@mcp.resource("redis://info")
def redis_info_resource() -> str:
    """Get information about the Redis MCP server."""
    return "Redis MCP Server - Multi-tenant Redis operations"


def main():
    """Run the Redis server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8010"))
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
