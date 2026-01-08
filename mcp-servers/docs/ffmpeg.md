# FFmpeg MCP Server - Usage Guide

## Overview

The FFmpeg MCP server provides comprehensive video and audio processing capabilities using FFmpeg. It supports format conversion, editing, merging, and analysis operations.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "ffmpeg-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/ffmpeg/mcp",
      "description": "FFmpeg MCP Server - Video and audio processing"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-ffmpeg-server

# Server will be available at http://localhost:8004
```

## Available Tools

All tools accept video/audio data as base64-encoded strings and return processed media as base64-encoded output.

### 1. `ffmpeg_convert_video` - Convert Video Format

Convert video to a different format with optional quality/resolution adjustments.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `output_format` (optional): Output format - mp4, avi, mov, webm, etc. (default: `"mp4"`)
- `video_codec` (optional): Video codec - h264, vp9, etc. (auto-detected if not specified)
- `audio_codec` (optional): Audio codec - aac, mp3, etc. (auto-detected if not specified)
- `quality` (optional): Quality preset - low, medium, high, veryhigh
- `resolution` (optional): Output resolution (e.g., `"1920x1080"`, `"1280x720"`)
- `bitrate` (optional): Video bitrate (e.g., `"2M"`, `"5000k"`)
- `fps` (optional): Frames per second

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "output_format": "mp4",
  "quality": "high",
  "resolution": "1920x1080"
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-output...",
  "format": "mp4",
  "message": "Video converted successfully to mp4"
}
```

### 2. `ffmpeg_extract_audio` - Extract Audio

Extract audio track from video file.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `output_format` (optional): Output audio format - mp3, wav, aac, ogg, etc. (default: `"mp3"`)
- `audio_codec` (optional): Audio codec (auto-detected if not specified)
- `bitrate` (optional): Audio bitrate (e.g., `"192k"`, `"320k"`) (default: `"192k"`)

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "output_format": "mp3",
  "bitrate": "320k"
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-audio...",
  "format": "mp3",
  "message": "Audio extracted successfully to mp3"
}
```

### 3. `ffmpeg_merge_videos` - Merge Videos

Merge multiple videos into a single video.

**Parameters:**
- `video_data_list` (required): List of base64-encoded video data
- `output_format` (optional): Output format (default: `"mp4"`)

**Example:**
```json
{
  "video_data_list": ["base64-video-1...", "base64-video-2..."],
  "output_format": "mp4"
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-merged-video...",
  "format": "mp4",
  "message": "Successfully merged 2 videos"
}
```

### 4. `ffmpeg_add_subtitles` - Add Subtitles

Add subtitles to a video.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `subtitle_text` (required): Subtitle text to add
- `start_time` (required): Start time (HH:MM:SS or seconds)
- `duration` (required): Duration (HH:MM:SS or seconds)
- `position` (optional): Subtitle position - top, center, bottom (default: `"bottom"`)
- `font_size` (optional): Font size (default: `24`)
- `output_format` (optional): Output format (default: `"mp4"`)

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "subtitle_text": "Hello, World!",
  "start_time": "00:00:05",
  "duration": "00:00:03",
  "position": "bottom",
  "font_size": 24
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-video-with-subtitles...",
  "format": "mp4",
  "message": "Subtitles added successfully"
}
```

### 5. `ffmpeg_trim_video` - Trim Video

Trim video to a specific time range.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `start_time` (required): Start time (HH:MM:SS or seconds)
- `duration` (optional): Duration (HH:MM:SS or seconds). If not specified, trims to end
- `end_time` (optional): End time (HH:MM:SS or seconds). Alternative to duration
- `output_format` (optional): Output format (default: `"mp4"`)

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "start_time": "00:00:10",
  "duration": "00:00:30",
  "output_format": "mp4"
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-trimmed-video...",
  "format": "mp4",
  "message": "Video trimmed successfully"
}
```

### 6. `ffmpeg_get_video_info_tool` - Get Video Information

Get detailed information about a video file (duration, resolution, codec, etc.).

**Parameters:**
- `input_data` (required): Base64-encoded input video data

**Example:**
```json
{
  "input_data": "base64-encoded-video..."
}
```

**Response:**
```json
{
  "success": true,
  "format": "mp4",
  "duration": "120.5",
  "size": "10485760",
  "bitrate": "8000000",
  "video": {
    "codec": "h264",
    "width": 1920,
    "height": 1080,
    "fps": "30/1",
    "bitrate": "5000000"
  },
  "audio": {
    "codec": "aac",
    "sample_rate": "44100",
    "channels": 2,
    "bitrate": "192000"
  }
}
```

### 7. `ffmpeg_resize_video` - Resize Video

Resize video to specific dimensions.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `width` (required): Output width in pixels
- `height` (required): Output height in pixels
- `maintain_aspect` (optional): Maintain aspect ratio (may add letterboxing) (default: `true`)
- `output_format` (optional): Output format (default: `"mp4"`)

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "width": 1280,
  "height": 720,
  "maintain_aspect": true
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-resized-video...",
  "format": "mp4",
  "resolution": "1280x720",
  "message": "Video resized to 1280x720"
}
```

### 8. `ffmpeg_extract_frame` - Extract Frame

Extract a single frame from video at a specific timestamp.

**Parameters:**
- `input_data` (required): Base64-encoded input video data
- `timestamp` (required): Timestamp to extract frame (HH:MM:SS or seconds)
- `output_format` (optional): Output image format - png, jpg, etc. (default: `"png"`)

**Example:**
```json
{
  "input_data": "base64-encoded-video...",
  "timestamp": "00:01:30",
  "output_format": "png"
}
```

**Response:**
```json
{
  "success": true,
  "output_data": "base64-encoded-image...",
  "format": "png",
  "timestamp": "00:01:30",
  "message": "Frame extracted at 00:01:30"
}
```

## Resources

Access server information as a resource:

- `ffmpeg://info` - Get information about the FFmpeg MCP server and its capabilities

## Example Workflow

1. Get video information:
   ```
   ffmpeg_get_video_info_tool(input_data="base64-video...")
   ```

2. Convert video format:
   ```
   ffmpeg_convert_video(input_data="base64-video...", output_format="webm", quality="high")
   ```

3. Extract audio:
   ```
   ffmpeg_extract_audio(input_data="base64-video...", output_format="mp3", bitrate="320k")
   ```

4. Trim video:
   ```
   ffmpeg_trim_video(input_data="base64-video...", start_time="00:00:10", duration="00:00:30")
   ```

5. Extract a frame:
   ```
   ffmpeg_extract_frame(input_data="base64-video...", timestamp="00:01:00", output_format="png")
   ```

## Notes

- All input and output data must be base64-encoded
- Supported video formats: mp4, avi, mov, webm, mkv, and more
- Supported audio formats: mp3, wav, aac, ogg, and more
- Quality presets: low (CRF 23), medium (CRF 20), high (CRF 18), veryhigh (CRF 16)
- Time formats: Use HH:MM:SS (e.g., "00:01:30") or seconds (e.g., "90")
- The server uses FFmpeg for all processing operations
- Temporary files are automatically cleaned up after processing


