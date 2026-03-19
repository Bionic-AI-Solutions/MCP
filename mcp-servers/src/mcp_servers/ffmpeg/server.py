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
    """Convert a video file from one format to another with optional transcoding settings.

    Use this tool to re-encode or re-mux a video into a different container format
    (e.g., MKV to MP4, AVI to WebM) and optionally adjust quality, resolution, bitrate,
    or frame rate during the conversion. This is the primary tool for format conversion
    and transcoding workflows.

    Common use cases:
    - Converting between container formats (MP4, AVI, MOV, WebM, MKV, FLV).
    - Transcoding to a specific codec for compatibility (e.g., H.264 for web playback).
    - Reducing file size by lowering quality, resolution, or bitrate.
    - Changing frame rate for slow-motion or time-lapse effects.

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file.
        output_format: str, default "mp4". Target container format. Supported values
            include "mp4", "avi", "mov", "webm", "mkv", "flv", and other FFmpeg-supported
            formats.
        video_codec: str or None, default None. Video codec to use for encoding (e.g.,
            "libx264", "libvpx-vp9", "h264", "vp9"). When None, FFmpeg selects an
            appropriate codec for the output format automatically.
        audio_codec: str or None, default None. Audio codec to use (e.g., "aac", "mp3",
            "libvorbis", "opus"). When None, FFmpeg selects an appropriate codec
            automatically.
        quality: str or None, default None. Quality preset that maps to CRF values for
            H.264-based encoding: "low" (CRF 23), "medium" (CRF 20), "high" (CRF 18),
            "veryhigh" (CRF 16). Lower CRF means higher quality and larger file size.
            Only applied when video_codec is "libx264" or unspecified.
        resolution: str or None, default None. Target resolution as "WIDTHxHEIGHT" (e.g.,
            "1920x1080", "1280x720", "640x480"). The video will be scaled to this size.
        bitrate: str or None, default None. Target video bitrate (e.g., "2M" for 2 Mbps,
            "5000k" for 5000 kbps). Overrides quality-based CRF if both are specified.
        fps: int or None, default None. Target frames per second. Use to change the
            playback frame rate of the output video.

    Returns:
        Dict with:
        - success (bool): Whether the conversion completed without errors.
        - output_data (str): Base64-encoded binary content of the converted video file.
            Only present when success is True.
        - format (str): The output format that was used. Only present when success is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the conversion failed.

    Note:
        - The input video is received and returned as base64-encoded data, so very large
          files may cause memory pressure or exceed transport limits.
        - When both quality and bitrate are specified, bitrate takes precedence for rate
          control, but both flags are passed to FFmpeg.
        - The quality preset (CRF mapping) is only applied for H.264 encoding. Other
          codecs ignore the quality parameter.
    """
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
    """Extract the audio track from a video file and save it as a standalone audio file.

    Use this tool to strip the audio stream out of a video container without
    re-encoding the video. This is useful when you only need the soundtrack,
    voiceover, or music from a video file. The video stream is discarded entirely.

    Common use cases:
    - Extracting a podcast or interview audio from a recorded video.
    - Ripping a music track from a music video.
    - Converting video narration into an audio file for transcription.
    - Creating audio-only versions of lectures or presentations.

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file
            that contains the audio track to extract.
        output_format: str, default "mp3". Target audio container format. Supported values
            include "mp3", "wav", "aac", "ogg", "flac", "m4a", and other FFmpeg-supported
            audio formats.
        audio_codec: str or None, default None. Audio codec to use for encoding (e.g.,
            "libmp3lame", "aac", "libvorbis", "pcm_s16le"). When None, FFmpeg selects an
            appropriate codec based on the output format automatically.
        bitrate: str or None, default "192k". Target audio bitrate (e.g., "128k", "192k",
            "320k"). Higher bitrates produce better audio quality at the cost of larger
            file sizes. Common values: "128k" (acceptable), "192k" (good), "256k" (high),
            "320k" (maximum for MP3).

    Returns:
        Dict with:
        - success (bool): Whether the extraction completed without errors.
        - output_data (str): Base64-encoded binary content of the extracted audio file.
            Only present when success is True.
        - format (str): The output audio format that was used. Only present when success
            is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the extraction failed.

    Note:
        - If the source video has no audio stream, FFmpeg will fail and return an error.
        - The video stream is completely discarded (using the -vn flag); only audio is kept.
        - For lossless extraction without re-encoding, set the audio_codec to "copy" and
          use a compatible output format that matches the source audio codec.
    """
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
    """Merge (concatenate) multiple video files into a single continuous video.

    Use this tool to join two or more video segments end-to-end into one output file.
    The videos are concatenated in the order they appear in the input list using
    FFmpeg's concat demuxer with stream copying (no re-encoding), which is fast but
    requires that all input videos share the same codec, resolution, and frame rate.

    Common use cases:
    - Joining video chapters or segments that were recorded separately.
    - Combining multiple camera takes into a single continuous video.
    - Assembling a final cut from individually processed video clips.
    - Merging split video downloads back into one file.

    Args:
        video_data_list: list of str, required. An ordered list of base64-encoded binary
            video data. Each element represents one video segment. The videos are
            concatenated in list order (index 0 is first, index 1 follows, etc.).
            All videos should ideally share the same codec, resolution, and frame rate
            for seamless merging.
        output_format: str, default "mp4". Target container format for the merged output.
            Supported values include "mp4", "avi", "mov", "mkv", "webm", and other
            FFmpeg-supported formats.

    Returns:
        Dict with:
        - success (bool): Whether the merge completed without errors.
        - output_data (str): Base64-encoded binary content of the merged video file.
            Only present when success is True.
        - format (str): The output format that was used. Only present when success is True.
        - message (str): Human-readable status message including the number of merged
            videos. Only present when success is True.
        - error (str): Error description if the merge failed.

    Note:
        - This tool uses stream copying ("-c copy") for speed, which means input videos
          must have compatible codecs, resolutions, and frame rates. Mismatched inputs may
          produce errors or playback artifacts.
        - If the input videos have different codecs or resolutions, convert them to a
          uniform format first using ffmpeg_convert_video before merging.
        - All input data is held in memory simultaneously, so merging many or very large
          videos may cause memory pressure.
    """
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
    """Burn a text subtitle overlay onto a video at a specified time range and position.

    Use this tool to hard-code (burn in) a single text string onto the video frames
    using FFmpeg's drawtext filter. The subtitle appears as white text with a black
    border for readability, positioned at the chosen vertical location on the frame.
    Because the text is rendered directly into the video pixels, it cannot be toggled
    off during playback (unlike soft subtitles in SRT/ASS format).

    Common use cases:
    - Adding a title card or caption to a specific segment of a video.
    - Burning hardcoded subtitles for platforms that do not support subtitle tracks.
    - Overlaying a single annotation, watermark text, or label onto footage.
    - Adding timed lower-third text for interviews or presentations.

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file.
        subtitle_text: str, required. The text string to display on the video. Avoid
            single quotes and special characters in the text as they may interfere with
            the FFmpeg drawtext filter syntax.
        start_time: str, required. The timestamp at which the subtitle should first
            appear. Accepts either "HH:MM:SS" format (e.g., "00:01:30") or a plain
            number of seconds (e.g., "90"). This value is passed to the drawtext
            filter's enable expression as the start of the visibility window.
        duration: str, required. The timestamp at which the subtitle should disappear.
            Despite the parameter name, this is used as the *end time* in the
            between(t, start, end) expression, not as a relative duration. Accepts
            "HH:MM:SS" format or seconds.
        position: str, default "bottom". Vertical placement of the subtitle text on the
            video frame. Accepted values: "top" (near the top edge), "center" (vertically
            centered), "bottom" (near the bottom edge). The text is always horizontally
            centered.
        font_size: int, default 24. Font size in pixels for the subtitle text. Larger
            values produce bigger text. Typical values range from 16 (small) to 48 (large).
        output_format: str, default "mp4". Target container format for the output video.
            Supported values include "mp4", "avi", "mov", "mkv", "webm", and other
            FFmpeg-supported formats.

    Returns:
        Dict with:
        - success (bool): Whether the subtitle overlay completed without errors.
        - output_data (str): Base64-encoded binary content of the video with burned-in
            subtitles. Only present when success is True.
        - format (str): The output format that was used. Only present when success is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the operation failed.

    Note:
        - The video stream is re-encoded because the drawtext filter modifies pixel data.
          The audio stream is copied without re-encoding.
        - For multiple subtitle lines at different times, call this tool repeatedly,
          passing the output of one call as the input to the next.
        - Special characters (single quotes, backslashes, colons) in subtitle_text may
          need escaping or may cause FFmpeg filter parsing errors.
        - The "duration" parameter is actually interpreted as an end time, not a relative
          duration. For example, to show text from 10s to 20s, set start_time="10" and
          duration="20".
    """
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
    """Trim a video to extract a specific time range, discarding everything outside it.

    Use this tool to cut out a portion of a video by specifying a start time and
    either a duration or an end time. The trimmed segment is extracted using stream
    copying (no re-encoding), making the operation very fast. Both the video and audio
    streams are preserved in the output.

    Common use cases:
    - Cutting a highlight clip from a longer recording.
    - Removing unwanted intro or outro sections from a video.
    - Extracting a specific scene or chapter from a movie or lecture.
    - Splitting a long video into shorter segments (call multiple times with different
      time ranges).

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file
            to trim.
        start_time: str, required. The point in the video where the trimmed output should
            begin. Accepts "HH:MM:SS" format (e.g., "00:01:30") or a plain number of
            seconds (e.g., "90").
        duration: str or None, default None. How long the trimmed segment should be,
            measured from start_time. Accepts "HH:MM:SS" format or seconds (e.g., "30"
            for 30 seconds). Mutually exclusive with end_time. If neither duration nor
            end_time is specified, the video is kept from start_time to the end.
        end_time: str or None, default None. The absolute timestamp where the trimmed
            segment should stop. Accepts "HH:MM:SS" format or seconds. Mutually exclusive
            with duration. If neither end_time nor duration is specified, the video is
            kept from start_time to the end.
        output_format: str, default "mp4". Target container format for the trimmed output.
            Supported values include "mp4", "avi", "mov", "mkv", "webm", and other
            FFmpeg-supported formats.

    Returns:
        Dict with:
        - success (bool): Whether the trim completed without errors.
        - output_data (str): Base64-encoded binary content of the trimmed video file.
            Only present when success is True.
        - format (str): The output format that was used. Only present when success is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the trim failed.

    Note:
        - This tool uses stream copying ("-c copy") so it does not re-encode the video,
          making it extremely fast. However, the actual cut point may not be frame-exact
          because stream copying can only cut on keyframes. The trimmed clip may start
          a few frames before the requested start_time.
        - If you need frame-exact trimming, use ffmpeg_convert_video with appropriate
          start/end parameters instead (which re-encodes the video).
        - If both duration and end_time are provided, duration takes precedence.
    """
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
    """Retrieve detailed metadata and technical information about a video file.

    Use this tool to inspect a video file's properties without modifying it. It runs
    ffprobe under the hood to extract container format details, video stream properties
    (codec, resolution, frame rate), and audio stream properties (codec, sample rate,
    channels). This is useful for understanding a file's characteristics before
    performing any processing operations.

    Common use cases:
    - Checking a video's resolution and codec before deciding on conversion settings.
    - Verifying the duration of a video before trimming.
    - Inspecting audio properties (sample rate, channels) before extraction.
    - Debugging playback issues by examining codec and container details.
    - Determining file size and bitrate to estimate output sizes after conversion.

    Args:
        input_data: str, required. Base64-encoded binary content of the video file to
            analyze. The file is written to a temporary location, probed, and then
            deleted.

    Returns:
        Dict with:
        - success (bool): Whether the probe completed without errors.
        - format (str): Container format name (e.g., "mov,mp4,m4a,3gp,3g2,mj2").
            Only present when success is True.
        - duration (str): Total duration in seconds as a string (e.g., "120.500000").
            Only present when success is True.
        - size (str): File size in bytes as a string. Only present when success is True.
        - bitrate (str): Overall bitrate in bits per second as a string.
            Only present when success is True.
        - video (dict): Video stream details, only present if the file contains a video
            stream. Contains keys: "codec" (str), "width" (int), "height" (int),
            "fps" (str, as a fraction like "30/1"), "bitrate" (str).
        - audio (dict): Audio stream details, only present if the file contains an audio
            stream. Contains keys: "codec" (str), "sample_rate" (str, e.g., "44100"),
            "channels" (int), "bitrate" (str).
        - error (str): Error description if the probe failed.

    Note:
        - This tool is read-only and does not modify the video in any way.
        - If the file is audio-only, the "video" key will be absent from the response.
        - If the file has no audio track, the "audio" key will be absent.
        - Fields that cannot be determined are returned as the string "unknown".
    """
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
    """Resize a video to specific pixel dimensions, optionally preserving the aspect ratio.

    Use this tool to scale a video to a target width and height. When aspect ratio
    preservation is enabled (the default), the video is first scaled down to fit
    within the target dimensions and then padded (letterboxed or pillarboxed) with
    black bars to reach the exact requested size. When aspect ratio preservation is
    disabled, the video is stretched to fill the exact dimensions, which may distort
    the image.

    Common use cases:
    - Resizing a video for a specific platform (e.g., 1920x1080 for YouTube,
      1080x1920 for Instagram Stories, 1280x720 for web embedding).
    - Downscaling a 4K video to 1080p or 720p for smaller file sizes.
    - Creating uniform dimensions across multiple clips before merging them.
    - Generating thumbnail-sized video previews.

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file.
        width: int, required. Target width in pixels for the output video (e.g., 1920,
            1280, 640). Must be a positive integer. Some codecs require even dimensions.
        height: int, required. Target height in pixels for the output video (e.g., 1080,
            720, 480). Must be a positive integer. Some codecs require even dimensions.
        maintain_aspect: bool, default True. When True, the original aspect ratio is
            preserved: the video is scaled to fit within width x height and black padding
            (letterboxing/pillarboxing) is added to fill the remaining space. When False,
            the video is stretched to exactly width x height, which may cause distortion.
        output_format: str, default "mp4". Target container format for the resized output.
            Supported values include "mp4", "avi", "mov", "mkv", "webm", and other
            FFmpeg-supported formats.

    Returns:
        Dict with:
        - success (bool): Whether the resize completed without errors.
        - output_data (str): Base64-encoded binary content of the resized video file.
            Only present when success is True.
        - format (str): The output format that was used. Only present when success is True.
        - resolution (str): The target resolution as "WIDTHxHEIGHT". Only present when
            success is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the resize failed.

    Note:
        - The video stream is re-encoded because the scale/pad filter modifies pixel data.
          The audio stream is copied without re-encoding to preserve quality and speed.
        - Some codecs (notably H.264) require both width and height to be even numbers.
          If you provide odd dimensions, FFmpeg may fail. Use even values like 1920x1080,
          1280x720, 640x480, etc.
        - When maintain_aspect is True, the padding color is black. The padding is evenly
          distributed on both sides (top/bottom or left/right).
    """
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
    """Extract a single still-image frame from a video at a specific timestamp.

    Use this tool to capture one frame from a video and save it as an image file.
    This is equivalent to taking a screenshot of the video at the given point in time.
    The extracted frame is returned as a base64-encoded image in the requested format.

    Common use cases:
    - Generating a thumbnail or poster image for a video.
    - Capturing a specific moment from a video for use as a still photograph.
    - Creating preview images for video galleries or playlists.
    - Extracting a frame for visual inspection or quality analysis.
    - Pulling a reference frame to compare before and after processing.

    Args:
        input_data: str, required. Base64-encoded binary content of the source video file
            from which to extract the frame.
        timestamp: str, required. The point in the video to capture. Accepts "HH:MM:SS"
            format (e.g., "00:00:05" for 5 seconds in) or a plain number of seconds
            (e.g., "5", "30.5"). If the timestamp exceeds the video duration, FFmpeg may
            produce an error or extract the last available frame.
        output_format: str, default "png". Image format for the extracted frame. Supported
            values include "png" (lossless, larger file), "jpg"/"jpeg" (lossy, smaller
            file), "bmp" (uncompressed), "tiff", and other FFmpeg-supported image formats.
            Use "png" when you need pixel-perfect quality; use "jpg" when file size matters.

    Returns:
        Dict with:
        - success (bool): Whether the frame extraction completed without errors.
        - output_data (str): Base64-encoded binary content of the extracted image file.
            Only present when success is True.
        - format (str): The output image format that was used. Only present when success
            is True.
        - timestamp (str): The timestamp that was requested. Only present when success
            is True.
        - message (str): Human-readable status message. Only present when success is True.
        - error (str): Error description if the extraction failed.

    Note:
        - Only one frame is extracted per call. To extract multiple frames (e.g., for a
          storyboard), call this tool multiple times with different timestamps.
        - The extracted frame corresponds to the nearest keyframe or decoded frame at the
          given timestamp. There may be a slight offset from the exact requested time.
        - PNG output is lossless but produces larger files; JPEG is lossy but much smaller.
          For thumbnails, JPEG is usually sufficient.
    """
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
