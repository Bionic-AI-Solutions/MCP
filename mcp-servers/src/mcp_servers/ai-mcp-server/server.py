"""
AI MCP Server (Multi-tenant)

A FastMCP server providing GPU-AI tools (OpenAI-compatible API)
with multi-tenant support. Each tenant can have their own API base URL.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import modules using absolute imports
from mcp_servers.ai-mcp-server.tenant_manager import AITenantManager
from mcp_servers.ai-mcp-server.client import AIClientWrapper

# Initialize tenant manager
tenant_manager = AITenantManager()


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
mcp = FastMCP("AI MCP Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "ai-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def ai_register_tenant(
    tenant_id: str,
    api_base_url: str = "http://192.168.0.10:8000",
    api_key: Optional[str] = None,
    timeout: int = 300,
    max_concurrent_requests: int = 10,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new AI tenant configuration.
    
    Args:
        tenant_id: Unique identifier for this tenant
        api_base_url: GPU-AI API base URL for this tenant (default: http://192.168.0.10:8000)
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds (default: 300)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 10)
    """
    if ctx:
        await ctx.info(f"Registering AI tenant: {tenant_id}")

    from mcp_servers.ai-mcp-server.tenant_manager import AITenantConfig

    config = AITenantConfig(
        tenant_id=tenant_id,
        api_base_url=api_base_url,
        api_key=api_key,
        timeout=timeout,
        max_concurrent_requests=max_concurrent_requests,
    )

    try:
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
async def ai_list_models(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List available AI models for a tenant.
    
    Args:
        tenant_id: Tenant identifier
    """
    if ctx:
        await ctx.info(f"Listing models for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.list_models()
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_chat_completion(
    tenant_id: str,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    stream: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a chat completion using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        model: Model name to use
        messages: List of message objects with 'role' and 'content'
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0-2)
        top_p: Nucleus sampling parameter
        stream: Whether to stream the response
    """
    if ctx:
        await ctx.info(f"Creating chat completion for tenant: {tenant_id} with model: {model}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.chat_completions(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=stream,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_text_completion(
    tenant_id: str,
    model: str,
    prompt: str,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    stream: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a text completion using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        model: Model name to use
        prompt: Text prompt to complete
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0-2)
        top_p: Nucleus sampling parameter
        stream: Whether to stream the response
    """
    if ctx:
        await ctx.info(f"Creating text completion for tenant: {tenant_id} with model: {model}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.text_completions(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=stream,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
