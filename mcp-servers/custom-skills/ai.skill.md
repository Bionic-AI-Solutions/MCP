---
name: ai
description: Access LLM chat/completion, embeddings, audio, image, and video generation via the AI MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<chat|embed|transcribe|tts|generate-image|generate-video|...> [args] [--tenant <id>]"
---

# AI MCP Server

Server: `ai-mcp-server` at `ai-mcp-server/mcp` (stateless transport)
Multi-tenant. Default tenant: `base`. 31 tools organized by category.

## Tool Inventory

### LLM (4 tools)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_chat_completion` | `tenant_id, messages, model?, temperature?, max_tokens?, stream?, tools?` | Chat completion with message history |
| `ai_text_completion` | `tenant_id, prompt, model?, temperature?, max_tokens?` | Single-prompt text completion |
| `ai_list_models` | `tenant_id` | List available LLM models |
| `ai_create_moderation` | `tenant_id, input` | Content moderation check |

### Embeddings (3 tools)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_create_embeddings` | `tenant_id, input (list), model?, job_id?` | Create text embeddings |
| `ai_embeddings_get_status` | `tenant_id, job_id` | Check async embedding job status |
| `ai_embeddings_analysis_prompt` | `tenant_id, use_case` | Get prompt template for embeddings use case |

### Audio (8 tools)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_create_audio_transcription` | `tenant_id, audio_data, filename, model?, language?` | Transcribe audio file |
| `ai_create_audio_translation` | `tenant_id, audio_data, filename, model?` | Translate audio to English |
| `ai_audio_speech_to_text` | `tenant_id, audio_data, filename, language?` | Speech to text |
| `ai_audio_text_to_speech` | `tenant_id, text, voice?, model?, speed?` | Text to speech synthesis |
| `ai_audio_list_models` | `tenant_id` | List available audio models |
| `ai_audio_voice_clone_xtts_v2` | `tenant_id, text, speaker_audio, speaker_filename, language` | Clone a voice using XTTS v2 |
| `ai_xtts_v2_list_models` | `tenant_id` | List XTTS v2 models |
| `ai_text_to_speech_prompt` | `tenant_id, text, style?` | Generate optimized TTS prompt |

### Image (1 tool)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_create_image` | `tenant_id, prompt, model?, n?, size?, quality?` | Generate image from prompt |

### Video (11 tools)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_generate_video` | `tenant_id, prompt, model?, duration?, resolution?` | Generate video from text |
| `ai_recognize_video` | `tenant_id, video_data, filename, questions?` | Analyze video content |
| `ai_video_get_status` | `tenant_id, job_id` | Check video generation job status |
| `ai_video_synopsis` | `tenant_id, video_data, filename` | Generate video summary |
| `ai_video_qa` | `tenant_id, video_data, filename, question` | Ask questions about a video |
| `ai_video_recognition_get_status` | `tenant_id, job_id` | Check recognition job status |
| `ai_wan2_text_to_video` | `tenant_id, prompt, negative_prompt?, duration?` | Wan2 text-to-video generation |
| `ai_wan2_image_to_video` | `tenant_id, image_data, filename, prompt?` | Wan2 image-to-video generation |
| `ai_wan2_compress_video` | `tenant_id, video_data, filename, quality?` | Wan2 video compression |
| `ai_wan2_get_status` | `tenant_id, job_id` | Check Wan2 job status |
| `ai_video_generation_prompt` | `tenant_id, description, style?, duration?` | Generate optimized video prompt |
| `ai_video_analysis_prompt` | `tenant_id, analysis_type` | Get video analysis prompt template |

### Proxy (2 tools)

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `ai_get_mcp_tools` | `tenant_id` | Get MCP tools as AI function-call tools |
| `ai_proxy_service_request` | `tenant_id, method, endpoint, body?` | Raw HTTP proxy to backend API |

## Usage Examples

Chat completion:
```bash
~/.claude/bin/mcp-rpc call ai-mcp-server ai_chat_completion '{"tenant_id": "base", "messages": [{"role": "user", "content": "Explain quantum computing in 2 sentences"}], "temperature": 0.7}'
```

Create embeddings:
```bash
~/.claude/bin/mcp-rpc call ai-mcp-server ai_create_embeddings '{"tenant_id": "base", "input": ["hello world", "machine learning"]}'
```

Text to speech:
```bash
~/.claude/bin/mcp-rpc call ai-mcp-server ai_audio_text_to_speech '{"tenant_id": "base", "text": "Welcome to the AI platform", "voice": "alloy"}'
```

## Notes

- `audio_data` and `video_data` parameters must be base64-encoded.
- Video and embedding operations may be async -- use the `*_get_status` tools with the returned `job_id`.
- The `messages` param for chat completion is a list of `{"role": "...", "content": "..."}` objects.
- Use `ai_list_models` to discover available models before specifying a custom `model` parameter.
