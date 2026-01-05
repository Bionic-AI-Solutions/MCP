"""
FFmpeg MCP Server

A FastMCP server providing comprehensive FFmpeg video/audio processing capabilities.
"""

import json
import os
import tempfile
import subprocess
import base64
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

# FFmpeg doesn't need multi-tenant support, but we'll keep the structure for consistency
try:
    from mcp_servers.ffmpeg.tenant_manager import FfmpegTenantManager
except ImportError:
    from .tenant_manager import FfmpegTenantManager

tenant_manager = FfmpegTenantManager()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan."""
    await tenant_manager.initialize()
    yield
    await tenant_manager.close_all()


mcp = FastMCP("FFmpeg Server", lifespan=lifespan)


# ============================================================================
# Helper Functions
# ============================================================================

def run_ffmpeg_command(args: List[str], input_data: Optional[bytes] = None) -> Dict[str, Any]:
    """Run an FFmpeg command and return the result."""
    try:
        cmd = ["ffmpeg", "-y"] + args  # -y to overwrite output files
        if input_data:
            process = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                check=True,
            )
        else:
            process = subprocess.run(
                cmd,
                capture_output=True,
                check=True,
            )
        return {
            "success": True,
            "stdout": process.stdout.decode() if process.stdout else "",
            "stderr": process.stderr.decode() if process.stderr else "",
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "error": e.stderr.decode() if e.stderr else str(e),
            "returncode": e.returncode,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def get_video_info(input_path: str) -> Dict[str, Any]:
    """Get video information using ffprobe."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def ffmpeg_convert_video(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    output_format: str = Field("mp4", description="Output format (mp4, avi, mov, webm, etc.)"),
    video_codec: Optional[str] = Field(None, description="Video codec (h264, vp9, etc.). Auto-detected if not specified"),
    audio_codec: Optional[str] = Field(None, description="Audio codec (aac, mp3, etc.). Auto-detected if not specified"),
    quality: Optional[str] = Field(None, description="Quality preset (low, medium, high, veryhigh)"),
    resolution: Optional[str] = Field(None, description="Output resolution (e.g., '1920x1080', '1280x720')"),
    bitrate: Optional[str] = Field(None, description="Video bitrate (e.g., '2M', '5000k')"),
    fps: Optional[int] = Field(None, description="Fideos per second"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Convert video to a different format with optional quality/resolution adjustments."""
    if ctx:
        await ctx.info(f"Converting video to {output_format} format...")
    
    try:
        # Decode input
        input_bytes = base64.b64decode(input_data)
        
        # Create temporary files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        # Build FFmpeg command
        args = ["-i", input_path]
        
        if video_codec:
            args.extend(["-c:v", video_codec])
        if audio_codec:
            args.extend(["-c:a", audio_codec])
        if quality:
            quality_map = {
                "low": "23",
                "medium": "20",
                "high": "18",
                "veryhigh": "16",
            }
            if video_codec == "libx264" or not video_codec:
                args.extend(["-crf", quality_map.get(quality, "20")])
        if resolution:
            args.extend(["-vf", f"scale={resolution}"])
        if bitrate:
            args.extend(["-b:v", bitrate])
        if fps:
            args.extend(["-r", str(fps)])
        
        args.append(output_path)
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            # Read output file
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            # Cleanup
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "message": f"Video converted successfully to {output_format}",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_extract_audio(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    output_format: str = Field("mp3", description="Output audio format (mp3, wav, aac, ogg, etc.)"),
    audio_codec: Optional[str] = Field(None, description="Audio codec. Auto-detected if not specified"),
    bitrate: Optional[str] = Field("192k", description="Audio bitrate (e.g., '192k', '320k')"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract audio track from video file."""
    if ctx:
        await ctx.info(f"Extracting audio to {output_format} format...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        args = ["-i", input_path, "-vn"]  # -vn = no video
        
        if audio_codec:
            args.extend(["-c:a", audio_codec])
        if bitrate:
            args.extend(["-b:a", bitrate])
        
        args.append(output_path)
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "message": f"Audio extracted successfully to {output_format}",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_merge_videos(
    video_data_list: List[str] = Field(..., description="List of base64-encoded video data"),
    output_format: str = Field("mp4", description="Output format"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Merge multiple videos into a single video."""
    if ctx:
        await ctx.info(f"Merging {len(video_data_list)} videos...")
    
    try:
        input_paths = []
        for i, video_data in enumerate(video_data_list):
            video_bytes = base64.b64decode(video_data)
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.input") as f:
                f.write(video_bytes)
                input_paths.append(f.name)
        
        # Create concat file
        concat_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt")
        for path in input_paths:
            concat_file.write(f"file '{os.path.abspath(path)}'\n")
        concat_file.close()
        
        output_path = concat_file.name.replace(".txt", f".{output_format}")
        
        args = [
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file.name,
            "-c", "copy",
            output_path,
        ]
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            # Cleanup
            for path in input_paths:
                os.unlink(path)
            os.unlink(concat_file.name)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "message": f"Successfully merged {len(video_data_list)} videos",
            }
        else:
            for path in input_paths:
                if os.path.exists(path):
                    os.unlink(path)
            if os.path.exists(concat_file.name):
                os.unlink(concat_file.name)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_add_subtitles(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    subtitle_text: str = Field(..., description="Subtitle text to add"),
    start_time: str = Field(..., description="Start time (HH:MM:SS or seconds)"),
    duration: str = Field(..., description="Duration (HH:MM:SS or seconds)"),
    position: str = Field("bottom", description="Subtitle position (top, center, bottom)"),
    font_size: int = Field(24, description="Font size"),
    output_format: str = Field("mp4", description="Output format"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add subtitles to a video."""
    if ctx:
        await ctx.info("Adding subtitles to video...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        # Position mapping
        position_map = {
            "top": "x=(w-text_w)/2:y=50",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "bottom": "x=(w-text_w)/2:y=h-th-50",
        }
        
        subtitle_filter = (
            f"drawtext=text='{subtitle_text}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"borderw=2:"
            f"bordercolor=black:"
            f"{position_map.get(position, position_map['bottom'])}:"
            f"enable='between(t,{start_time},{duration})'"
        )
        
        args = [
            "-i", input_path,
            "-vf", subtitle_filter,
            "-c:a", "copy",
            output_path,
        ]
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "message": "Subtitles added successfully",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_trim_video(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    start_time: str = Field(..., description="Start time (HH:MM:SS or seconds)"),
    duration: Optional[str] = Field(None, description="Duration (HH:MM:SS or seconds). If not specified, trims to end"),
    end_time: Optional[str] = Field(None, description="End time (HH:MM:SS or seconds). Alternative to duration"),
    output_format: str = Field("mp4", description="Output format"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Trim video to a specific time range."""
    if ctx:
        await ctx.info(f"Trimming video from {start_time}...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        args = ["-i", input_path, "-ss", start_time]
        
        if duration:
            args.extend(["-t", duration])
        elif end_time:
            # Calculate duration from start and end
            args.extend(["-to", end_time])
        
        args.extend(["-c", "copy", output_path])
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "message": "Video trimmed successfully",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_get_video_info_tool(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a video file (duration, resolution, codec, etc.)."""
    if ctx:
        await ctx.info("Analyzing video file...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        info = get_video_info(input_path)
        
        os.unlink(input_path)
        
        if "error" in info:
            return {"success": False, "error": info["error"]}
        
        # Extract useful information
        video_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
        
        result = {
            "success": True,
            "format": info.get("format", {}).get("format_name", "unknown"),
            "duration": info.get("format", {}).get("duration", "unknown"),
            "size": info.get("format", {}).get("size", "unknown"),
            "bitrate": info.get("format", {}).get("bit_rate", "unknown"),
        }
        
        if video_stream:
            result["video"] = {
                "codec": video_stream.get("codec_name", "unknown"),
                "width": video_stream.get("width", "unknown"),
                "height": video_stream.get("height", "unknown"),
                "fps": video_stream.get("r_frame_rate", "unknown"),
                "bitrate": video_stream.get("bit_rate", "unknown"),
            }
        
        if audio_stream:
            result["audio"] = {
                "codec": audio_stream.get("codec_name", "unknown"),
                "sample_rate": audio_stream.get("sample_rate", "unknown"),
                "channels": audio_stream.get("channels", "unknown"),
                "bitrate": audio_stream.get("bit_rate", "unknown"),
            }
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_resize_video(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    width: int = Field(..., description="Output width in pixels"),
    height: int = Field(..., description="Output height in pixels"),
    maintain_aspect: bool = Field(True, description="Maintain aspect ratio (may add letterboxing)"),
    output_format: str = Field("mp4", description="Output format"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Resize video to specific dimensions."""
    if ctx:
        await ctx.info(f"Resizing video to {width}x{height}...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        if maintain_aspect:
            scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        else:
            scale_filter = f"scale={width}:{height}"
        
        args = [
            "-i", input_path,
            "-vf", scale_filter,
            "-c:a", "copy",
            output_path,
        ]
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "resolution": f"{width}x{height}",
                "message": f"Video resized to {width}x{height}",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def ffmpeg_extract_frame(
    input_data: str = Field(..., description="Base64-encoded input video data"),
    timestamp: str = Field(..., description="Timestamp to extract frame (HH:MM:SS or seconds)"),
    output_format: str = Field("png", description="Output image format (png, jpg, etc.)"),
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Extract a single frame from video at a specific timestamp."""
    if ctx:
        await ctx.info(f"Extracting frame at {timestamp}...")
    
    try:
        input_bytes = base64.b64decode(input_data)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as input_file:
            input_file.write(input_bytes)
            input_path = input_file.name
        
        output_path = input_path.replace(".input", f".{output_format}")
        
        args = [
            "-i", input_path,
            "-ss", timestamp,
            "-vframes", "1",
            output_path,
        ]
        
        result = run_ffmpeg_command(args)
        
        if result["success"]:
            with open(output_path, "rb") as f:
                output_data = base64.b64encode(f.read()).decode()
            
            os.unlink(input_path)
            os.unlink(output_path)
            
            return {
                "success": True,
                "output_data": output_data,
                "format": output_format,
                "timestamp": timestamp,
                "message": f"Frame extracted at {timestamp}",
            }
        else:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return result
            
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("ffmpeg://info")
def server_info() -> str:
    """Get information about the FFmpeg MCP server."""
    return json.dumps({
        "server": "FFmpeg MCP Server",
        "description": "Comprehensive video and audio processing using FFmpeg",
        "capabilities": [
            "Video format conversion",
            "Audio extraction",
            "Video merging",
            "Subtitle addition",
            "Video trimming",
            "Video resizing",
            "Frame extraction",
            "Video information analysis",
        ],
    }, indent=2)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the FFmpeg server with HTTP transport for remote access."""
    import os
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8004"))
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()
