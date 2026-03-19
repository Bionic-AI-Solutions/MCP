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
    """Register a new GenImage tenant configuration for multi-tenant image generation.

    Sets up a new tenant with the provided Runware API credentials so that
    subsequent image generation, upscaling, and background removal calls can be
    made on behalf of that tenant. The configuration is persisted to Redis (when
    available) so it survives server restarts.

    Use this tool before calling any other gi_* tool for a given tenant. If the
    tenant is already registered, calling this again will overwrite the existing
    configuration. Tenants can also be pre-configured via environment variables
    (GENIMAGE_TENANT_{TENANT_ID}_RUNWARE_API_KEY, etc.), in which case explicit
    registration is not required.

    Args:
        tenant_id: str - Unique identifier for this tenant. Used in all subsequent
            API calls to route requests to the correct Runware account.
        runware_api_key: str - Runware API key for this tenant. Obtain one by
            signing up at https://runware.ai/ and generating a key in the dashboard.
        base_url: str, default "https://api.runware.ai/v1" - Runware API base URL.
            Override only if using a custom or proxy endpoint.
        max_concurrent_requests: int, default 10 - Maximum number of concurrent
            requests allowed for this tenant. Controls the semaphore used to
            throttle parallel image operations.

    Returns:
        Dict with:
        - success (bool): Whether the tenant was registered successfully.
        - message (str): Human-readable confirmation message.

    Notes:
        - The Runware API key is stored in Redis in plain text. For production
          deployments, consider adding an encryption layer.
        - If Redis is unavailable, the tenant is registered in-memory only and
          will not persist across server restarts.
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
    """Generate an image from a text prompt using the Runware AI inference API.

    Creates an AI-generated image based on the provided text description. The
    image is produced by a diffusion model running on the Runware platform. Use
    this tool when you need to create original images from textual descriptions,
    such as product mockups, creative artwork, concept illustrations, or any
    visual content described in natural language.

    The tenant must be registered (via gi_register_tenant or environment
    variables) before calling this tool. The request is subject to the tenant's
    concurrency limit.

    Args:
        tenant_id: str - Tenant identifier whose Runware account and API key
            will be used for the generation request.
        prompt: str - Text description of the image to generate (the "positive
            prompt"). Be specific and descriptive for best results. For example:
            "a photorealistic mountain landscape at sunset with a lake in the
            foreground".
        width: int, default 1024 - Image width in pixels. Must be compatible
            with the chosen model's supported resolutions. Common values are
            512, 768, 1024.
        height: int, default 1024 - Image height in pixels. Must be compatible
            with the chosen model's supported resolutions. Common values are
            512, 768, 1024.
        model: str or None, default None - Runware model identifier to use for
            generation. When None, defaults to "runware:400@1". You can specify
            alternative models using the Runware model ID format (e.g.,
            "civitai:943001@1055701" for CivitAI-hosted SDXL models).
        steps: int, default 40 - Number of diffusion inference steps. Higher
            values generally produce more detailed images but take longer.
            Typical range is 20-50.
        cfg_scale: float, default 5.0 - Classifier-Free Guidance scale. Controls
            how closely the generation follows the prompt. Higher values (7-15)
            produce images more faithful to the prompt but may reduce diversity;
            lower values (1-5) allow more creative freedom.
        output_path: str or None, default None - Optional local file path to
            save the generated image as a PNG file. If None, the image is
            returned only as base64-encoded data in the response.

    Returns:
        Dict with:
        - success (bool): Whether the image was generated successfully.
        - image_data (str): Base64-encoded PNG image data (present on success).
        - output_path (str | None): The file path where the image was saved,
          or None if no output_path was provided.
        - width (int): The width of the generated image in pixels.
        - height (int): The height of the generated image in pixels.
        - format (str): The image format, always "png".
        - task_uuid (str): Unique identifier for this generation task.
        - error (str): Error message (present only on failure).

    Notes:
        - The API request has a 5-minute timeout to accommodate large or
          complex generation tasks.
        - The returned image_data can be large (several MB in base64). If you
          only need the file on disk, provide output_path to avoid transferring
          the full base64 payload unnecessarily.
        - Width and height combinations should be sensible for the chosen model;
          extreme aspect ratios may produce poor results.
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
    """Upscale an image to a higher resolution using the Runware AI upscaling API.

    Increases the resolution of an existing image by the specified scale factor
    while preserving detail and sharpness through AI-powered super-resolution.
    Use this tool when you have a low-resolution image that needs to be enlarged,
    such as enhancing thumbnails, improving print quality, or preparing images
    for high-DPI displays.

    The input can be provided as either a base64-encoded string or a local file
    path. The tool automatically detects which format is used: strings shorter
    than 200 characters are treated as file paths; longer strings are treated as
    base64-encoded image data.

    The tenant must be registered (via gi_register_tenant or environment
    variables) before calling this tool.

    Args:
        tenant_id: str - Tenant identifier whose Runware account and API key
            will be used for the upscale request.
        image_data: str - The image to upscale. Accepts either:
            (1) A base64-encoded string of the image binary data (PNG, JPEG, or
                WebP), or
            (2) A local file path to an image file (e.g., "/tmp/photo.png").
            The format is auto-detected based on string length (< 200 chars
            is treated as a file path).
        scale: int, default 2 - The upscale multiplier. A value of 2 doubles
            both width and height (4x total pixels); a value of 4 quadruples
            them (16x total pixels). Supported values depend on the Runware
            API plan.
        output_path: str or None, default None - Optional local file path to
            save the upscaled image. If None, the image is returned only as
            base64-encoded data in the response.

    Returns:
        Dict with:
        - success (bool): Whether the upscaling succeeded.
        - image_data (str): Base64-encoded upscaled image data (present on
          success).
        - output_path (str | None): The file path where the image was saved,
          or None if no output_path was provided.
        - scale (int): The upscale factor that was applied.
        - error (str): Error message (present only on failure).

    Notes:
        - Upscaling very large images (e.g., already 4K) with high scale factors
          may hit API size limits or produce diminishing quality returns.
        - The returned base64 image data can be significantly larger than the
          input due to the increased resolution.
        - The 5-minute HTTP timeout applies to this operation as well.
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
    """Remove the background from an image using the Runware AI background removal API.

    Automatically detects the foreground subject in an image and removes the
    background, producing a transparent-background PNG. Uses the RemBG 1.4 model
    (runware:109@1) under the hood. Use this tool when you need to isolate a
    subject from its background, such as for product photography, creating
    stickers or overlays, compositing images, or preparing assets for graphic
    design.

    The input can be provided as either a base64-encoded string or a local file
    path. The tool automatically detects which format is used: strings shorter
    than 200 characters are treated as file paths; longer strings are treated as
    base64-encoded image data.

    The tenant must be registered (via gi_register_tenant or environment
    variables) before calling this tool.

    Args:
        tenant_id: str - Tenant identifier whose Runware account and API key
            will be used for the background removal request.
        image_data: str - The image from which to remove the background. Accepts
            either:
            (1) A base64-encoded string of the image binary data (PNG, JPEG, or
                WebP), or
            (2) A local file path to an image file (e.g., "/tmp/photo.png").
            The format is auto-detected based on string length (< 200 chars
            is treated as a file path).
        output_path: str or None, default None - Optional local file path to
            save the processed image (with transparent background). If None,
            the image is returned only as base64-encoded data in the response.

    Returns:
        Dict with:
        - success (bool): Whether the background removal succeeded.
        - image_data (str): Base64-encoded PNG image data with transparent
          background (present on success).
        - output_path (str | None): The file path where the image was saved,
          or None if no output_path was provided.
        - error (str): Error message (present only on failure).

    Notes:
        - The output is always a PNG with an alpha channel (transparency),
          regardless of the input format.
        - Works best with images that have a clear distinction between foreground
          subject and background. Complex scenes with multiple overlapping
          subjects may produce imperfect masks.
        - The RemBG 1.4 model is used by default and cannot be changed via this
          tool's parameters.
        - The 5-minute HTTP timeout applies to this operation as well.
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
