"""
Nano Banana MCP Server (Multi-tenant)

A FastMCP server providing AI image generation and editing using Google Gemini API
with multi-tenant support. Each tenant provides their own Gemini API key.
"""

import json
import base64
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import using importlib to handle directory with hyphen
import importlib.util
import sys
from pathlib import Path

# Load tenant_manager module
tenant_manager_path = Path(__file__).parent / "tenant_manager.py"
spec = importlib.util.spec_from_file_location("tenant_manager", tenant_manager_path)
tenant_manager_module = importlib.util.module_from_spec(spec)
sys.modules["tenant_manager"] = tenant_manager_module
spec.loader.exec_module(tenant_manager_module)
NanoBananaTenantManager = tenant_manager_module.NanoBananaTenantManager

# Load client module
client_path = Path(__file__).parent / "client.py"
spec = importlib.util.spec_from_file_location("client", client_path)
client_module = importlib.util.module_from_spec(spec)
sys.modules["client"] = client_module
spec.loader.exec_module(client_module)
NanoBananaClientWrapper = client_module.NanoBananaClientWrapper

# Initialize tenant manager
tenant_manager = NanoBananaTenantManager()


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
mcp = FastMCP("Nano Banana Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "nano-banana-mcp-server",
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
async def nb_register_tenant(
    tenant_id: str,
    gemini_api_key: str,
    model: str = "gemini-2.0-flash-exp",
    max_concurrent_requests: int = 10,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new Nano Banana tenant configuration.
    
    Args:
        tenant_id: Unique identifier for this tenant
        gemini_api_key: Google Gemini API key for this tenant
        model: Gemini model to use (default: gemini-2.0-flash-exp)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 10)
    """
    if ctx:
        await ctx.info(f"Registering Nano Banana tenant: {tenant_id}")

    # Import using the same method as above
    NanoBananaTenantConfig = tenant_manager_module.NanoBananaTenantConfig

    config = NanoBananaTenantConfig(
        tenant_id=tenant_id,
        gemini_api_key=gemini_api_key,
        model=model,
        max_concurrent_requests=max_concurrent_requests,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


@mcp.tool
async def nb_generate_image(
    tenant_id: str,
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    output_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate an image using Gemini AI.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text description of the image to generate
        width: Image width in pixels (default: 1024)
        height: Image height in pixels (default: 1024)
        output_path: Optional path to save the image
    """
    if ctx:
        await ctx.info(f"Generating image for tenant: {tenant_id} with prompt: {prompt[:50]}...")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = NanoBananaClientWrapper(
            client_info["client"],
            client_info["semaphore"],
            client_info["config"].model,
        )
        
        result = await wrapper.generate_image(
            prompt=prompt,
            output_path=output_path,
            width=width,
            height=height,
        )
        
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def nb_edit_image(
    tenant_id: str,
    image_data: str,  # Base64-encoded image or file path
    prompt: str,
    output_path: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Edit an existing image using Gemini AI.
    
    Args:
        tenant_id: Tenant identifier
        image_data: Base64-encoded image data or file path
        prompt: Description of the edit to make
        output_path: Optional path to save the edited image
    """
    if ctx:
        await ctx.info(f"Editing image for tenant: {tenant_id}")

    try:
        import tempfile
        import os
        
        # Handle base64 or file path
        if os.path.exists(image_data):
            image_path = image_data
        else:
            # Assume it's base64, decode and save to temp file
            try:
                image_bytes = base64.b64decode(image_data)
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp.write(image_bytes)
                    image_path = tmp.name
            except Exception:
                return {
                    "success": False,
                    "error": "Invalid image_data: must be base64-encoded string or valid file path",
                }
        
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = NanoBananaClientWrapper(
            client_info["client"],
            client_info["semaphore"],
            client_info["config"].model,
        )
        
        result = await wrapper.edit_image(
            image_path=image_path,
            prompt=prompt,
            output_path=output_path,
        )
        
        # Clean up temp file if we created it
        if not os.path.exists(image_data) and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except Exception:
                pass
        
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def nb_generate_content(
    tenant_id: str,
    prompt: str,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate text content using Gemini AI.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text prompt for content generation
        temperature: Sampling temperature 0.0-1.0 (default: 0.7)
        max_tokens: Maximum tokens to generate
    """
    if ctx:
        await ctx.info(f"Generating content for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = NanoBananaClientWrapper(
            client_info["client"],
            client_info["semaphore"],
            client_info["config"].model,
        )
        
        result = await wrapper.generate_content(
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
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

@mcp.resource("nano-banana://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    try:
        client_info = await tenant_manager.get_client(tenant_id)
        config = client_info["config"]
        
        result = {
            "tenant_id": tenant_id,
            "status": "active",
            "model": config.model,
            "max_concurrent_requests": config.max_concurrent_requests,
            "gemini_api_key_configured": bool(config.gemini_api_key),
        }
    except Exception as e:
        result = {
            "tenant_id": tenant_id,
            "status": "error",
            "error": str(e),
        }
    return json.dumps(result, indent=2)


@mcp.resource("nano-banana://info")
def server_info() -> str:
    """Get information about the Nano Banana MCP server."""
    return "Nano Banana MCP Server - Multi-tenant AI image generation and editing with Gemini API"


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the Nano Banana server."""
    mcp.run()


if __name__ == "__main__":
    main()

