"""
Langfuse MCP Server (Multi-tenant)

A FastMCP server providing Langfuse observability and tracing operations with multi-tenant support.
Each tenant uses their own Langfuse API keys.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.langfuse.tenant_manager import LangfuseTenantManager
except ImportError:
    from .tenant_manager import LangfuseTenantManager

# Initialize tenant manager
tenant_manager = LangfuseTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all connections and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Langfuse Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "langfuse-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def lf_register_tenant(
    tenant_id: str,
    secret_key: str,
    public_key: str,
    base_url: str = "https://langfuse.bionicaisolutions.com",
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new Langfuse tenant configuration with concurrency control.
    
    Args:
        tenant_id: Unique identifier for this tenant
        secret_key: Langfuse secret key (sk-lf-...)
        public_key: Langfuse public key (pk-lf-...)
        base_url: Langfuse base URL (default: https://langfuse.bionicaisolutions.com)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 100)
    """
    if ctx:
        await ctx.info(f"Registering Langfuse tenant: {tenant_id}")

    try:
        from mcp_servers.langfuse.tenant_manager import LangfuseTenantConfig

        config = LangfuseTenantConfig(
            tenant_id=tenant_id,
            secret_key=secret_key,
            public_key=public_key,
            base_url=base_url,
            max_concurrent_requests=max_concurrent_requests,
        )

        await tenant_manager.register_tenant(config)
        return {
            "success": True,
            "message": f"Tenant '{tenant_id}' registered successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_trace(
    tenant_id: str,
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new trace in Langfuse.
    
    Args:
        tenant_id: Tenant identifier
        name: Name of the trace
        user_id: Optional user ID
        session_id: Optional session ID
        metadata: Optional metadata dictionary
        tags: Optional list of tags
    """
    if ctx:
        await ctx.info(f"Creating trace '{name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            tags=tags,
        )
        return {
            "success": True,
            "trace": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_span(
    tenant_id: str,
    trace_id: str,
    name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a span within a trace.
    
    Args:
        tenant_id: Tenant identifier
        trace_id: Trace ID to attach span to
        name: Name of the span
        start_time: Optional start time (ISO format)
        end_time: Optional end time (ISO format)
        metadata: Optional metadata dictionary
    """
    if ctx:
        await ctx.info(f"Creating span '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.span(
            trace_id=trace_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            metadata=metadata,
        )
        return {
            "success": True,
            "span": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_generation(
    tenant_id: str,
    trace_id: str,
    name: str,
    model: Optional[str] = None,
    model_parameters: Optional[Dict[str, Any]] = None,
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a generation (LLM call) observation.
    
    Args:
        tenant_id: Tenant identifier
        trace_id: Trace ID to attach generation to
        name: Name of the generation
        model: Optional model name
        model_parameters: Optional model parameters dictionary
        input: Optional input data
        output: Optional output data
        metadata: Optional metadata dictionary
    """
    if ctx:
        await ctx.info(f"Creating generation '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.generation(
            trace_id=trace_id,
            name=name,
            model=model,
            model_parameters=model_parameters,
            input=input,
            output=output,
            metadata=metadata,
        )
        return {
            "success": True,
            "generation": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_event(
    tenant_id: str,
    trace_id: str,
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create an event observation.
    
    Args:
        tenant_id: Tenant identifier
        trace_id: Trace ID to attach event to
        name: Name of the event
        metadata: Optional metadata dictionary
    """
    if ctx:
        await ctx.info(f"Creating event '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.event(
            trace_id=trace_id,
            name=name,
            metadata=metadata,
        )
        return {
            "success": True,
            "event": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_score(
    tenant_id: str,
    name: str,
    value: float,
    trace_id: Optional[str] = None,
    observation_id: Optional[str] = None,
    comment: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a score for a trace or observation.
    
    Args:
        tenant_id: Tenant identifier
        name: Name of the score
        value: Score value (float)
        trace_id: Optional trace ID
        observation_id: Optional observation ID
        comment: Optional comment
    """
    if ctx:
        await ctx.info(f"Creating score '{name}' with value {value}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            observation_id=observation_id,
            comment=comment,
        )
        return {
            "success": True,
            "score": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_get_trace(
    tenant_id: str,
    trace_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a trace by ID.
    
    Args:
        tenant_id: Tenant identifier
        trace_id: Trace ID to retrieve
    """
    if ctx:
        await ctx.info(f"Getting trace {trace_id} for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.get_trace(trace_id)
        return {
            "success": True,
            "trace": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_get_project(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get project information for a tenant.
    
    Args:
        tenant_id: Tenant identifier
    """
    if ctx:
        await ctx.info(f"Getting project info for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.get_project()
        return {
            "success": True,
            "project": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("langfuse://{tenant_id}/info")
async def get_tenant_info(tenant_id: str) -> str:
    """Get information about a tenant."""
    try:
        client_info = await tenant_manager.get_client(tenant_id)
        config = client_info["config"]
        return json.dumps({
            "tenant_id": config.tenant_id,
            "base_url": config.base_url,
            "max_concurrent_requests": config.max_concurrent_requests,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("langfuse://info")
def langfuse_info() -> str:
    """Get information about the Langfuse MCP server."""
    return "Langfuse MCP Server - Multi-tenant observability and tracing"


def main():
    """Run the Langfuse server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8011"))
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
