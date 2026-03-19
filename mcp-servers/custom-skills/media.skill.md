---
name: media
description: Convert, trim, merge, and inspect video/audio files via the FFmpeg MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<action> <input_path> [options] [--tenant <id>]"
---

# FFmpeg Media Processing MCP Server

Server: `ffmpeg` at `ffmpeg/mcp` (stateless transport)
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `ffmpeg_convert_video` | `tenant_id, input_path, output_format, output_path?, video_codec?, audio_codec?, video_bitrate?, audio_bitrate?, resolution?` | Convert video format |
| `ffmpeg_extract_audio` | `tenant_id, input_path, output_path?, audio_format, audio_bitrate?` | Extract audio from video |
| `ffmpeg_merge_videos` | `tenant_id, input_paths (list), output_path, transition?` | Merge multiple videos |
| `ffmpeg_add_subtitles` | `tenant_id, input_path, subtitle_path, output_path?, subtitle_language?` | Add subtitles to video |
| `ffmpeg_trim_video` | `tenant_id, input_path, start_time, end_time, output_path?` | Trim video to time range |
| `ffmpeg_get_video_info_tool` | `tenant_id, input_path` | Get video metadata (codec, duration, resolution) |
| `ffmpeg_resize_video` | `tenant_id, input_path, width, height, output_path?, maintain_aspect_ratio?` | Resize video dimensions |
| `ffmpeg_extract_frame` | `tenant_id, input_path, timestamp, output_path?, format?` | Extract a single frame as image |

## Usage Examples

Get video metadata:
```bash
~/.claude/bin/mcp-rpc call ffmpeg ffmpeg_get_video_info_tool '{"tenant_id": "base", "input_path": "/data/video.mp4"}'
```

Convert a video to WebM:
```bash
~/.claude/bin/mcp-rpc call ffmpeg ffmpeg_convert_video '{"tenant_id": "base", "input_path": "/data/video.mp4", "output_format": "webm", "resolution": "1280x720"}'
```

Trim a video clip:
```bash
~/.claude/bin/mcp-rpc call ffmpeg ffmpeg_trim_video '{"tenant_id": "base", "input_path": "/data/video.mp4", "start_time": "00:01:30", "end_time": "00:02:45"}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default connection.
- This server uses stateless transport -- no session management needed.
- File paths refer to locations accessible within the server container.
- When `output_path` is omitted, the server generates one automatically.
