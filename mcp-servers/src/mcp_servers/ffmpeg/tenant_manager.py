"""
FFmpeg Tenant Manager

FFmpeg doesn't require multi-tenant support, but we keep the structure for consistency.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis

from mcp_servers.common.config_loader import load_tenant_configs_from_file


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
            redis_db = int(os.getenv("REDIS_DB", "3"))  # Use DB 3 for FFmpeg
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
            print(f"Warning: Redis not available for tenant persistence: {e}")
            self.redis_client = None
            self._redis_initialized = True

    async def _save_to_redis(self, config: FfmpegTenantConfig) -> None:
        """Save tenant configuration to Redis."""
        await self._init_redis()
        if not self.redis_client:
            return

        try:
            key = f"{self.redis_key_prefix}{config.tenant_id}"
            config_dict = config.model_dump()
            await self.redis_client.set(key, json.dumps(config_dict))
        except Exception as e:
            print(f"Warning: Failed to save tenant config to Redis: {e}")

    async def _load_from_redis(self, tenant_id: str) -> Optional[FfmpegTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return FfmpegTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, FfmpegTenantConfig]:
        """Load all tenant configurations from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return {}

        configs = {}
        try:
            pattern = f"{self.redis_key_prefix}*"
            keys = await self.redis_client.keys(pattern)
            for key in keys:
                tenant_id = key.replace(self.redis_key_prefix, "")
                config = await self._load_from_redis(tenant_id)
                if config:
                    configs[tenant_id] = config
        except Exception as e:
            print(f"Warning: Failed to load all tenant configs from Redis: {e}")
        return configs

    def _load_tenants_from_config_file(self) -> Dict[str, FfmpegTenantConfig]:
        """Load tenant configurations from the mounted JSON config file."""
        raw_configs = load_tenant_configs_from_file()
        configs = {}
        for tenant_id, raw in raw_configs.items():
            try:
                raw["tenant_id"] = tenant_id
                configs[tenant_id] = FfmpegTenantConfig(**raw)
            except Exception as e:
                print(f"Warning: Invalid config for tenant '{tenant_id}' in config file: {e}")
        return configs

    async def register_tenant(self, config: FfmpegTenantConfig) -> None:
        """Register a tenant (no-op for FFmpeg, but kept for API consistency)."""
        self.configs[config.tenant_id] = config
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> Any:
        """Get client for a tenant (returns None for FFmpeg as it's stateless)."""
        return None

    async def initialize(self) -> None:
        """Initialize tenant manager - load all tenants from Redis, config file, and environment.

        Loading priority (later sources fill gaps, not overwrite):
        1. Redis persistence (restored from previous runs)
        2. Config file (/etc/mcp/tenants.json from K8s Secret volume)
        3. Environment variables (legacy fallback for local dev / docker-compose)
        """
        # 1. Load all from Redis
        redis_configs = await self._load_all_from_redis()
        for config in redis_configs.values():
            try:
                await self.register_tenant(config)
            except Exception as e:
                print(f"Warning: Skipping Redis tenant '{config.tenant_id}': {e}")

        # 2. Load from config file (fills gaps not covered by Redis)
        file_configs = self._load_tenants_from_config_file()
        for tenant_id, config in file_configs.items():
            if tenant_id not in self.configs:
                try:
                    await self.register_tenant(config)
                except Exception as e:
                    print(f"Warning: Config-file tenant '{tenant_id}' failed: {e}")

    async def close_all(self) -> None:
        """Close all connections."""
        self.configs.clear()
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
