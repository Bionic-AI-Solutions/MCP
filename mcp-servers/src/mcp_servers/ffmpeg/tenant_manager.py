"""
FFmpeg Tenant Manager

FFmpeg doesn't require multi-tenant support, but we keep the structure for consistency.
"""

import json
import os
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field
import redis.asyncio as redis


class FfmpegTenantConfig(BaseModel):
    """Configuration for FFmpeg (minimal, no tenant-specific config needed)."""
    tenant_id: str = Field(default="default", description="Tenant identifier (not used for FFmpeg)")


class FfmpegTenantManager:
    """Manages FFmpeg operations (stateless, no tenant-specific configuration needed)."""

    def __init__(self):
        self.configs: Dict[str, FfmpegTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:ffmpeg:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "3"))
            redis_password = os.getenv("REDIS_PASSWORD")

            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
            )
            await self.redis_client.ping()
            self._redis_initialized = True
        except Exception as e:
            print(f"Warning: Redis not available: {e}")
            self.redis_client = None
            self._redis_initialized = True

    async def register_tenant(self, config: FfmpegTenantConfig) -> None:
        """Register a tenant (no-op for FFmpeg, but kept for API consistency)."""
        self.configs[config.tenant_id] = config

    async def get_client(self, tenant_id: str) -> Any:
        """Get client for a tenant (returns None for FFmpeg as it's stateless)."""
        return None

    async def initialize(self) -> None:
        """Initialize tenant manager."""
        await self._init_redis()

    async def close_all(self) -> None:
        """Close all connections."""
        self.configs.clear()
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
