# AI MCP Server - Usage Guide

## Overview

The AI MCP Server provides comprehensive AI capabilities including LLM chat/completions, audio processing (speech-to-text, text-to-speech), embeddings, video generation and recognition, and more. It supports multi-tenant configurations with provider routing:

- **"global" tenant** → Uses GPU-AI API at `192.168.0.10:8000`
- **Other tenants** → Routes to:
  - LLM/STT → OpenRouter (requires `openrouter_api_key`)
  - TTS → Eleven Labs (requires `elevenlabs_api_key`)
  - Embeddings → OpenAI (requires `openai_api_key`)

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "ai-mcp-server-remote": {
      "url": "https://mcp.baisoln.com/ai-mcp-server/mcp",
      "description": "AI MCP Server - GPU-AI tools (OpenAI-compatible) - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-ai-mcp-server

# Server will be available at http://localhost:8009
```

## Tenant Registration

Before using most tools, you need to register a tenant. For the "global" tenant, you can use the GPU-AI API directly. For other tenants, provide the appropriate API keys.

### Register Global Tenant (GPU-AI API)
```json
{
  "tenant_id": "global",
  "api_base_url": "http://192.168.0.10:8000",
  "api_key": "optional-api-key"
}
```

### Register Custom Tenant (Multi-Provider)
```json
{
  "tenant_id": "my-tenant",
  "openrouter_api_key": "sk-or-v1-...",
  "elevenlabs_api_key": "...",
  "openai_api_key": "sk-...",
  "timeout": 300,
  "max_concurrent_requests": 10
}
```

## Available Tools

The AI MCP Server provides 31 tools organized by category:

### Tenant Management

#### 1. `ai_register_tenant` - Register Tenant Configuration

Register a new tenant with provider-specific API keys.

**Parameters:**
- `tenant_id` (string, required): Unique identifier (use "global" for GPU-AI API)
- `api_base_url` (string, optional): GPU-AI API base URL (default: http://192.168.0.10:8000)
- `api_key` (string, optional): GPU-AI API key
- `openrouter_api_key` (string, optional): OpenRouter API key for LLM/STT
- `elevenlabs_api_key` (string, optional): Eleven Labs API key for TTS
- `openai_api_key` (string, optional): OpenAI API key for embeddings
- `timeout` (integer, optional): Request timeout in seconds (default: 300)
- `max_concurrent_requests` (integer, optional): Max concurrent requests (default: 10)

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "openrouter_api_key": "sk-or-v1-...",
  "elevenlabs_api_key": "...",
  "openai_api_key": "sk-..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tenant 'my-tenant' registered successfully with providers: OpenRouter (LLM/STT), Eleven Labs (TTS), OpenAI (Embeddings)"
}
```

### LLM Tools

#### 2. `ai_list_models` - List Available Models

List available AI models for a tenant.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier

**Example:**
```json
{
  "tenant_id": "global"
}
```

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "model-name",
      "object": "model",
      "created": 1234567890,
      "owned_by": "organization"
    }
  ]
}
```

#### 3. `ai_chat_completion` - Chat Completions

Create a chat completion using GPU-AI or OpenRouter.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `model` (string, required): Model name to use
- `messages` (array, required): List of message objects with 'role' and 'content'
- `max_tokens` (integer, optional): Maximum tokens to generate
- `temperature` (float, optional): Sampling temperature (0-2)
- `top_p` (float, optional): Nucleus sampling parameter
- `stream` (boolean, optional): Whether to stream the response

**Example:**
```json
{
  "tenant_id": "global",
  "model": "qwen2.5-7b-instruct",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "max_tokens": 100,
  "temperature": 0.7
}
```

**Response:**
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "qwen2.5-7b-instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ]
}
```

#### 4. `ai_text_completion` - Text Completions

