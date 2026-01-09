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
from mcp_servers.ai_mcp_server.tenant_manager import AITenantManager
from mcp_servers.ai_mcp_server.client import AIClientWrapper

# Initialize tenant manager
tenant_manager = AITenantManager()


# ============================================================================
# Helper Functions for Provider Routing
# ============================================================================

def _get_provider_client(client_info: Dict[str, Any], service_type: str):
    """Get the appropriate provider client based on service type.
    
    Args:
        client_info: Client info dict from tenant_manager
        service_type: 'llm', 'stt', 'tts', 'embeddings'
    
    Returns:
        Provider client or None if should use main GPU-AI client
    """
    providers = client_info.get("providers", {})
    config = client_info.get("config")
    
    # For global tenant, always use GPU-AI API
    if config and config.tenant_id == "global":
        return None  # Use main client
    
    # Route based on service type
    if service_type in ["llm", "stt"]:
        return providers.get("openrouter")
    elif service_type == "tts":
        return providers.get("elevenlabs")
    elif service_type == "embeddings":
        return providers.get("openai")
    
    return None


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
    openrouter_api_key: Optional[str] = None,
    elevenlabs_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    timeout: int = 300,
    max_concurrent_requests: int = 10,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new AI tenant configuration with multi-provider support.
    
    For "global" tenant: Uses GPU-AI API at 192.168.0.10:8000
    For other tenants: Routes to:
    - LLM/STT → OpenRouter (requires openrouter_api_key)
    - TTS → Eleven Labs (requires elevenlabs_api_key)
    - Embeddings → OpenAI (requires openai_api_key)
    
    Args:
        tenant_id: Unique identifier for this tenant (use "global" for GPU-AI API)
        api_base_url: GPU-AI API base URL (default: http://192.168.0.10:8000)
        api_key: Optional API key for GPU-AI API authentication
        openrouter_api_key: OpenRouter API key for LLM and STT services (non-global tenants)
        elevenlabs_api_key: Eleven Labs API key for TTS service (non-global tenants)
        openai_api_key: OpenAI API key for embeddings service (non-global tenants)
        timeout: Request timeout in seconds (default: 300)
        max_concurrent_requests: Maximum concurrent requests per tenant (default: 10)
    """
    if ctx:
        await ctx.info(f"Registering AI tenant: {tenant_id}")

    from mcp_servers.ai_mcp_server.tenant_manager import AITenantConfig

    config = AITenantConfig(
        tenant_id=tenant_id,
        api_base_url=api_base_url,
        api_key=api_key,
        openrouter_api_key=openrouter_api_key,
        elevenlabs_api_key=elevenlabs_api_key,
        openai_api_key=openai_api_key,
        timeout=timeout,
        max_concurrent_requests=max_concurrent_requests,
    )

    try:
        await tenant_manager.register_tenant(config)
        provider_info = []
        if tenant_id != "global":
            if openrouter_api_key:
                provider_info.append("OpenRouter (LLM/STT)")
            if elevenlabs_api_key:
                provider_info.append("Eleven Labs (TTS)")
            if openai_api_key:
                provider_info.append("OpenAI (Embeddings)")
        
        message = f"Tenant '{tenant_id}' registered successfully"
        if provider_info:
            message += f" with providers: {', '.join(provider_info)}"
        else:
            message += " (using GPU-AI API)"
        
        return {
            "success": True,
            "message": message,
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
    """List available AI models for a tenant (GPU-AI API or OpenRouter for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
    """
    if ctx:
        await ctx.info(f"Listing models for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "llm")
        if provider_client:
            # Use OpenRouter for non-global tenants
            result = await provider_client.list_models()
            return result
        else:
            # Use GPU-AI API for global tenant
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
    """Create a chat completion using GPU-AI or OpenRouter (for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
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
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "llm")
        if provider_client:
            # Use OpenRouter for non-global tenants
            result = await provider_client.chat_completions(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            return result
        else:
            # Use GPU-AI API for global tenant
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
    """Create a text completion using GPU-AI or OpenRouter (for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
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
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "llm")
        if provider_client:
            # Use OpenRouter for non-global tenants
            result = await provider_client.text_completions(
                model=model,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            return result
        else:
            # Use GPU-AI API for global tenant
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


@mcp.tool
async def ai_create_embeddings(
    tenant_id: str,
    model: str,
    input_text: str,
    encoding_format: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create embeddings for input text using GPU-AI or OpenAI (for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
        model: Model name to use for embeddings
        input_text: Text to create embeddings for
        encoding_format: Format for the embeddings (e.g., "float", "base64")
    """
    if ctx:
        await ctx.info(f"Creating embeddings for tenant: {tenant_id} with model: {model}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "embeddings")
        if provider_client:
            # Use OpenAI for non-global tenants
            result = await provider_client.create_embeddings(
                model=model,
                input_text=input_text,
                encoding_format=encoding_format,
            )
            return result
        else:
            # Use GPU-AI API for global tenant
            wrapper = client_info["client"]
            result = await wrapper.create_embeddings(
                model=model,
                input_text=input_text,
                encoding_format=encoding_format,
            )
            return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_create_audio_transcription(
    tenant_id: str,
    file_data: str,  # Base64-encoded audio file
    filename: str,
    model: str = "whisper-1",
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    response_format: Optional[str] = None,
    temperature: Optional[float] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Transcribe audio to text using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        file_data: Base64-encoded audio file content
        filename: Name of the audio file
        model: Model to use for transcription (default: whisper-1)
        language: Language of the audio (ISO-639-1 format)
        prompt: Optional text to guide the model's style
        response_format: Format of the response (json, text, srt, verbose_json, vtt)
        temperature: Sampling temperature (0-1)
    """
    if ctx:
        await ctx.info(f"Transcribing audio for tenant: {tenant_id}")

    try:
        import base64
        audio_bytes = base64.b64decode(file_data)
        
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.create_audio_transcription(
            file_data=audio_bytes,
            filename=filename,
            model=model,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_create_audio_translation(
    tenant_id: str,
    file_data: str,  # Base64-encoded audio file
    filename: str,
    model: str = "whisper-1",
    prompt: Optional[str] = None,
    response_format: Optional[str] = None,
    temperature: Optional[float] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Translate audio to English text using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        file_data: Base64-encoded audio file content
        filename: Name of the audio file
        model: Model to use for translation (default: whisper-1)
        prompt: Optional text to guide the model's style
        response_format: Format of the response (json, text, srt, verbose_json, vtt)
        temperature: Sampling temperature (0-1)
    """
    if ctx:
        await ctx.info(f"Translating audio for tenant: {tenant_id}")

    try:
        import base64
        audio_bytes = base64.b64decode(file_data)
        
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.create_audio_translation(
            file_data=audio_bytes,
            filename=filename,
            model=model,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_create_image(
    tenant_id: str,
    prompt: str,
    model: Optional[str] = None,
    n: int = 1,
    size: str = "1024x1024",
    quality: Optional[str] = None,
    response_format: Optional[str] = None,
    style: Optional[str] = None,
    user: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate an image from a text prompt using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text description of the image to generate
        model: Model to use for image generation
        n: Number of images to generate (1-10)
        size: Size of the generated image (256x256, 512x512, 1024x1024)
        quality: Quality of the image (standard, hd)
        response_format: Format of the response (url, b64_json)
        style: Style of the image (vivid, natural)
        user: Unique identifier for the end user
    """
    if ctx:
        await ctx.info(f"Generating image for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.create_image(
            prompt=prompt,
            model=model,
            n=n,
            size=size,
            quality=quality,
            response_format=response_format,
            style=style,
            user=user,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_create_moderation(
    tenant_id: str,
    input_text: str,
    model: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Classify if text violates content policy using GPU-AI.
    
    Args:
        tenant_id: Tenant identifier
        input_text: Text to classify
        model: Model to use for moderation (default: text-moderation-latest)
    """
    if ctx:
        await ctx.info(f"Moderating text for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.create_moderation(
            input_text=input_text,
            model=model,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_get_mcp_tools(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get additional MCP tools from the GPU-AI API server at /mcp/tools/tools.
    
    This queries the GPU-AI API server for any additional tools it may expose
    beyond the standard OpenAI-compatible endpoints.
    
    Args:
        tenant_id: Tenant identifier
    """
    if ctx:
        await ctx.info(f"Fetching MCP tools from GPU-AI API server for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.get_mcp_tools()
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_proxy_service_request(
    tenant_id: str,
    service_name: str,
    path: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Proxy a request to a GPU-AI service endpoint.
    
    Available services: llm, audio, xtts_v2, embeddings, video_generation, video_recognition
    
    Examples:
    - Get LLM models: service_name="llm", path="v1/models", method="GET"
    - LLM chat: service_name="llm", path="v1/chat/completions", method="POST"
    - Generate embeddings: service_name="embeddings", path="embeddings", method="POST"
    
    Args:
        tenant_id: Tenant identifier
        service_name: Service to proxy to (llm, audio, xtts_v2, embeddings, video_generation, video_recognition)
        path: Path to proxy to (e.g., "v1/models", "embeddings", "v1/chat/completions")
        method: HTTP method (GET, POST, PUT, DELETE)
        payload: Optional JSON payload for POST/PUT requests
    """
    if ctx:
        await ctx.info(f"Proxying {method} request to {service_name}/{path} for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name=service_name,
            path=path,
            method=method,
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_generate_video(
    tenant_id: str,
    prompt: str,
    path: str = "generate",
    additional_params: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate a video from a text prompt using GPU-AI video generation service.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text description of the video to generate
        path: API path for video generation (default: "generate")
        additional_params: Additional parameters for video generation (duration, resolution, style, etc.)
    """
    if ctx:
        await ctx.info(f"Generating video for tenant: {tenant_id} with prompt: {prompt[:50]}...")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        # Build payload
        payload = {"prompt": prompt}
        if additional_params:
            payload.update(additional_params)
        
        result = await wrapper.proxy_service_request(
            service_name="video_generation",
            path=path,
            method="POST",
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_recognize_video(
    tenant_id: str,
    video_data: str,  # Base64-encoded video or URL
    path: str = "recognize",
    additional_params: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Recognize and analyze video content using GPU-AI video recognition service.
    
    Args:
        tenant_id: Tenant identifier
        video_data: Base64-encoded video content or URL to video
        path: API path for video recognition (default: "recognize")
        additional_params: Additional parameters for video recognition (tasks, format, etc.)
    """
    if ctx:
        await ctx.info(f"Recognizing video for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        # Build payload
        payload = {"video": video_data}
        if additional_params:
            payload.update(additional_params)
        
        result = await wrapper.proxy_service_request(
            service_name="video_recognition",
            path=path,
            method="POST",
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Audio Tools
# ============================================================================

@mcp.tool
async def ai_audio_speech_to_text(
    tenant_id: str,
    audio_data: str,  # Base64-encoded audio
    filename: str = "audio.mp3",
    model: Optional[str] = None,
    language: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Convert speech to text using GPU-AI audio service or OpenRouter (for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
        audio_data: Base64-encoded audio file content
        filename: Name of the audio file
        model: Model to use for transcription
        language: Language of the audio (ISO-639-1 format)
    """
    if ctx:
        await ctx.info(f"Converting speech to text for tenant: {tenant_id}")

    try:
        import base64
        audio_bytes = base64.b64decode(audio_data)
        
        client_info = await tenant_manager.get_client(tenant_id)
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "stt")
        if provider_client:
            # Use OpenRouter for non-global tenants
            result = await provider_client.speech_to_text(audio_bytes, model=model, language=language)
            return result
        else:
            # Use GPU-AI API for global tenant
            wrapper = client_info["client"]
            result = await wrapper.proxy_service_request(
                service_name="audio",
                path="speech_to_text",
                method="POST",
                payload={"audio": audio_data, "filename": filename, "model": model, "language": language},
            )
            return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_audio_text_to_speech(
    tenant_id: str,
    text: str,
    voice_id: Optional[str] = None,
    model: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Convert text to speech using GPU-AI audio service or Eleven Labs (for non-global tenants).
    
    Args:
        tenant_id: Tenant identifier (use "global" for GPU-AI API)
        text: Text to convert to speech
        voice_id: Voice ID to use (for Eleven Labs or GPU-AI)
        model: Model to use for TTS
    """
    if ctx:
        await ctx.info(f"Converting text to speech for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        
        # Check if we should use provider client
        provider_client = _get_provider_client(client_info, "tts")
        if provider_client:
            # Use Eleven Labs for non-global tenants
            audio_bytes = await provider_client.text_to_speech(
                text=text,
                voice_id=voice_id or "21m00Tcm4TlvDq8ikWAM",
            )
            import base64
            return {
                "success": True,
                "audio": base64.b64encode(audio_bytes).decode(),
                "format": "mp3",
            }
        else:
            # Use GPU-AI API for global tenant
            wrapper = client_info["client"]
            result = await wrapper.proxy_service_request(
                service_name="audio",
                path="text_to_speech",
                method="POST",
                payload={"text": text, "voice_id": voice_id, "model": model},
            )
            return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_audio_list_models(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List available audio models for a tenant.
    
    Args:
        tenant_id: Tenant identifier
    """
    if ctx:
        await ctx.info(f"Listing audio models for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="audio",
            path="list_models",
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_audio_voice_clone_xtts_v2(
    tenant_id: str,
    text: str,
    voice_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Clone voice using XTTS v2 service.
    
    Args:
        tenant_id: Tenant identifier
        text: Text to convert to speech
        voice_id: Voice ID to clone
    """
    if ctx:
        await ctx.info(f"Cloning voice for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="xtts_v2",
            path="voice_clone",
            method="POST",
            payload={"text": text, "voice_id": voice_id},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_xtts_v2_list_models(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List available XTTS v2 models.
    
    Args:
        tenant_id: Tenant identifier
    """
    if ctx:
        await ctx.info(f"Listing XTTS v2 models for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="xtts_v2",
            path="list_models",
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Embeddings Tools
# ============================================================================

@mcp.tool
async def ai_embeddings_get_status(
    tenant_id: str,
    task_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get status of embeddings generation task.
    
    Args:
        tenant_id: Tenant identifier
        task_id: Task ID to check status for
    """
    if ctx:
        await ctx.info(f"Getting embeddings status for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        path = f"get_status" + (f"/{task_id}" if task_id else "")
        result = await wrapper.proxy_service_request(
            service_name="embeddings",
            path=path,
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Video Tools (Additional)
# ============================================================================

@mcp.tool
async def ai_video_get_status(
    tenant_id: str,
    task_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get status of video generation task.
    
    Args:
        tenant_id: Tenant identifier
        task_id: Task ID to check status for
    """
    if ctx:
        await ctx.info(f"Getting video generation status for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        path = f"get_status" + (f"/{task_id}" if task_id else "")
        result = await wrapper.proxy_service_request(
            service_name="video_generation",
            path=path,
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_video_synopsis(
    tenant_id: str,
    video_data: str,  # Base64-encoded video or URL
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate a synopsis of video content.
    
    Args:
        tenant_id: Tenant identifier
        video_data: Base64-encoded video content or URL to video
    """
    if ctx:
        await ctx.info(f"Generating video synopsis for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="video_recognition",
            path="synopsis",
            method="POST",
            payload={"video": video_data},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_video_qa(
    tenant_id: str,
    video_data: str,  # Base64-encoded video or URL
    question: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Answer questions about video content.
    
    Args:
        tenant_id: Tenant identifier
        video_data: Base64-encoded video content or URL to video
        question: Question to ask about the video
    """
    if ctx:
        await ctx.info(f"Answering video question for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="video_recognition",
            path="qa",
            method="POST",
            payload={"video": video_data, "question": question},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_video_recognition_get_status(
    tenant_id: str,
    task_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get status of video recognition task.
    
    Args:
        tenant_id: Tenant identifier
        task_id: Task ID to check status for
    """
    if ctx:
        await ctx.info(f"Getting video recognition status for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        path = f"get_status" + (f"/{task_id}" if task_id else "")
        result = await wrapper.proxy_service_request(
            service_name="video_recognition",
            path=path,
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# WAN2 Tools
# ============================================================================

@mcp.tool
async def ai_wan2_text_to_video(
    tenant_id: str,
    prompt: str,
    additional_params: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate video from text using WAN2 service.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Text description of the video to generate
        additional_params: Additional parameters for video generation
    """
    if ctx:
        await ctx.info(f"Generating WAN2 video from text for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        payload = {"prompt": prompt}
        if additional_params:
            payload.update(additional_params)
        
        result = await wrapper.proxy_service_request(
            service_name="wan2",
            path="text_to_video",
            method="POST",
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_wan2_image_to_video(
    tenant_id: str,
    image_data: str,  # Base64-encoded image or URL
    additional_params: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate video from image using WAN2 service.
    
    Args:
        tenant_id: Tenant identifier
        image_data: Base64-encoded image content or URL to image
        additional_params: Additional parameters for video generation
    """
    if ctx:
        await ctx.info(f"Generating WAN2 video from image for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        payload = {"image": image_data}
        if additional_params:
            payload.update(additional_params)
        
        result = await wrapper.proxy_service_request(
            service_name="wan2",
            path="image_to_video",
            method="POST",
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_wan2_compress_video(
    tenant_id: str,
    video_data: str,  # Base64-encoded video or URL
    additional_params: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Compress video using WAN2 service.
    
    Args:
        tenant_id: Tenant identifier
        video_data: Base64-encoded video content or URL to video
        additional_params: Additional parameters for compression
    """
    if ctx:
        await ctx.info(f"Compressing video with WAN2 for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        payload = {"video": video_data}
        if additional_params:
            payload.update(additional_params)
        
        result = await wrapper.proxy_service_request(
            service_name="wan2",
            path="compress_video",
            method="POST",
            payload=payload,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_wan2_get_status(
    tenant_id: str,
    task_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get status of WAN2 task.
    
    Args:
        tenant_id: Tenant identifier
        task_id: Task ID to check status for
    """
    if ctx:
        await ctx.info(f"Getting WAN2 status for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        path = f"get_status" + (f"/{task_id}" if task_id else "")
        result = await wrapper.proxy_service_request(
            service_name="wan2",
            path=path,
            method="GET",
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Prompt-based Tools
# ============================================================================

@mcp.tool
async def ai_text_to_speech_prompt(
    tenant_id: str,
    prompt: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate text-to-speech using a natural language prompt.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Natural language prompt describing the desired speech output
    """
    if ctx:
        await ctx.info(f"Generating TTS from prompt for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="audio",
            path="text_to_speech_prompt",
            method="POST",
            payload={"prompt": prompt},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_video_generation_prompt(
    tenant_id: str,
    prompt: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate video using a natural language prompt.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Natural language prompt describing the desired video
    """
    if ctx:
        await ctx.info(f"Generating video from prompt for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="video_generation",
            path="prompt",
            method="POST",
            payload={"prompt": prompt},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_video_analysis_prompt(
    tenant_id: str,
    video_data: str,  # Base64-encoded video or URL
    prompt: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Analyze video using a natural language prompt.
    
    Args:
        tenant_id: Tenant identifier
        video_data: Base64-encoded video content or URL to video
        prompt: Natural language prompt describing what to analyze
    """
    if ctx:
        await ctx.info(f"Analyzing video with prompt for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="video_recognition",
            path="prompt",
            method="POST",
            payload={"video": video_data, "prompt": prompt},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def ai_embeddings_analysis_prompt(
    tenant_id: str,
    prompt: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Generate embeddings analysis using a natural language prompt.
    
    Args:
        tenant_id: Tenant identifier
        prompt: Natural language prompt describing the embeddings analysis needed
    """
    if ctx:
        await ctx.info(f"Generating embeddings analysis from prompt for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        wrapper = client_info["client"]
        
        result = await wrapper.proxy_service_request(
            service_name="embeddings",
            path="analysis_prompt",
            method="POST",
            payload={"prompt": prompt},
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
