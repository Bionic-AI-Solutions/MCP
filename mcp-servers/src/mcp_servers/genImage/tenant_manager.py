"""
GenImage Tenant Manager

Manages multiple GenImage tenant connections with Runware API.
Tenant configurations are persisted in Redis for durability across restarts.
Each tenant provides their own Runware API key for isolation.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis


class GenImageTenantConfig(BaseModel):
    """Configuration for a single GenImage tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    runware_api_key: str = Field(..., description="Runware API key for this tenant")
    base_url: str = Field(
        default="https://api.runware.ai/v1",
        description="Runware API base URL",
    )
    max_concurrent_requests: int = Field(
        default=10, description="Maximum concurrent requests per tenant"
    )


class GenImageTenantManager:
    """Manages multiple GenImage tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, GenImageTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:genImage:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "7"))  # Use DB 7 for GenImage
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

    async def _save_to_redis(self, config: GenImageTenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[GenImageTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return GenImageTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, GenImageTenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[GenImageTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"GENIMAGE_TENANT_{tenant_id.upper()}"

        runware_api_key = os.getenv(f"{prefix}_RUNWARE_API_KEY")
        if not runware_api_key:
            return None

        return GenImageTenantConfig(
            tenant_id=tenant_id,
            runware_api_key=runware_api_key,
            base_url=os.getenv(f"{prefix}_BASE_URL", "https://api.runware.ai/v1"),
            max_concurrent_requests=int(os.getenv(f"{prefix}_MAX_CONCURRENT", "10")),
        )

    async def register_tenant(self, config: GenImageTenantConfig) -> None:
        """Register a tenant and create a Runware client wrapper."""
        # Import here to avoid circular imports
        from .client import GenImageClientWrapper

        # Create client wrapper for this tenant
        wrapper = GenImageClientWrapper(
            api_key=config.runware_api_key,
            semaphore=asyncio.Semaphore(config.max_concurrent_requests),
            base_url=config.base_url,
        )

        # Store the client and config
        self.clients[config.tenant_id] = {
            "client": wrapper,
            "config": config,
            "semaphore": wrapper.semaphore,
        }
        self.configs[config.tenant_id] = config

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> Dict[str, Any]:
        """Get client wrapper and semaphore for a tenant (with concurrency control)."""
        if tenant_id not in self.clients:
            # Try to load from Redis first
            config = await self._load_from_redis(tenant_id)
            if not config:
                # Fall back to environment variables
                config = self.load_tenant_from_env(tenant_id)
            if config:
                await self.register_tenant(config)
            else:
                raise ValueError(
                    f"Tenant '{tenant_id}' not found. Configure it via environment variables or register it programmatically."
                )

        return self.clients[tenant_id]

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
            if key.startswith("GENIMAGE_TENANT_") and key.endswith("_RUNWARE_API_KEY"):
                tenant_id = (
                    key.replace("GENIMAGE_TENANT_", "")
                    .replace("_RUNWARE_API_KEY", "")
                    .lower()
                )
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    await self.register_tenant(config)

    async def close_all(self) -> None:
        """Close all connections and Redis connection."""
        # Close all HTTP clients
        for client_info in self.clients.values():
            wrapper = client_info.get("client")
            if wrapper:
                await wrapper.close()

        self.clients.clear()
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