Create a text completion using GPU-AI or OpenRouter.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `model` (string, required): Model name to use
- `prompt` (string, required): Text prompt to complete
- `max_tokens` (integer, optional): Maximum tokens to generate
- `temperature` (float, optional): Sampling temperature (0-2)
- `top_p` (float, optional): Nucleus sampling parameter
- `stream` (boolean, optional): Whether to stream the response

**Example:**
```json
{
  "tenant_id": "global",
  "model": "qwen2.5-7b-instruct",
  "prompt": "The capital of France is",
  "max_tokens": 10
}
```

**Response:**
```json
{
  "id": "cmpl-...",
  "object": "text_completion",
  "created": 1234567890,
  "model": "qwen2.5-7b-instruct",
  "choices": [
    {
      "text": " Paris.",
      "index": 0,
      "finish_reason": "stop"
    }
  ]
}
```

### Audio Tools

#### 5. `ai_audio_speech_to_text` - Speech to Text

Convert speech to text using GPU-AI audio service or OpenRouter.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `audio_data` (string, required): Base64-encoded audio file content
- `filename` (string, optional): Name of the audio file (default: "audio.mp3")
- `model` (string, optional): Model to use for transcription
- `language` (string, optional): Language of the audio (ISO-639-1 format)

**Example:**
```json
{
  "tenant_id": "global",
  "audio_data": "base64-encoded-audio-content...",
  "filename": "recording.mp3",
  "language": "en"
}
```

**Response:**
```json
{
  "text": "Transcribed text from audio"
}
```

#### 6. `ai_audio_text_to_speech` - Text to Speech

Convert text to speech using GPU-AI audio service or Eleven Labs.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `text` (string, required): Text to convert to speech
- `voice_id` (string, optional): Voice ID to use
- `model` (string, optional): Model to use for TTS

**Example:**
```json
{
  "tenant_id": "global",
  "text": "Hello, this is a test.",
  "voice_id": "voice-123"
}
```

**Response:**
```json
{
  "success": true,
  "audio": "base64-encoded-audio-content...",
  "format": "mp3"
}
```

#### 7. `ai_audio_list_models` - List Audio Models

List available audio models for a tenant.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier

**Example:**
```json
{
  "tenant_id": "global"
}
```

#### 8. `ai_audio_voice_clone_xtts_v2` - Voice Clone (XTTS v2)

Clone voice using XTTS v2 service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `text` (string, required): Text to convert to speech
- `voice_id` (string, required): Voice ID to clone

**Example:**
```json
{
  "tenant_id": "global",
  "text": "Hello, this is a cloned voice.",
  "voice_id": "voice-123"
}
```

#### 9. `ai_xtts_v2_list_models` - List XTTS v2 Models

List available XTTS v2 models.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier

#### 10. `ai_create_audio_transcription` - Audio Transcription

Transcribe audio to text (OpenAI-compatible endpoint).

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `file_data` (string, required): Base64-encoded audio file
- `filename` (string, required): Name of the audio file
- `model` (string, optional): Model to use (default: "whisper-1")
- `language` (string, optional): Language of the audio
- `prompt` (string, optional): Optional text to guide the model
- `response_format` (string, optional): Format of the response
- `temperature` (float, optional): Sampling temperature (0-1)

#### 11. `ai_create_audio_translation` - Audio Translation

Translate audio to English text (OpenAI-compatible endpoint).

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `file_data` (string, required): Base64-encoded audio file
- `filename` (string, required): Name of the audio file
- `model` (string, optional): Model to use (default: "whisper-1")
- `prompt` (string, optional): Optional text to guide the model
- `response_format` (string, optional): Format of the response
- `temperature` (float, optional): Sampling temperature (0-1)

#### 12. `ai_text_to_speech_prompt` - Text to Speech from Prompt

Generate text-to-speech using a natural language prompt.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Natural language prompt describing the desired speech output

**Example:**
```json
{
  "tenant_id": "global",
  "prompt": "Generate a friendly greeting in a warm, professional voice"
}
```

