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

    Creates or updates a tenant entry that determines how subsequent AI tool
    calls are routed to backend providers. Tenant configurations are persisted
    to Redis so they survive server restarts.

    Provider routing rules:
    - "global" tenant: All requests are sent to the GPU-AI API at the given
      api_base_url (default http://192.168.0.10:8000). This backend provides
      LLM, STT, TTS, embeddings, image generation, video generation/recognition,
      XTTS v2 voice cloning, and moderation -- all via OpenAI-compatible endpoints.
    - Any other tenant_id: Requests are routed to external providers based on
      service type:
        * LLM and STT -> OpenRouter (requires openrouter_api_key)
        * TTS -> Eleven Labs (requires elevenlabs_api_key)
        * Embeddings -> OpenAI (requires openai_api_key)
      Services without a matching API key will fall back to the GPU-AI API.

    Use this tool before calling any other AI tool if the desired tenant has not
    been registered yet.  Calling it again with the same tenant_id overwrites the
    previous configuration.

    Args:
        tenant_id: Unique identifier for this tenant. Use "global" to target the
            GPU-AI API directly. Any other string creates a multi-provider tenant.
        api_base_url: Base URL of the GPU-AI API server (default:
            "http://192.168.0.10:8000"). Only used for the "global" tenant or as a
            fallback for non-global tenants.
        api_key: Optional Bearer-token API key for authenticating with the GPU-AI
            API. Pass None if the server does not require authentication.
        openrouter_api_key: API key for OpenRouter. Required for non-global tenants
            that need LLM chat/text completions or speech-to-text via OpenRouter.
        elevenlabs_api_key: API key for Eleven Labs. Required for non-global tenants
            that need text-to-speech synthesis via Eleven Labs.
        openai_api_key: API key for OpenAI. Required for non-global tenants that
            need embeddings via the OpenAI embeddings API.
        timeout: HTTP request timeout in seconds (default: 300). Applies to all
            provider clients created for this tenant.
        max_concurrent_requests: Maximum number of concurrent HTTP requests allowed
            per tenant (default: 10). Enforced via an asyncio semaphore.

    Returns:
        Dict with:
        - success (bool): Whether registration succeeded.
        - message (str): Human-readable summary including which providers were
          configured (e.g., "OpenRouter (LLM/STT), Eleven Labs (TTS)").
        - error (str): Error message if registration failed.
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
    """List all available AI models for a given tenant.

    Queries the model catalogue from the appropriate backend. Use this to
    discover which model identifiers to pass to ai_chat_completion,
    ai_text_completion, ai_create_embeddings, and other model-dependent tools.

    Provider routing:
    - "global" tenant: Queries GET /v1/models on the GPU-AI API, which returns
      all locally-hosted models (LLMs, whisper, embedding models, etc.).
    - Other tenants: Queries OpenRouter's model list, which includes hundreds of
      third-party models (GPT-4, Claude, Llama, Mixtral, etc.).

    Note: The returned model list only covers LLM/general models. Audio, video,
    and embedding models may not appear here; refer to ai_audio_list_models,
    ai_xtts_v2_list_models, or the provider documentation for those.

    Args:
        tenant_id: Tenant identifier. Use "global" for GPU-AI API models, or any
            registered tenant ID for OpenRouter models.

    Returns:
        Dict with OpenAI-compatible model list format:
        - object (str): "list"
        - data (list): Array of model objects, each containing:
            - id (str): Model identifier to use in API calls.
            - object (str): "model"
            - created (int): Unix timestamp of model creation.
            - owned_by (str): Organization or provider that owns the model.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Create a chat completion from a conversation of messages.

    Sends a list of messages (system, user, assistant turns) to an LLM and
    returns the model's response. This is the primary tool for multi-turn
    conversational AI, instruction-following, and any task that benefits from
    chat-style prompting.

    Provider routing:
    - "global" tenant: Uses the GPU-AI API (POST /v1/chat/completions), which
      hosts local models. Streaming is supported.
    - Other tenants: Uses OpenRouter, which proxies to hundreds of third-party
      models (GPT-4, Claude, Llama, Mixtral, etc.). Streaming is NOT forwarded
      to OpenRouter in this implementation; the full response is returned.

    Each message in the messages list must have at least:
    - "role": One of "system", "user", or "assistant".
    - "content": The text content of the message.
    Multi-modal messages (with image URLs) are supported if the underlying model
    supports them.

    Args:
        tenant_id: Tenant identifier. Use "global" for the GPU-AI API or any
            registered tenant ID for OpenRouter.
        model: Model identifier to use (e.g., "gpt-4", "meta-llama/llama-3-70b",
            or a locally-hosted model name). Use ai_list_models to discover
            available model IDs.
        messages: Ordered list of message dicts, each with "role" (str) and
            "content" (str). Example:
            [{"role": "system", "content": "You are helpful."},
             {"role": "user", "content": "Hello!"}]
        max_tokens: Maximum number of tokens to generate in the response. If None,
            the model's default limit is used. Higher values allow longer responses
            but increase latency and cost.
        temperature: Sampling temperature between 0 and 2 (default depends on
            model). Lower values (e.g., 0.2) produce more deterministic output;
            higher values (e.g., 1.0) produce more creative/random output.
        top_p: Nucleus sampling parameter between 0 and 1. An alternative to
            temperature -- the model considers tokens whose cumulative probability
            mass reaches top_p. Use either temperature or top_p, not both.
        stream: Whether to stream the response token-by-token (default: False).
            Only supported for the "global" tenant (GPU-AI API). Ignored for
            OpenRouter tenants.

    Returns:
        Dict in OpenAI chat completion format:
        - id (str): Unique completion identifier.
        - object (str): "chat.completion"
        - created (int): Unix timestamp.
        - model (str): The model used.
        - choices (list): Array of completion choices, each with:
            - index (int): Choice index.
            - message (dict): {"role": "assistant", "content": "..."}.
            - finish_reason (str): "stop", "length", etc.
        - usage (dict): Token usage with prompt_tokens, completion_tokens,
          total_tokens.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Create a text completion from a single prompt string.

    Sends a raw text prompt to an LLM and returns the model's continuation.
    Unlike ai_chat_completion, this uses the legacy completions endpoint
    (POST /v1/completions) which takes a single string rather than a list of
    messages. Useful for code completion, text continuation, fill-in-the-blank
    tasks, and models that do not support the chat format.

    Provider routing:
    - "global" tenant: Uses the GPU-AI API (POST /v1/completions). Streaming is
      supported.
    - Other tenants: Uses OpenRouter's text completions endpoint. Streaming is
      NOT forwarded in this implementation.

    Note: Not all models support the completions endpoint. Many newer models
    (GPT-4, Claude, etc.) only expose a chat completions interface. Use
    ai_chat_completion for those models instead.

    Args:
        tenant_id: Tenant identifier. Use "global" for the GPU-AI API or any
            registered tenant ID for OpenRouter.
        model: Model identifier to use (e.g., "text-davinci-003", or a locally
            hosted model name). Use ai_list_models to discover available IDs.
        prompt: The text prompt for the model to complete. Can be anything from a
            single sentence to a multi-paragraph document with a continuation point.
        max_tokens: Maximum number of tokens to generate. If None, the model's
            default limit is used.
        temperature: Sampling temperature between 0 and 2. Lower values produce
            more deterministic output; higher values produce more varied output.
        top_p: Nucleus sampling parameter between 0 and 1. Use either temperature
            or top_p, not both.
        stream: Whether to stream the response (default: False). Only supported
            for the "global" tenant (GPU-AI API). Ignored for OpenRouter tenants.

    Returns:
        Dict in OpenAI completion format:
        - id (str): Unique completion identifier.
        - object (str): "text_completion"
        - created (int): Unix timestamp.
        - model (str): The model used.
        - choices (list): Array of completion choices, each with:
            - text (str): The generated text.
            - index (int): Choice index.
            - finish_reason (str): "stop", "length", etc.
        - usage (dict): Token usage with prompt_tokens, completion_tokens,
          total_tokens.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Create vector embeddings for the given input text.

    Converts text into a dense vector representation suitable for semantic
    search, clustering, classification, anomaly detection, and retrieval-
    augmented generation (RAG). The output vectors capture semantic meaning,
    so texts with similar meaning produce vectors that are close together in
    the embedding space.

    Provider routing:
    - "global" tenant: Uses the GPU-AI API (POST /v1/embeddings), which runs
      locally-hosted embedding models.
    - Other tenants: Uses the OpenAI Embeddings API (requires openai_api_key).
      Popular models include "text-embedding-3-small" and "text-embedding-3-large".

    Args:
        tenant_id: Tenant identifier. Use "global" for the GPU-AI API or any
            registered tenant ID for OpenAI embeddings.
        model: Embedding model identifier (e.g., "text-embedding-3-small",
            "text-embedding-3-large", or a locally hosted embedding model name).
        input_text: The text to embed. Maximum token length depends on the model
            (e.g., 8191 tokens for OpenAI text-embedding-3-small). Longer texts
            will be truncated or cause an error depending on the provider.
        encoding_format: Format of the returned embedding vectors. Options:
            "float" (default) -- list of floats; "base64" -- base64-encoded binary.
            If None, the provider's default format is used ("float").

    Returns:
        Dict in OpenAI embeddings format:
        - object (str): "list"
        - data (list): Array of embedding objects, each with:
            - object (str): "embedding"
            - index (int): Index of the embedding.
            - embedding (list[float] | str): The embedding vector, as a list of
              floats or a base64 string depending on encoding_format.
        - model (str): The model used.
        - usage (dict): Token usage with prompt_tokens, total_tokens.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Transcribe audio into text in the original spoken language.

    Converts spoken audio into a text transcription using the Whisper model on
    the GPU-AI API (POST /v1/audio/transcriptions). This is a speech-to-text
    tool that preserves the original language -- use ai_create_audio_translation
    if you need the output translated into English.

    This tool always routes to the GPU-AI API regardless of tenant, because it
    uses the OpenAI-compatible multipart upload endpoint directly.

    Supported audio formats: mp3, mp4, mpeg, mpga, m4a, wav, webm. Maximum file
    size depends on the GPU-AI API configuration (typically 25 MB).

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        file_data: The audio file content encoded as a Base64 string. Encode the
            raw bytes of the audio file (e.g., via Python's base64.b64encode()).
        filename: Original filename including extension (e.g., "interview.mp3",
            "recording.wav"). The extension helps the server determine the audio
            format.
        model: Whisper model identifier (default: "whisper-1"). This is currently
            the only supported model on most deployments.
        language: ISO-639-1 language code of the spoken language (e.g., "en" for
            English, "es" for Spanish, "fr" for French). If None, the model
            auto-detects the language. Supplying the correct language improves
            accuracy and speed.
        prompt: Optional text to guide the model's style or continue a previous
            transcript. The prompt should match the language of the audio. Useful
            for providing context, spelling of proper nouns, or domain-specific
            terminology.
        response_format: Desired output format. Options:
            "json" (default) -- JSON object with the text field;
            "text" -- plain text;
            "srt" -- SubRip subtitle format;
            "verbose_json" -- JSON with word-level timestamps and metadata;
            "vtt" -- WebVTT subtitle format.
        temperature: Sampling temperature between 0 and 1 (default: 0). Lower
            values make the output more deterministic. When set to 0, the model
            uses beam search for maximum accuracy.

    Returns:
        Dict containing:
        - text (str): The transcribed text.
        For "verbose_json" format, additional fields may include:
        - task (str): "transcribe"
        - language (str): Detected language.
        - duration (float): Audio duration in seconds.
        - segments (list): Word/segment-level timing information.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Translate audio from any language into English text.

    Converts spoken audio in any supported language into an English text
    translation using the Whisper model on the GPU-AI API
    (POST /v1/audio/translations). Unlike ai_create_audio_transcription, this
    always outputs English regardless of the source language.

    This tool always routes to the GPU-AI API regardless of tenant, because it
    uses the OpenAI-compatible multipart upload endpoint directly.

    Supported audio formats: mp3, mp4, mpeg, mpga, m4a, wav, webm. Maximum file
    size depends on the GPU-AI API configuration (typically 25 MB).

    Note: There is no language parameter because the source language is
    auto-detected and the output is always English.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        file_data: The audio file content encoded as a Base64 string. Encode the
            raw bytes of the audio file (e.g., via Python's base64.b64encode()).
        filename: Original filename including extension (e.g., "meeting_fr.mp3").
            The extension helps the server determine the audio format.
        model: Whisper model identifier (default: "whisper-1"). This is currently
            the only supported model on most deployments.
        prompt: Optional English text to guide the model's style or provide
            context. Should be in English since the output is always English.
            Useful for proper nouns and domain-specific terms.
        response_format: Desired output format. Options:
            "json" (default) -- JSON object with the text field;
            "text" -- plain text;
            "srt" -- SubRip subtitle format;
            "verbose_json" -- JSON with word-level timestamps and metadata;
            "vtt" -- WebVTT subtitle format.
        temperature: Sampling temperature between 0 and 1 (default: 0). Lower
            values produce more deterministic output.

    Returns:
        Dict containing:
        - text (str): The translated English text.
        For "verbose_json" format, additional fields may include:
        - task (str): "translate"
        - language (str): Detected source language.
        - duration (float): Audio duration in seconds.
        - segments (list): Segment-level timing information.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate one or more images from a text prompt using GPU-AI.

    Creates images via the GPU-AI API's image generation endpoint
    (POST /v1/images/generations), which is OpenAI-compatible. The model
    interprets the text prompt and produces images matching the description.

    This tool always routes to the GPU-AI API regardless of tenant. Image
    generation is not available via OpenRouter or other external providers
    through this server.

    Tips for better results:
    - Be specific and detailed in your prompt (subject, style, lighting, angle).
    - Mention artistic styles or references (e.g., "oil painting", "photorealistic").
    - Use the "hd" quality setting for more detailed images (if supported).

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A detailed text description of the desired image. Longer, more
            descriptive prompts generally produce better results. Maximum length
            depends on the model (typically 1000-4000 characters).
        model: Image generation model identifier. If None, the server's default
            model is used. Available models depend on the GPU-AI API deployment.
        n: Number of images to generate (default: 1). Range: 1-10. Higher values
            increase response time proportionally.
        size: Dimensions of the generated image as "WIDTHxHEIGHT". Common options:
            "256x256", "512x512", "1024x1024" (default), "1024x1792", "1792x1024".
            Available sizes depend on the model.
        quality: Image quality level. Options: "standard" (default, faster) or
            "hd" (higher detail, slower). Not all models support quality selection.
        response_format: How the image is returned. Options:
            "url" (default) -- a temporary URL to download the image;
            "b64_json" -- the image encoded as a base64 JSON string (inline).
        style: Visual style of the generated image. Options:
            "vivid" (default) -- hyper-real, dramatic imagery;
            "natural" -- more natural, less hyper-real. Not all models support this.
        user: A unique identifier for the end user, used for abuse monitoring and
            rate limiting. Optional.

    Returns:
        Dict in OpenAI images format:
        - created (int): Unix timestamp.
        - data (list): Array of image objects, each with:
            - url (str): Temporary download URL (if response_format is "url").
            - b64_json (str): Base64-encoded image (if response_format is "b64_json").
            - revised_prompt (str): The model's interpretation of the prompt
              (if the model supports prompt revision).
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Classify whether text violates content policies using GPU-AI moderation.

    Runs the input text through a content moderation model to detect potentially
    harmful content across multiple categories (hate, violence, sexual content,
    self-harm, etc.). Useful for pre-screening user-generated content, chatbot
    output filtering, or compliance workflows.

    This tool always routes to the GPU-AI API (POST /v1/moderations) regardless
    of tenant. It uses the OpenAI-compatible moderation endpoint.

    The moderation model evaluates the text and returns per-category scores
    (0.0 to 1.0) indicating how likely the text falls into each harmful category,
    along with boolean flags indicating whether each threshold is exceeded.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        input_text: The text to classify for content policy violations. There is
            no strict length limit, but very long texts may be truncated internally
            by the model.
        model: Moderation model identifier. If None, the server uses the latest
            default model (typically "text-moderation-latest"). Alternative:
            "text-moderation-stable" for a fixed model version.

    Returns:
        Dict in OpenAI moderation format:
        - id (str): Unique moderation request identifier.
        - model (str): The model used.
        - results (list): Array of moderation result objects, each with:
            - flagged (bool): True if any category threshold is exceeded.
            - categories (dict): Boolean flags per category (e.g., "hate",
              "violence", "sexual", "self-harm", "harassment").
            - category_scores (dict): Float scores (0.0-1.0) per category,
              indicating confidence of policy violation.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Discover additional MCP tools exposed by the GPU-AI API server.

    Queries the GPU-AI API at GET /mcp/tools/tools to retrieve any extra tools
    that the server makes available beyond the standard OpenAI-compatible
    endpoints. These may include custom GPU-AI-specific capabilities such as
    specialized model management, fine-tuning controls, or hardware monitoring.

    This is a discovery/introspection tool -- call it to find out what additional
    capabilities are available on the GPU-AI API server before attempting to use
    them via ai_proxy_service_request.

    If the /mcp/tools/tools endpoint does not exist on the GPU-AI API server
    (HTTP 404), the tool returns an empty tools list rather than an error.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
            Typically "global" since MCP tools are a GPU-AI-specific feature.

    Returns:
        Dict with:
        - success (bool): Whether the query succeeded.
        - tools (list): Array of tool definition objects exposed by the GPU-AI
          API server. Each tool object typically contains name, description,
          and input schema information. Returns an empty list if the endpoint
          is not available (404).
        - message (str): Informational message if the endpoint is not available.
        - error (str): Error message if the operation failed.
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
    """Proxy a raw HTTP request to a specific GPU-AI service endpoint.

    Sends an arbitrary HTTP request to one of the GPU-AI API's internal service
    endpoints via the proxy path: /api/v1/services/{service_name}/proxy/{path}.
    This is a low-level escape hatch for accessing GPU-AI features that do not
    have a dedicated MCP tool wrapper.

    Use this when you need to access a service endpoint that is not covered by
    the higher-level tools (ai_chat_completion, ai_generate_video, etc.), or
    when you need fine-grained control over the request payload.

    Available services and example paths:
    - "llm": LLM inference (e.g., path="v1/models" for model listing,
      "v1/chat/completions" for chat).
    - "audio": Audio processing (e.g., "speech_to_text", "text_to_speech",
      "list_models", "text_to_speech_prompt").
    - "xtts_v2": XTTS v2 voice cloning (e.g., "voice_clone", "list_models").
    - "embeddings": Embedding generation (e.g., "embeddings", "get_status",
      "analysis_prompt").
    - "video_generation": Video creation (e.g., "generate", "get_status",
      "prompt").
    - "video_recognition": Video analysis (e.g., "recognize", "synopsis", "qa",
      "get_status", "prompt").
    - "wan2": WAN2 video service (e.g., "text_to_video", "image_to_video",
      "compress_video", "get_status").

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        service_name: Name of the GPU-AI service to route the request to. Must be
            one of: "llm", "audio", "xtts_v2", "embeddings", "video_generation",
            "video_recognition", "wan2".
        path: The sub-path within the service to call (e.g., "v1/models",
            "generate", "get_status/task-123"). Leading slashes are stripped
            automatically.
        method: HTTP method to use (default: "GET"). Supported: "GET", "POST",
            "PUT", "DELETE".
        payload: Optional JSON-serializable dictionary to send as the request body
            for POST and PUT requests. Ignored for GET and DELETE.

    Returns:
        Dict containing the JSON response from the proxied service endpoint.
        The structure varies by service and endpoint.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate a video from a text description using the GPU-AI video generation service.

    Creates a video by sending a text prompt to the GPU-AI API's video generation
    service (POST /api/v1/services/video_generation/proxy/{path}). The service
    interprets the prompt and produces a video matching the description.

    Video generation is typically an asynchronous operation -- the initial call
    may return a task_id. Use ai_video_get_status to poll for completion and
    retrieve the generated video URL or data.

    This tool always routes to the GPU-AI API regardless of tenant. Video
    generation is not available via external providers.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A text description of the video to generate. Be specific about
            the desired scene, motion, camera angle, style, and duration for
            best results (e.g., "A drone shot flying over a misty mountain
            range at sunrise, cinematic style, 5 seconds").
        path: API sub-path within the video_generation service (default:
            "generate"). Override this only if the GPU-AI API uses a different
            endpoint path.
        additional_params: Optional dictionary of additional video generation
            parameters to merge into the request payload. Common options may
            include:
            - duration (int): Video duration in seconds.
            - resolution (str): e.g., "1280x720", "1920x1080".
            - style (str): Visual style or artistic direction.
            - fps (int): Frames per second.
            - seed (int): Random seed for reproducibility.
            Keys depend on the GPU-AI API's video generation backend.

    Returns:
        Dict containing the video generation response, which typically includes:
        - task_id (str): Identifier for polling the generation status.
        - status (str): Current status (e.g., "pending", "processing").
        - video_url (str): URL of the generated video (if completed immediately).
        The exact structure depends on the GPU-AI API implementation.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Analyze and recognize content within a video using GPU-AI video recognition.

    Sends a video to the GPU-AI API's video recognition service
    (POST /api/v1/services/video_recognition/proxy/{path}) for automated
    analysis. The service can detect objects, scenes, actions, text, faces, and
    other visual elements depending on the recognition backend.

    Video recognition may be asynchronous -- check the response for a task_id
    and use ai_video_recognition_get_status to poll for results if needed.

    This tool always routes to the GPU-AI API regardless of tenant. For
    higher-level video analysis with natural language prompts, consider using
    ai_video_analysis_prompt instead.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        video_data: The video to analyze, provided either as:
            - A Base64-encoded string of the video file bytes.
            - A URL pointing to a publicly accessible video file.
            Supported formats depend on the backend but typically include mp4,
            avi, mov, and webm.
        path: API sub-path within the video_recognition service (default:
            "recognize"). Override this only if the GPU-AI API uses a different
            endpoint path.
        additional_params: Optional dictionary of additional recognition
            parameters to merge into the request payload. Common options may
            include:
            - tasks (list[str]): Specific recognition tasks (e.g., ["objects",
              "scenes", "actions", "text"]).
            - format (str): Desired output format.
            - max_frames (int): Maximum number of frames to analyze.
            - confidence_threshold (float): Minimum confidence score for results.
            Keys depend on the GPU-AI API's video recognition backend.

    Returns:
        Dict containing the video recognition response, which may include:
        - task_id (str): Identifier for polling if processing is asynchronous.
        - status (str): Current processing status.
        - results (dict): Recognition results with detected objects, scenes, etc.
        The exact structure depends on the GPU-AI API implementation.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Convert speech audio to text using the audio service or OpenRouter.

    Transcribes spoken audio into text. This is similar to
    ai_create_audio_transcription but routes through the GPU-AI audio service
    proxy (POST /api/v1/services/audio/proxy/speech_to_text) for the "global"
    tenant, or through OpenRouter's speech-to-text endpoint for non-global
    tenants.

    Use this tool for quick speech-to-text conversions. For more control over
    transcription parameters (response format, prompt guidance, etc.), use
    ai_create_audio_transcription instead.

    Provider routing:
    - "global" tenant: Uses the GPU-AI audio service via the proxy endpoint.
    - Other tenants: Uses OpenRouter's speech-to-text API (requires
      openrouter_api_key to be configured for the tenant).

    Supported audio formats: mp3, mp4, mpeg, mpga, m4a, wav, webm.

    Args:
        tenant_id: Tenant identifier. Use "global" for the GPU-AI audio service
            or any registered tenant ID for OpenRouter STT.
        audio_data: The audio file content encoded as a Base64 string. Encode the
            raw bytes of the audio file via base64.b64encode().
        filename: Filename with extension to help identify the audio format
            (default: "audio.mp3"). Examples: "recording.wav", "memo.m4a".
        model: Model identifier for transcription. If None, the provider's
            default model is used (e.g., "whisper-1" on GPU-AI, or the default
            STT model on OpenRouter).
        language: ISO-639-1 language code of the spoken audio (e.g., "en", "es",
            "de"). If None, the model auto-detects the language. Providing the
            correct language improves accuracy.

    Returns:
        Dict containing transcription results. Structure varies by provider:
        - For GPU-AI: The raw response from the audio service proxy.
        - For OpenRouter: The response from OpenRouter's STT endpoint.
        Common fields:
        - text (str): The transcribed text.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Convert text to spoken audio using GPU-AI or Eleven Labs.

    Synthesizes natural-sounding speech from text input. The audio is generated
    using either the GPU-AI audio service or Eleven Labs depending on the tenant
    configuration.

    Provider routing:
    - "global" tenant: Uses the GPU-AI audio service via the proxy endpoint
      (POST /api/v1/services/audio/proxy/text_to_speech). Voice and model
      selection depends on the GPU-AI backend.
    - Other tenants: Uses the Eleven Labs TTS API (requires elevenlabs_api_key).
      Returns MP3 audio encoded as Base64. If no voice_id is provided, defaults
      to Eleven Labs voice "21m00Tcm4TlvDq8ikWAM" (Rachel).

    For prompt-based TTS with more natural control over intonation and style,
    consider using ai_text_to_speech_prompt instead. For voice cloning with a
    reference audio sample, use ai_audio_voice_clone_xtts_v2.

    Args:
        tenant_id: Tenant identifier. Use "global" for the GPU-AI audio service
            or any registered tenant ID for Eleven Labs TTS.
        text: The text to convert to speech. Maximum length depends on the
            provider (Eleven Labs free tier: ~5000 characters per request).
        voice_id: Identifier for the voice to use. For Eleven Labs, this is a
            voice ID string (default: "21m00Tcm4TlvDq8ikWAM" / Rachel). For
            GPU-AI, the available voices depend on the backend configuration.
            Use None to select the provider's default voice.
        model: TTS model identifier. For GPU-AI, this selects the synthesis
            model. For Eleven Labs, this is set internally by the provider client.
            If None, the provider's default model is used.

    Returns:
        Dict containing:
        For Eleven Labs (non-global tenants):
        - success (bool): True if synthesis succeeded.
        - audio (str): Base64-encoded MP3 audio data. Decode with
          base64.b64decode() to get raw audio bytes.
        - format (str): "mp3"
        For GPU-AI (global tenant):
        - The raw response from the GPU-AI audio service proxy, which may include
          audio data in various formats depending on the backend.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """List available audio models on the GPU-AI audio service.

    Queries the GPU-AI API's audio service
    (GET /api/v1/services/audio/proxy/list_models) to retrieve the catalogue of
    available audio models. This includes models for speech-to-text (e.g.,
    Whisper variants), text-to-speech, and other audio processing tasks hosted
    on the GPU-AI backend.

    This tool always routes to the GPU-AI API regardless of tenant. For
    non-global tenants using OpenRouter (STT) or Eleven Labs (TTS), model
    availability is determined by those providers and not listed here.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
            Typically "global" since audio models are listed from the GPU-AI
            backend.

    Returns:
        Dict containing the audio model list from the GPU-AI API. Structure
        depends on the backend but typically includes:
        - models (list): Array of model objects with names, capabilities, and
          supported formats.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Clone a voice and synthesize speech using the XTTS v2 service.

    Uses the XTTS v2 (Coqui TTS) voice cloning service on the GPU-AI API
    (POST /api/v1/services/xtts_v2/proxy/voice_clone) to generate speech that
    mimics a previously registered voice. The voice_id must refer to a voice
    profile that has been pre-registered on the XTTS v2 backend with reference
    audio samples.

    XTTS v2 supports multi-language voice cloning with natural prosody. It is
    particularly useful when you need speech output that matches a specific
    person's voice characteristics rather than a generic TTS voice.

    This tool always routes to the GPU-AI API regardless of tenant. Voice
    cloning is not available via external providers through this server.

    Note: Voice profiles must be registered on the XTTS v2 backend before they
    can be used here. Use ai_xtts_v2_list_models to check available models and
    ai_proxy_service_request to manage voice profiles if supported.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        text: The text to synthesize as speech using the cloned voice. The XTTS
            v2 model supports multiple languages; the language is typically
            auto-detected from the text or can be set via the backend
            configuration.
        voice_id: Identifier of the pre-registered voice profile to clone. This
            must match a voice ID that has been set up on the XTTS v2 backend
            with reference audio samples.

    Returns:
        Dict containing the voice clone synthesis response from the GPU-AI API.
        The structure depends on the XTTS v2 backend but typically includes:
        - audio (str): Base64-encoded audio data of the synthesized speech.
        - format (str): Audio format (e.g., "wav").
        - sample_rate (int): Audio sample rate in Hz.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """List available XTTS v2 voice cloning models on the GPU-AI backend.

    Queries the GPU-AI API's XTTS v2 service
    (GET /api/v1/services/xtts_v2/proxy/list_models) to retrieve the catalogue
    of available voice cloning models. XTTS v2 (Coqui TTS) models support
    multi-language voice cloning and text-to-speech synthesis.

    Use this tool to discover which models are available before calling
    ai_audio_voice_clone_xtts_v2.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
            Typically "global" since XTTS v2 models are hosted on the GPU-AI
            backend.

    Returns:
        Dict containing the XTTS v2 model list from the GPU-AI API. Structure
        depends on the backend but typically includes:
        - models (list): Array of model objects with names, supported languages,
          and capabilities.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Get the status of an asynchronous embeddings generation task.

    Queries the GPU-AI API's embeddings service
    (GET /api/v1/services/embeddings/proxy/get_status[/{task_id}]) to check the
    progress and result of a previously submitted embeddings task. Some embedding
    operations (e.g., batch embedding of large datasets) run asynchronously and
    return a task_id that can be polled with this tool.

    If no task_id is provided, returns the status of all recent embeddings tasks
    for the tenant.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        task_id: The unique identifier of the embeddings task to check. This is
            returned by asynchronous embedding operations. If None, returns the
            status overview of all recent tasks.

    Returns:
        Dict containing the task status from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - task_id (str): The task identifier.
        - status (str): Current status (e.g., "pending", "processing",
          "completed", "failed").
        - progress (float): Completion percentage (0.0-1.0).
        - result (dict): The embedding results (when status is "completed").
        - error (str): Error details (when status is "failed").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Get the status of an asynchronous video generation task.

    Queries the GPU-AI API's video generation service
    (GET /api/v1/services/video_generation/proxy/get_status[/{task_id}]) to check
    the progress and result of a previously submitted video generation request.
    Video generation is typically a long-running operation; use this tool to poll
    for completion after calling ai_generate_video or ai_video_generation_prompt.

    If no task_id is provided, returns the status of all recent video generation
    tasks for the tenant.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        task_id: The unique identifier of the video generation task to check.
            This is returned by ai_generate_video or ai_video_generation_prompt.
            If None, returns the status overview of all recent tasks.

    Returns:
        Dict containing the task status from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - task_id (str): The task identifier.
        - status (str): Current status (e.g., "pending", "processing",
          "completed", "failed").
        - progress (float): Completion percentage (0.0-1.0).
        - video_url (str): URL to download the generated video (when completed).
        - error (str): Error details (when status is "failed").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate a textual synopsis summarizing the content of a video.

    Sends a video to the GPU-AI API's video recognition service
    (POST /api/v1/services/video_recognition/proxy/synopsis) to produce a
    human-readable summary of what happens in the video. The synopsis covers
    key scenes, actions, objects, and narrative flow.

    This is useful for cataloguing video content, generating video descriptions,
    accessibility annotations, or quick content review without watching the
    entire video.

    For asking specific questions about video content, use ai_video_qa instead.
    For more flexible analysis with custom prompts, use ai_video_analysis_prompt.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        video_data: The video to summarize, provided either as:
            - A Base64-encoded string of the video file bytes.
            - A URL pointing to a publicly accessible video file.
            Supported formats typically include mp4, avi, mov, and webm.

    Returns:
        Dict containing the synopsis response from the GPU-AI API. Structure
        depends on the backend but typically includes:
        - synopsis (str): A text summary describing the video content.
        - duration (float): Video duration in seconds.
        - key_scenes (list): Descriptions of notable scenes or moments.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Answer a specific question about the content of a video.

    Sends a video along with a natural language question to the GPU-AI API's
    video recognition service (POST /api/v1/services/video_recognition/proxy/qa).
    The model watches the video and generates an answer to the question based on
    the visual and (if available) audio content.

    This is useful for targeted video understanding tasks such as "What color is
    the car?", "How many people are in the room?", or "What happens after the
    door opens?".

    For a general summary of video content, use ai_video_synopsis instead.
    For open-ended analysis with custom prompts, use ai_video_analysis_prompt.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        video_data: The video to analyze, provided either as:
            - A Base64-encoded string of the video file bytes.
            - A URL pointing to a publicly accessible video file.
            Supported formats typically include mp4, avi, mov, and webm.
        question: A natural language question about the video content. Be specific
            and clear for best results (e.g., "What is the person holding in their
            right hand?" rather than "What do you see?").

    Returns:
        Dict containing the QA response from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - answer (str): The model's answer to the question.
        - confidence (float): Confidence score for the answer (0.0-1.0).
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Get the status of an asynchronous video recognition task.

    Queries the GPU-AI API's video recognition service
    (GET /api/v1/services/video_recognition/proxy/get_status[/{task_id}]) to
    check the progress and result of a previously submitted video recognition,
    synopsis, QA, or analysis request. Video recognition tasks may run
    asynchronously for long or complex videos.

    If no task_id is provided, returns the status of all recent video recognition
    tasks for the tenant.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        task_id: The unique identifier of the video recognition task to check.
            This is returned by ai_recognize_video, ai_video_synopsis,
            ai_video_qa, or ai_video_analysis_prompt when the operation runs
            asynchronously. If None, returns the status overview of all recent
            tasks.

    Returns:
        Dict containing the task status from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - task_id (str): The task identifier.
        - status (str): Current status (e.g., "pending", "processing",
          "completed", "failed").
        - progress (float): Completion percentage (0.0-1.0).
        - result (dict): The recognition results (when status is "completed").
        - error (str): Error details (when status is "failed").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate a video from a text description using the WAN2 video service.

    Uses the WAN2 video generation backend on the GPU-AI API
    (POST /api/v1/services/wan2/proxy/text_to_video) to create a video from a
    text prompt. WAN2 is a specialized video generation service that may offer
    different styles, resolutions, or generation approaches compared to the
    standard ai_generate_video tool.

    Video generation is typically asynchronous. The response includes a task_id
    that can be polled with ai_wan2_get_status to check progress and retrieve
    the final video.

    This tool always routes to the GPU-AI API regardless of tenant.

    For generating video from an existing image, use ai_wan2_image_to_video
    instead.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A text description of the video to generate. Be specific about
            subject, action, style, camera movement, and duration for best
            results (e.g., "A cat playing with a ball of yarn in a sunny living
            room, slow motion, 4 seconds").
        additional_params: Optional dictionary of additional WAN2 generation
            parameters to merge into the request payload. Common options may
            include:
            - duration (int): Video length in seconds.
            - resolution (str): Output resolution (e.g., "720p", "1080p").
            - style (str): Artistic style preset.
            - negative_prompt (str): Things to avoid in the generated video.
            - seed (int): Random seed for reproducibility.
            - num_frames (int): Number of frames to generate.
            Keys depend on the WAN2 backend configuration.

    Returns:
        Dict containing the WAN2 generation response. Structure depends on the
        backend but typically includes:
        - task_id (str): Identifier for polling status with ai_wan2_get_status.
        - status (str): Initial status (e.g., "pending", "processing").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate a video from a static image using the WAN2 video service.

    Uses the WAN2 image-to-video backend on the GPU-AI API
    (POST /api/v1/services/wan2/proxy/image_to_video) to animate a static image
    into a short video. The service applies motion, camera effects, and scene
    dynamics to bring the image to life.

    This is useful for creating animated content from photographs, illustrations,
    or AI-generated images. The motion is inferred from the image content and
    any additional parameters provided.

    Video generation is typically asynchronous. The response includes a task_id
    that can be polled with ai_wan2_get_status to check progress and retrieve
    the final video.

    This tool always routes to the GPU-AI API regardless of tenant.

    For generating video from text descriptions instead, use
    ai_wan2_text_to_video.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        image_data: The source image, provided either as:
            - A Base64-encoded string of the image file bytes.
            - A URL pointing to a publicly accessible image file.
            Supported formats typically include JPEG, PNG, and WebP.
        additional_params: Optional dictionary of additional WAN2 generation
            parameters to merge into the request payload. Common options may
            include:
            - prompt (str): Text description to guide the animation direction.
            - duration (int): Video length in seconds.
            - motion_strength (float): How much motion to apply (0.0-1.0).
            - resolution (str): Output resolution.
            - seed (int): Random seed for reproducibility.
            Keys depend on the WAN2 backend configuration.

    Returns:
        Dict containing the WAN2 generation response. Structure depends on the
        backend but typically includes:
        - task_id (str): Identifier for polling status with ai_wan2_get_status.
        - status (str): Initial status (e.g., "pending", "processing").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Compress a video to reduce file size using the WAN2 service.

    Uses the WAN2 video compression backend on the GPU-AI API
    (POST /api/v1/services/wan2/proxy/compress_video) to reduce a video's file
    size while attempting to maintain visual quality. Useful for optimizing
    videos for web delivery, reducing storage costs, or meeting file size limits.

    Compression is typically asynchronous. The response may include a task_id
    that can be polled with ai_wan2_get_status to check progress and retrieve
    the compressed video.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        video_data: The video to compress, provided either as:
            - A Base64-encoded string of the video file bytes.
            - A URL pointing to a publicly accessible video file.
            Supported formats typically include mp4, avi, mov, and webm.
        additional_params: Optional dictionary of additional compression
            parameters to merge into the request payload. Common options may
            include:
            - target_size_mb (float): Target file size in megabytes.
            - quality (str): Quality preset (e.g., "low", "medium", "high").
            - resolution (str): Target resolution (e.g., "720p", "1080p").
            - bitrate (str): Target bitrate (e.g., "2M", "5M").
            - codec (str): Video codec (e.g., "h264", "h265").
            - fps (int): Target frames per second.
            Keys depend on the WAN2 backend configuration.

    Returns:
        Dict containing the WAN2 compression response. Structure depends on
        the backend but typically includes:
        - task_id (str): Identifier for polling status with ai_wan2_get_status.
        - status (str): Current status (e.g., "pending", "processing",
          "completed").
        - video_url (str): URL to download the compressed video (when completed).
        - original_size (int): Original file size in bytes.
        - compressed_size (int): Compressed file size in bytes.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Get the status of an asynchronous WAN2 task (video generation or compression).

    Queries the GPU-AI API's WAN2 service
    (GET /api/v1/services/wan2/proxy/get_status[/{task_id}]) to check the
    progress and result of a previously submitted WAN2 operation. This covers
    all WAN2 tasks including text-to-video, image-to-video, and video
    compression.

    Poll this endpoint periodically after submitting a WAN2 task via
    ai_wan2_text_to_video, ai_wan2_image_to_video, or ai_wan2_compress_video.

    If no task_id is provided, returns the status of all recent WAN2 tasks for
    the tenant.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        task_id: The unique identifier of the WAN2 task to check. This is
            returned by ai_wan2_text_to_video, ai_wan2_image_to_video, or
            ai_wan2_compress_video. If None, returns the status overview of all
            recent WAN2 tasks.

    Returns:
        Dict containing the task status from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - task_id (str): The task identifier.
        - status (str): Current status (e.g., "pending", "processing",
          "completed", "failed").
        - progress (float): Completion percentage (0.0-1.0).
        - video_url (str): URL to download the result (when status is
          "completed").
        - error (str): Error details (when status is "failed").
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate text-to-speech audio using a natural language prompt for control.

    Sends a natural language prompt to the GPU-AI API's audio service
    (POST /api/v1/services/audio/proxy/text_to_speech_prompt) to generate
    speech with prompt-based control over delivery. Unlike ai_audio_text_to_speech
    which takes plain text and a voice ID, this tool uses a descriptive prompt
    that can specify intonation, emotion, pacing, accent, and other speech
    characteristics in natural language.

    Example prompts:
    - "Say 'Welcome to the show!' in an excited, energetic voice"
    - "Read this paragraph slowly and calmly with a British accent: ..."
    - "Whisper the following text mysteriously: ..."

    This tool always routes to the GPU-AI API regardless of tenant. It is not
    available via Eleven Labs or other external TTS providers.

    For standard text-to-speech with voice selection, use ai_audio_text_to_speech.
    For voice cloning, use ai_audio_voice_clone_xtts_v2.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A natural language prompt describing both the text to speak and
            the desired speech characteristics. Include instructions for tone,
            emotion, speed, accent, or style alongside the text content.

    Returns:
        Dict containing the TTS response from the GPU-AI API. Structure depends
        on the backend but typically includes:
        - audio (str): Base64-encoded audio data.
        - format (str): Audio format (e.g., "wav", "mp3").
        - sample_rate (int): Audio sample rate in Hz.
        - duration (float): Audio duration in seconds.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Generate a video using a natural language prompt with automatic parameter selection.

    Sends a natural language prompt to the GPU-AI API's video generation service
    (POST /api/v1/services/video_generation/proxy/prompt) to generate a video.
    Unlike ai_generate_video which requires explicit parameters, this prompt-based
    tool allows the backend to interpret the prompt and automatically determine
    optimal settings (resolution, duration, style, etc.).

    This is the simplest way to generate a video -- just describe what you want
    in plain language and let the backend handle the technical details.

    Video generation is typically asynchronous. Use ai_video_get_status to poll
    for the task's completion.

    This tool always routes to the GPU-AI API regardless of tenant.

    For more control over generation parameters, use ai_generate_video instead.
    For WAN2-specific video generation, use ai_wan2_text_to_video.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A natural language description of the desired video. Be specific
            about the scene, action, camera work, style, duration, and mood.
            Example: "Create a 5-second cinematic shot of waves crashing on a
            rocky coastline at sunset with dramatic lighting."

    Returns:
        Dict containing the video generation response from the GPU-AI API.
        Structure depends on the backend but typically includes:
        - task_id (str): Identifier for polling status with ai_video_get_status.
        - status (str): Initial status (e.g., "pending", "processing").
        - video_url (str): URL of the video (if completed immediately).
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Analyze a video using a free-form natural language prompt.

    Sends a video along with a custom analysis prompt to the GPU-AI API's video
    recognition service (POST /api/v1/services/video_recognition/proxy/prompt).
    This is the most flexible video analysis tool, allowing you to specify
    exactly what you want to extract or understand about the video content.

    Unlike ai_video_synopsis (which produces a fixed summary format) or
    ai_video_qa (which answers a single question), this tool lets you provide
    arbitrary instructions for how to analyze the video. Examples:
    - "List all text visible in this video with timestamps."
    - "Describe the emotional arc of the characters throughout the video."
    - "Identify all brand logos that appear and note when they're visible."
    - "Count the number of scene transitions and describe each one."

    Video analysis may run asynchronously for long videos. Check the response
    for a task_id and use ai_video_recognition_get_status to poll if needed.

    This tool always routes to the GPU-AI API regardless of tenant.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        video_data: The video to analyze, provided either as:
            - A Base64-encoded string of the video file bytes.
            - A URL pointing to a publicly accessible video file.
            Supported formats typically include mp4, avi, mov, and webm.
        prompt: A natural language instruction describing what to analyze in the
            video and how to format the results. Be specific about what aspects
            of the video you want examined.

    Returns:
        Dict containing the analysis response from the GPU-AI API. Structure
        depends on the backend and the analysis requested, but typically includes:
        - analysis (str): The model's analysis output based on the prompt.
        - task_id (str): Identifier for polling if processing is asynchronous.
        On failure:
        - success (bool): False
        - error (str): Error description.
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
    """Perform embeddings-based analysis using a natural language prompt.

    Sends a natural language prompt to the GPU-AI API's embeddings service
    (POST /api/v1/services/embeddings/proxy/analysis_prompt) for prompt-guided
    embedding analysis. Unlike ai_create_embeddings which produces raw vectors,
    this tool lets the backend interpret the prompt and perform higher-level
    analysis tasks such as semantic similarity comparisons, clustering
    descriptions, or text classification using embeddings under the hood.

    Example prompts:
    - "Compare the semantic similarity between these two paragraphs: ..."
    - "Classify the following text into one of these categories: ..."
    - "Find the most relevant passages in the following document for the
       query 'machine learning applications'."

    This tool always routes to the GPU-AI API regardless of tenant.

    For raw embedding vector generation, use ai_create_embeddings instead.
    For checking the status of asynchronous embedding tasks, use
    ai_embeddings_get_status.

    Args:
        tenant_id: Tenant identifier used to look up the GPU-AI API connection.
        prompt: A natural language prompt describing the embeddings-based
            analysis to perform. Include the text(s) to analyze and the type of
            analysis desired.

    Returns:
        Dict containing the analysis response from the GPU-AI API. Structure
        depends on the backend and the analysis requested, but typically
        includes:
        - analysis (str): The model's analysis output based on the prompt.
        - results (dict): Structured analysis results (similarity scores,
          classifications, etc.).
        On failure:
        - success (bool): False
        - error (str): Error description.
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
