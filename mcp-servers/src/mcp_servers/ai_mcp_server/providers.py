"""
Multi-Provider AI Client Support

Supports routing to different AI providers based on tenant configuration:
- "global" tenant → GPU-AI API at 192.168.0.10:8000
- Other tenants → OpenRouter (LLM/STT), Eleven Labs (TTS), OpenAI (Embeddings)
"""

import asyncio
from typing import Dict, Any, Optional, List
import httpx


class OpenRouterClient:
    """Client for OpenRouter API (LLM and STT services)."""
    
    def __init__(self, api_key: str, timeout: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def chat_completions(self, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """OpenRouter chat completions."""
        payload = {"model": model, "messages": messages, **kwargs}
        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def text_completions(self, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """OpenRouter text completions."""
        payload = {"model": model, "prompt": prompt, **kwargs}
        response = await self.client.post("/completions", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def list_models(self) -> Dict[str, Any]:
        """List OpenRouter models."""
        response = await self.client.get("/models")
        response.raise_for_status()
        return response.json()
    
    async def speech_to_text(self, audio_data: bytes, **kwargs) -> Dict[str, Any]:
        """OpenRouter speech-to-text (if supported)."""
        # OpenRouter may not have STT, but we'll use the same endpoint pattern
        import io
        files = {"file": ("audio.mp3", io.BytesIO(audio_data), "audio/mpeg")}
        # Update headers for multipart
        headers = self.client.headers.copy()
        headers.pop("Content-Type", None)  # Let httpx set Content-Type with boundary
        response = await self.client.post("/audio/transcriptions", files=files, data=kwargs, headers=headers)
        response.raise_for_status()
        return response.json()


class ElevenLabsClient:
    """Client for Eleven Labs API (TTS service)."""
    
    def __init__(self, api_key: str, timeout: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.elevenlabs.io/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def text_to_speech(self, text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM", **kwargs) -> bytes:
        """Eleven Labs text-to-speech."""
        payload = {"text": text, "voice_id": voice_id, **kwargs}
        response = await self.client.post(f"/text-to-speech/{voice_id}", json=payload)
        response.raise_for_status()
        return response.content
    
    async def voice_clone(self, text: str, voice_id: str, **kwargs) -> bytes:
        """Eleven Labs voice clone."""
        return await self.text_to_speech(text, voice_id, **kwargs)
    
    async def list_voices(self) -> Dict[str, Any]:
        """List Eleven Labs voices."""
        response = await self.client.get("/voices")
        response.raise_for_status()
        return response.json()


class OpenAIClient:
    """Client for OpenAI API (Embeddings service)."""
    
    def __init__(self, api_key: str, timeout: int = 300):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
        )
    
    async def close(self):
        await self.client.aclose()
    
    async def create_embeddings(self, model: str, input_text: str, **kwargs) -> Dict[str, Any]:
        """OpenAI embeddings."""
        payload = {"model": model, "input": input_text, **kwargs}
        response = await self.client.post("/embeddings", json=payload)
        response.raise_for_status()
        return response.json()