### Embeddings Tools

#### 13. `ai_create_embeddings` - Create Embeddings

Create embeddings for input text using GPU-AI or OpenAI.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `model` (string, required): Model name to use for embeddings
- `input_text` (string, required): Text to create embeddings for
- `encoding_format` (string, optional): Format for the embeddings (e.g., "float", "base64")

**Example:**
```json
{
  "tenant_id": "global",
  "model": "text-embedding-ada-002",
  "input_text": "Hello, world!"
}
```

**Response:**
```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.1, 0.2, 0.3, ...],
      "index": 0
    }
  ],
  "model": "text-embedding-ada-002",
  "usage": {
    "prompt_tokens": 3,
    "total_tokens": 3
  }
}
```

#### 14. `ai_embeddings_get_status` - Get Embeddings Status

Get status of embeddings generation task.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `task_id` (string, optional): Task ID to check status for

**Example:**
```json
{
  "tenant_id": "global",
  "task_id": "task-123"
}
```

#### 15. `ai_embeddings_analysis_prompt` - Embeddings Analysis from Prompt

Generate embeddings analysis using a natural language prompt.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Natural language prompt describing the embeddings analysis needed

### Video Tools

#### 16. `ai_generate_video` - Generate Video from Text

Generate a video from a text prompt using GPU-AI video generation service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Text description of the video to generate
- `path` (string, optional): API path for video generation (default: "generate")
- `additional_params` (object, optional): Additional parameters (duration, resolution, style, etc.)

**Example:**
```json
{
  "tenant_id": "global",
  "prompt": "A beautiful sunset over the ocean",
  "additional_params": {
    "duration": 10,
    "resolution": "1920x1080"
  }
}
```

**Response:**
```json
{
  "success": true,
  "video_url": "https://...",
  "task_id": "task-123"
}
```

#### 17. `ai_video_get_status` - Get Video Generation Status

Get status of video generation task.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `task_id` (string, optional): Task ID to check status for

#### 18. `ai_recognize_video` - Recognize Video Content

Recognize and analyze video content using GPU-AI video recognition service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `video_data` (string, required): Base64-encoded video content or URL to video
- `path` (string, optional): API path for video recognition (default: "recognize")
- `additional_params` (object, optional): Additional parameters (tasks, format, etc.)

**Example:**
```json
{
  "tenant_id": "global",
  "video_data": "base64-encoded-video...",
  "additional_params": {
    "tasks": ["object_detection", "scene_analysis"]
  }
}
```

#### 19. `ai_video_synopsis` - Generate Video Synopsis

Generate a synopsis of video content.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `video_data` (string, required): Base64-encoded video content or URL to video

**Example:**
```json
{
  "tenant_id": "global",
  "video_data": "base64-encoded-video..."
}
```

**Response:**
```json
{
  "synopsis": "This video shows a beautiful sunset over the ocean with birds flying in the background..."
}
```

#### 20. `ai_video_qa` - Video Question Answering

Answer questions about video content.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `video_data` (string, required): Base64-encoded video content or URL to video
- `question` (string, required): Question to ask about the video

**Example:**
```json
{
  "tenant_id": "global",
  "video_data": "base64-encoded-video...",
  "question": "What is the main subject of this video?"
}
```

**Response:**
```json
{
  "answer": "The main subject is a sunset over the ocean."
}
```

#### 21. `ai_video_recognition_get_status` - Get Video Recognition Status

Get status of video recognition task.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `task_id` (string, optional): Task ID to check status for

#### 22. `ai_video_generation_prompt` - Video Generation from Prompt

Generate video using a natural language prompt.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Natural language prompt describing the desired video

**Example:**
```json
{
  "tenant_id": "global",
  "prompt": "Create a video of a cat playing with a ball of yarn in slow motion"
}
```

#### 23. `ai_video_analysis_prompt` - Video Analysis from Prompt

