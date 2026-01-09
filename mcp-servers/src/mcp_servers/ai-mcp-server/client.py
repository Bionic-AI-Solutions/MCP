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
