"""
AI Client Wrapper

Provides async-friendly wrapper around GPU-AI API (OpenAI-compatible).
Supports concurrency control via semaphores.
"""

import asyncio
from typing import Dict, Any, Optional, List

import httpx


class AIClientWrapper:
    """Wrapper around GPU-AI API client for async operations with concurrency control."""

    def __init__(
        self,
        api_base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 300,
        semaphore: Optional[asyncio.Semaphore] = None,
    ):
        self.api_base_url = api_base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.semaphore = semaphore or asyncio.Semaphore(10)

        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self.client = httpx.AsyncClient(
            base_url=self.api_base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def list_models(self) -> Dict[str, Any]:
        """List available models."""
        async with self.semaphore:
            try:
                response = await self.client.get("/v1/models")
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def chat_completions(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Create a chat completion."""
        async with self.semaphore:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": stream,
                }
                if max_tokens is not None:
                    payload["max_tokens"] = max_tokens
                if temperature is not None:
                    payload["temperature"] = temperature
                if top_p is not None:
                    payload["top_p"] = top_p

                response = await self.client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def text_completions(
        self,
        model: str,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Create a text completion."""
        async with self.semaphore:
            try:
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": stream,
                }
                if max_tokens is not None:
                    payload["max_tokens"] = max_tokens
                if temperature is not None:
                    payload["temperature"] = temperature
                if top_p is not None:
                    payload["top_p"] = top_p

                response = await self.client.post("/v1/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def create_embeddings(
        self,
        model: str,
        input_text: str,
        encoding_format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create embeddings for input text."""
        async with self.semaphore:
            try:
                payload = {
                    "model": model,
                    "input": input_text,
                }
                if encoding_format is not None:
                    payload["encoding_format"] = encoding_format

                response = await self.client.post("/v1/embeddings", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def create_audio_transcription(
        self,
        file_data: bytes,
        filename: str,
        model: str = "whisper-1",
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio to text."""
        async with self.semaphore:
            try:
                import io
                files = {
                    "file": (filename, io.BytesIO(file_data), "audio/mpeg")
                }
                data = {"model": model}
                if language is not None:
                    data["language"] = language
                if prompt is not None:
                    data["prompt"] = prompt
                if response_format is not None:
                    data["response_format"] = response_format
                if temperature is not None:
                    data["temperature"] = temperature

                # Use multipart form data for file upload
                form_data = httpx.MultipartFormData()
                form_data.add_field("file", file_data, filename=filename, content_type="audio/mpeg")
                form_data.add_field("model", model)
                if language is not None:
                    form_data.add_field("language", language)
                if prompt is not None:
                    form_data.add_field("prompt", prompt)
                if response_format is not None:
                    form_data.add_field("response_format", response_format)
                if temperature is not None:
                    form_data.add_field("temperature", str(temperature))

                # Update headers for multipart
                headers = self.client.headers.copy()
                headers.pop("Content-Type", None)  # Let httpx set Content-Type with boundary

                response = await self.client.post(
                    "/v1/audio/transcriptions",
                    content=form_data,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def create_audio_translation(
        self,
        file_data: bytes,
        filename: str,
        model: str = "whisper-1",
        prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Translate audio to English text."""
        async with self.semaphore:
            try:
                # Use multipart form data for file upload
                form_data = httpx.MultipartFormData()
                form_data.add_field("file", file_data, filename=filename, content_type="audio/mpeg")
                form_data.add_field("model", model)
                if prompt is not None:
                    form_data.add_field("prompt", prompt)
                if response_format is not None:
                    form_data.add_field("response_format", response_format)
                if temperature is not None:
                    form_data.add_field("temperature", str(temperature))

                # Update headers for multipart
                headers = self.client.headers.copy()
                headers.pop("Content-Type", None)  # Let httpx set Content-Type with boundary

                response = await self.client.post(
                    "/v1/audio/translations",
                    content=form_data,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def create_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        n: int = 1,
        size: str = "1024x1024",
        quality: Optional[str] = None,
        response_format: Optional[str] = None,
        style: Optional[str] = None,
        user: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate an image from a text prompt."""
        async with self.semaphore:
            try:
                payload = {
                    "prompt": prompt,
                    "n": n,
                    "size": size,
                }
                if model is not None:
                    payload["model"] = model
                if quality is not None:
                    payload["quality"] = quality
                if response_format is not None:
                    payload["response_format"] = response_format
                if style is not None:
                    payload["style"] = style
                if user is not None:
                    payload["user"] = user

                response = await self.client.post("/v1/images/generations", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def create_moderation(
        self,
        input_text: str,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Classify if text violates OpenAI's content policy."""
        async with self.semaphore:
            try:
                payload = {
                    "input": input_text,
                }
                if model is not None:
                    payload["model"] = model

                response = await self.client.post("/v1/moderations", json=payload)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def get_mcp_tools(self) -> Dict[str, Any]:
        """Get MCP tools from the GPU-AI API server at /mcp/tools/tools.
        
        This endpoint may expose additional tools beyond the standard OpenAI-compatible endpoints.
        """
        async with self.semaphore:
            try:
                # Try the /mcp/tools/tools endpoint
                response = await self.client.get("/mcp/tools/tools")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Endpoint doesn't exist yet, return empty list
                    return {
                        "success": True,
                        "tools": [],
                        "message": "MCP tools endpoint (/mcp/tools/tools) not available on GPU-AI API server",
                    }
                raise
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }

    async def proxy_service_request(
        self,
        service_name: str,
        path: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Proxy a request to a service endpoint.
        
        Args:
            service_name: Name of the service (llm, audio, xtts_v2, embeddings, video_generation, video_recognition)
            path: Path to proxy to (e.g., "v1/models", "embeddings", "v1/chat/completions")
            method: HTTP method (GET, POST, PUT, DELETE)
            payload: Optional JSON payload for POST/PUT requests
        """
        async with self.semaphore:
            try:
                # Ensure path doesn't start with /
                path = path.lstrip("/")
                url = f"/api/v1/services/{service_name}/proxy/{path}"
                
                if method.upper() == "GET":
                    response = await self.client.get(url)
                elif method.upper() == "POST":
                    response = await self.client.post(url, json=payload or {})
                elif method.upper() == "PUT":
                    response = await self.client.put(url, json=payload or {})
                elif method.upper() == "DELETE":
                    response = await self.client.delete(url)
                else:
                    return {
                        "success": False,
                        "error": f"Unsupported HTTP method: {method}",
                    }
                
                response.raise_for_status()
                return response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                }