Analyze video using a natural language prompt.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `video_data` (string, required): Base64-encoded video content or URL to video
- `prompt` (string, required): Natural language prompt describing what to analyze

**Example:**
```json
{
  "tenant_id": "global",
  "video_data": "base64-encoded-video...",
  "prompt": "Analyze the emotions and activities of people in this video"
}
```

### WAN2 Tools

#### 24. `ai_wan2_text_to_video` - WAN2 Text to Video

Generate video from text using WAN2 service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Text description of the video to generate
- `additional_params` (object, optional): Additional parameters for video generation

**Example:**
```json
{
  "tenant_id": "global",
  "prompt": "A cat walking on the moon",
  "additional_params": {
    "duration": 5,
    "fps": 24
  }
}
```

#### 25. `ai_wan2_image_to_video` - WAN2 Image to Video

Generate video from image using WAN2 service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `image_data` (string, required): Base64-encoded image content or URL to image
- `additional_params` (object, optional): Additional parameters for video generation

**Example:**
```json
{
  "tenant_id": "global",
  "image_data": "base64-encoded-image...",
  "additional_params": {
    "motion": "zoom_in",
    "duration": 3
  }
}
```

#### 26. `ai_wan2_compress_video` - WAN2 Compress Video

Compress video using WAN2 service.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `video_data` (string, required): Base64-encoded video content or URL to video
- `additional_params` (object, optional): Additional parameters for compression

**Example:**
```json
{
  "tenant_id": "global",
  "video_data": "base64-encoded-video...",
  "additional_params": {
    "quality": "medium",
    "format": "mp4"
  }
}
```

#### 27. `ai_wan2_get_status` - Get WAN2 Status

Get status of WAN2 task.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `task_id` (string, optional): Task ID to check status for

### Other Tools

#### 28. `ai_create_image` - Generate Image

Generate an image from a text prompt (OpenAI-compatible endpoint).

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `prompt` (string, required): Text description of the image to generate
- `model` (string, optional): Model to use for image generation
- `n` (integer, optional): Number of images to generate (1-10, default: 1)
- `size` (string, optional): Size of the generated image (default: "1024x1024")
- `quality` (string, optional): Quality of the image (standard, hd)
- `response_format` (string, optional): Format of the response (url, b64_json)
- `style` (string, optional): Style of the image (vivid, natural)
- `user` (string, optional): Unique identifier for the end user

#### 29. `ai_create_moderation` - Content Moderation

Classify if text violates content policy (OpenAI-compatible endpoint).

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `input_text` (string, required): Text to classify
- `model` (string, optional): Model to use for moderation

**Example:**
```json
{
  "tenant_id": "global",
  "input_text": "This is a test message"
}
```

**Response:**
```json
{
  "id": "modr-...",
  "model": "text-moderation-latest",
  "results": [
    {
      "flagged": false,
      "categories": {},
      "category_scores": {}
    }
  ]
}
```

#### 30. `ai_get_mcp_tools` - Get MCP Tools

Get additional MCP tools from the GPU-AI API server at `/mcp/tools/tools`.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier

#### 31. `ai_proxy_service_request` - Proxy Service Request

Proxy a request to any GPU-AI service endpoint.

**Parameters:**
- `tenant_id` (string, required): Tenant identifier
- `service_name` (string, required): Service to proxy to (llm, audio, xtts_v2, embeddings, video_generation, video_recognition, wan2)
- `path` (string, required): Path to proxy to (e.g., "v1/models", "embeddings", "v1/chat/completions")
- `method` (string, optional): HTTP method (GET, POST, PUT, DELETE, default: "GET")
- `payload` (object, optional): JSON payload for POST/PUT requests

**Example:**
```json
{
  "tenant_id": "global",
  "service_name": "llm",
  "path": "v1/models",
  "method": "GET"
}
```

