"""
GenImage MCP Server (Multi-tenant)

A FastMCP server providing AI image generation using Runware API
with multi-tenant support. Each tenant provides their own Runware API key.
"""

import json
import base64
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import modules using absolute imports
from mcp_servers.genImage.tenant_manager import GenImageTenantManager
from mcp_servers.genImage.client import GenImageClientWrapper

# Initialize tenant manager
tenant_manager = GenImageTenantManager()


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
mcp = FastMCP("GenImage Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "genImage-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Request/Response Models
# ============================================================================

class ImageGenerationRequest(BaseModel):
    """Request model for image generation."""

    tenant_id: str = Field(..., description="Tenant identifier")
    prompt: str = Field(..., description="Text description of the image to generate")
    width: int = Field(default=1024, description="Image width in pixels")
    height: int = Field(default=1024, description="Image height in pixels")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def gi_register_tenant(
    tenant_id: str,
    runware_api_key: str,
    base_url: str = "https://api.runware.ai/v1",
    max_concurrent_requests: int = 10,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new GenImage tenant configuration.
    
    Args:
        tenant_id: Unique identifier for this tenant
        runware_api_key: Runware API key for this tenant (get from https://runware.ai/)
        base_url: Runware API base URL (default: https://api.runware.ai/v1)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 10)
    """
    if ctx:
        await ctx.info(f"Registering GenImage tenant: {tenant_id}")

    from mcp_servers.genImage.tenant_manager import GenImageTenantConfig

    config = GenImageTenantConfig(
        tenant_id=tenant_id,
        runware_api_key=runware_api_key,
        base_url=base_url,
        max_concurrent_requests=max_concurrent_requests,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


@mcp.tool
async def gi_generate_image(
    tenant_id: str,
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: Optional[str] = None,
    steps: int = 40,
    cfg_scale: float = 5.0,
    output_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate an image using Runware AI.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text description of the image to generate
        width: Image width in pixels (default: 1024)
        height: Image height in pixels (default: 1024)
        model: Model ID (default: civitai:943001@1055701 - SDXL-based)
        steps: Number of inference steps (default: 40)
        cfg_scale: CFG scale (default: 5.0)
        output_path: Optional path to save the image
    """
    if ctx:
        await ctx.info(f"Generating image for tenant: {tenant_id} with prompt: {prompt[:50]}...")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.generate_image(
            prompt=prompt,
            width=width,
            height=height,
            model=model,
            steps=steps,
            cfg_scale=cfg_scale,
            output_path=output_path,
        )
        
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def gi_upscale_image(
    tenant_id: str,
    image_data: str,  # Base64-encoded image or file path
    scale: int = 2,
    output_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Upscale an image using Runware AI.
    
    Args:
        tenant_id: Tenant identifier
        image_data: Base64-encoded image data or file path
        scale: Upscale factor (default: 2)
        output_path: Optional path to save the upscaled image
    """
    if ctx:
        await ctx.info(f"Upscaling image for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.upscale_image(
            image_data=image_data,
            scale=scale,
            output_path=output_path,
        )
        
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def gi_remove_background(
    tenant_id: str,
    image_data: str,  # Base64-encoded image or file path
    output_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove background from an image using Runware AI.
    
    Args:
        tenant_id: Tenant identifier
        image_data: Base64-encoded image data or file path
        output_path: Optional path to save the processed image
    """
    if ctx:
        await ctx.info(f"Removing background for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.remove_background(
            image_data=image_data,
            output_path=output_path,
        )
        
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("genImage://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    try:
        client_info = await tenant_manager.get_client(tenant_id)
        config = client_info["config"]
        
        result = {
            "tenant_id": tenant_id,
            "status": "active",
            "base_url": config.base_url,
            "max_concurrent_requests": config.max_concurrent_requests,
            "runware_api_key_configured": bool(config.runware_api_key),
        }
    except Exception as e:
        result = {
            "tenant_id": tenant_id,
            "status": "error",
            "error": str(e),
        }
    return json.dumps(result, indent=2)


@mcp.resource("genImage://info")
def server_info() -> str:
    """Get information about the GenImage MCP server."""
    return "GenImage MCP Server - Multi-tenant AI image generation with Runware API"


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the GenImage server."""
    mcp.run()


if __name__ == "__main__":
    main()
