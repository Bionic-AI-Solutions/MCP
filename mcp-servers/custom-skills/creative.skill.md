---
name: creative
description: Creative & AI hub — routes to /images (GenImage), /media (FFmpeg), or /ai (GPU AI inference) based on your needs.
allowed-tools: Bash, TodoWrite
argument-hint: "<description of what you need>"
---

# Creative & AI Operations

This is a routing skill. Based on what you need, invoke the appropriate specialized skill:

## Available Creative Skills

| Skill | Server | When to Use |
|-------|--------|-------------|
| `/images` | GenImage (Runware) | AI image generation, upscaling, background removal |
| `/media` | FFmpeg | Video/audio conversion, trimming, merging, frame extraction |
| `/ai` | AI MCP Server | LLM chat, embeddings, TTS, speech-to-text, video generation |

## Routing Guide

Analyze `$ARGUMENTS` and invoke the matching skill:

- **Generate image, upscale, background removal, Runware** → Invoke `/images`
- **Convert video, trim, merge, extract audio, resize, FFmpeg** → Invoke `/media`
- **Chat completion, LLM, embeddings, text-to-speech, speech-to-text, video generation, Wan2** → Invoke `/ai`
- **Unclear** → Ask the user what kind of creative task they need

All three servers are multi-tenant. Default tenant: `base`.