**Example (POST):**
```json
{
  "tenant_id": "global",
  "service_name": "embeddings",
  "path": "embeddings",
  "method": "POST",
  "payload": {
    "texts": ["Hello world"],
    "normalize": true
  }
}
```

## Resources

Access server information as a resource:

- `ai://{tenant_id}/info` - Get information about a tenant configuration

## Example Workflow

### Using Global Tenant (GPU-AI API)

```python
# Register global tenant
ai_register_tenant(
    tenant_id="global",
    api_base_url="http://192.168.0.10:8000"
)

# List available models
models = ai_list_models(tenant_id="global")

# Create chat completion
response = ai_chat_completion(
    tenant_id="global",
    model="qwen2.5-7b-instruct",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Generate embeddings
embeddings = ai_create_embeddings(
    tenant_id="global",
    model="text-embedding-ada-002",
    input_text="Hello, world!"
)
```

### Using Custom Tenant (Multi-Provider)

```python
# Register custom tenant with provider API keys
ai_register_tenant(
    tenant_id="my-tenant",
    openrouter_api_key="sk-or-v1-...",
    elevenlabs_api_key="...",
    openai_api_key="sk-..."
)

# LLM requests go to OpenRouter
response = ai_chat_completion(
    tenant_id="my-tenant",
    model="openai/gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)

# TTS requests go to Eleven Labs
audio = ai_audio_text_to_speech(
    tenant_id="my-tenant",
    text="Hello, this is a test."
)

# Embeddings go to OpenAI
embeddings = ai_create_embeddings(
    tenant_id="my-tenant",
    model="text-embedding-ada-002",
    input_text="Hello, world!"
)
```

### Video Generation Workflow

```python
# Generate video from text
result = ai_generate_video(
    tenant_id="global",
    prompt="A beautiful sunset over the ocean",
    additional_params={
        "duration": 10,
        "resolution": "1920x1080"
    }
)

# Check status
status = ai_video_get_status(
    tenant_id="global",
    task_id=result["task_id"]
)

# Analyze video
analysis = ai_recognize_video(
    tenant_id="global",
    video_data="base64-encoded-video...",
    additional_params={
        "tasks": ["object_detection", "scene_analysis"]
    }
)
```

## Multi-Tenant Provider Routing

The AI MCP Server automatically routes requests based on tenant configuration:

| Service Type | Global Tenant | Other Tenants |
|-------------|---------------|---------------|
| **LLM** (Chat/Text Completions) | GPU-AI API | OpenRouter |
| **STT** (Speech-to-Text) | GPU-AI API | OpenRouter |
| **TTS** (Text-to-Speech) | GPU-AI API | Eleven Labs |
| **Embeddings** | GPU-AI API | OpenAI |
| **Video** | GPU-AI API | GPU-AI API |
| **Audio** | GPU-AI API | GPU-AI API |
| **WAN2** | GPU-AI API | GPU-AI API |

## Notes

- **Tenant Registration**: Most tools require a registered tenant. Use `ai_register_tenant` first.
- **Provider Routing**: For non-global tenants, ensure you provide the appropriate API keys for the services you want to use.
- **Base64 Encoding**: Audio and video data must be base64-encoded when passed as strings.
- **Async Operations**: Video generation and some other operations are async and return task IDs. Use status check tools to monitor progress.
- **Error Handling**: All tools return a `success` field and `error` field for error cases.
- **Concurrency Control**: Each tenant has configurable max concurrent requests (default: 10).
- **Timeout**: Request timeout is configurable per tenant (default: 300 seconds).

## Service Endpoints

The server proxies requests to GPU-AI services via:
- `/api/v1/services/{service_name}/proxy/{path}`

Available services:
- `llm` - Language model services
- `audio` - Audio processing
- `xtts_v2` - Text-to-speech v2
- `embeddings` - Embedding generation
- `video_generation` - Video generation
- `video_recognition` - Video recognition
- `wan2` - WAN2 video processing
