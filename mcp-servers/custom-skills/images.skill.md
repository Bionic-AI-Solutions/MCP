---
name: images
description: Generate, upscale, and process images using the GenImage MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<generate|upscale|remove-bg> [args] [--tenant <id>]"
---

# GenImage MCP Server

Server: `genimage` at `genimage/mcp` (stateful transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `gi_register_tenant` | `tenant_id, api_url, api_key` | Register a new tenant with API credentials |
| `gi_generate_image` | `tenant_id, prompt, negative_prompt?, width?, height?, steps?, cfg_scale?, seed?, model?` | Generate an image from a text prompt |
| `gi_upscale_image` | `tenant_id, image_data (base64), scale_factor, model?` | AI upscale an existing image |
| `gi_remove_background` | `tenant_id, image_data (base64)` | Remove background from an image |

### Parameter Defaults

- `width`: 512, `height`: 512, `steps`: 20
- `image_data`: base64-encoded image bytes

## Usage Examples

Generate a simple image:
```bash
~/.claude/bin/mcp-rpc call genimage gi_generate_image '{"tenant_id": "base", "prompt": "a red fox sitting in a snowy forest", "width": 512, "height": 512, "steps": 20}'
```

Generate with negative prompt and custom size:
```bash
~/.claude/bin/mcp-rpc call genimage gi_generate_image '{"tenant_id": "base", "prompt": "professional headshot portrait", "negative_prompt": "blurry, low quality", "width": 768, "height": 768, "steps": 30}'
```

Remove background from an image (pass base64 data):
```bash
~/.claude/bin/mcp-rpc call genimage gi_remove_background '{"tenant_id": "base", "image_data": "<base64-encoded-image>"}'
```

## Notes

- Image generation can take 10-60 seconds depending on steps and resolution.
- The `image_data` parameter for upscale and remove-bg must be base64-encoded.
- Higher `steps` values produce better quality but take longer.
- Use `cfg_scale` to control how closely the image follows the prompt (higher = stricter).
