"""
PDF Generator Tenant Manager

Manages multiple PDF generator tenant configurations.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
from typing import Optional, Dict
from pathlib import Path

from pydantic import BaseModel, Field
import redis.asyncio as redis


class PdfGeneratorTenantConfig(BaseModel):
    """Configuration for a single PDF generator tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    storage_path: Optional[str] = Field(
        default=None,
        description="Optional custom storage path for this tenant's PDFs"
    )


class PdfGeneratorTenantManager:
    """Manages multiple PDF generator tenant configurations with Redis persistence."""

    def __init__(self):
        self.configs: Dict[str, PdfGeneratorTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:pdf-generator:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "0"))
            redis_password = os.getenv("REDIS_PASSWORD")

            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
            )
            # Test connection
            await self.redis_client.ping()
            self._redis_initialized = True
        except Exception as e:
            # If Redis is not available, continue without persistence
            print(f"Warning: Redis not available for tenant persistence: {e}")
            self.redis_client = None
            self._redis_initialized = True  # Mark as initialized to avoid retry loops

    async def _save_to_redis(self, config: PdfGeneratorTenantConfig) -> None:
        """Save tenant configuration to Redis."""
        await self._init_redis()
        if not self.redis_client:
            return

        try:
            key = f"{self.redis_key_prefix}{config.tenant_id}"
            # Store as JSON (sensitive data will be in plain text - consider encryption for production)
            config_dict = config.model_dump()
            await self.redis_client.set(key, json.dumps(config_dict))
        except Exception as e:
            print(f"Warning: Failed to save tenant config to Redis: {e}")

    async def _load_from_redis(self, tenant_id: str) -> Optional[PdfGeneratorTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return PdfGeneratorTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, PdfGeneratorTenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[PdfGeneratorTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"PDF_GENERATOR_TENANT_{tenant_id.upper()}"
        
        storage_path = os.getenv(f"{prefix}_STORAGE_PATH")
        
        # If no config found, return None
        if not storage_path:
            return None
        
        return PdfGeneratorTenantConfig(
            tenant_id=tenant_id,
            storage_path=storage_path,
        )

    async def register_tenant(self, config: PdfGeneratorTenantConfig) -> None:
        """Register a tenant configuration."""
        # Create storage directory if custom path provided
        if config.storage_path:
            storage_dir = Path(config.storage_path)
            storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.configs[config.tenant_id] = config

        # Persist to Redis
        await self._save_to_redis(config)

    async def initialize(self) -> None:
        """Initialize tenant manager - load all tenants from Redis and environment."""
        # Load all from Redis
        redis_configs = await self._load_all_from_redis()
        for config in redis_configs.values():
            await self.register_tenant(config)

        # Also load from environment variables (they take precedence)
        # Check for common tenant IDs
        tenant_ids = set()
        for key in os.environ:
            if key.startswith("PDF_GENERATOR_TENANT_") and key.endswith("_STORAGE_PATH"):
                tenant_id = key.replace("PDF_GENERATOR_TENANT_", "").replace("_STORAGE_PATH", "").lower()
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    await self.register_tenant(config)

    async def close_all(self) -> None:
        """Close Redis connection."""
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False

