"""
Langfuse Client Wrapper

Wraps the Langfuse SDK client with concurrency control.
"""

import asyncio
from typing import Optional, Dict, Any
import httpx


class LangfuseClientWrapper:
    """Wrapper for Langfuse client with concurrency control."""

    def __init__(
        self,
        secret_key: str,
        public_key: str,
        base_url: str,
        semaphore: asyncio.Semaphore,
    ):
        """Initialize Langfuse client wrapper.

        Args:
            secret_key: Langfuse secret key (sk-lf-...)
            public_key: Langfuse public key (pk-lf-...)
            base_url: Langfuse base URL
            semaphore: Semaphore for concurrency control
        """
        self.secret_key = secret_key
        self.public_key = public_key
        self.base_url = base_url.rstrip("/")
        self.semaphore = semaphore
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            # Create Basic Auth header: public_key:secret_key encoded in base64
            import base64

            credentials = f"{self.public_key}:{self.secret_key}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def score(
        self,
        trace_id: Optional[str] = None,
        name: str = "",
        value: float = 0.0,
        observation_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a score for a trace or observation."""
        async with self.semaphore:
            client = await self._get_client()
            payload = {
                "traceId": trace_id,
                "name": name,
                "value": value,
            }
            if observation_id:
                payload["observationId"] = observation_id
            if comment:
                payload["comment"] = comment

            response = await client.post("/api/public/scores", json=payload)
            response.raise_for_status()
            return response.json()

    async def trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """Create a trace."""
        async with self.semaphore:
            client = await self._get_client()
            payload = {
                "name": name,
            }
            if user_id:
                payload["userId"] = user_id
            if session_id:
                payload["sessionId"] = session_id
            if metadata:
                payload["metadata"] = metadata
            if tags:
                payload["tags"] = tags

            response = await client.post("/api/public/traces", json=payload)
            response.raise_for_status()
            return response.json()

    async def span(
        self,
        trace_id: str,
        name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a span within a trace."""
        async with self.semaphore:
            client = await self._get_client()
            payload = {
                "traceId": trace_id,
                "name": name,
            }
            if start_time:
                payload["startTime"] = start_time
            if end_time:
                payload["endTime"] = end_time
            if metadata:
                payload["metadata"] = metadata

            response = await client.post("/api/public/spans", json=payload)
            response.raise_for_status()
            return response.json()

    async def generation(
        self,
        trace_id: str,
        name: str,
        model: Optional[str] = None,
        model_parameters: Optional[Dict[str, Any]] = None,
        input: Optional[Any] = None,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a generation (LLM call) observation."""
        async with self.semaphore:
            client = await self._get_client()
            payload = {
                "traceId": trace_id,
                "name": name,
            }
            if model:
                payload["model"] = model
            if model_parameters:
                payload["modelParameters"] = model_parameters
            if input is not None:
                payload["input"] = input
            if output is not None:
                payload["output"] = output
            if metadata:
                payload["metadata"] = metadata

            response = await client.post("/api/public/generations", json=payload)
            response.raise_for_status()
            return response.json()

    async def event(
        self,
        trace_id: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an event observation."""
        async with self.semaphore:
            client = await self._get_client()
            payload = {
                "traceId": trace_id,
                "name": name,
            }
            if metadata:
                payload["metadata"] = metadata

            response = await client.post("/api/public/events", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_trace(self, trace_id: str) -> Dict[str, Any]:
        """Get a trace by ID."""
        async with self.semaphore:
            client = await self._get_client()
            response = await client.get(f"/api/public/traces/{trace_id}")
            response.raise_for_status()
            return response.json()

    async def get_project(self) -> Dict[str, Any]:
        """Get project information."""
        async with self.semaphore:
            client = await self._get_client()
            response = await client.get("/api/public/projects/current")
            response.raise_for_status()
            return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
