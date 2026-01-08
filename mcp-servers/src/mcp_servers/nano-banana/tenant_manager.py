"""
Nano Banana Tenant Manager

Manages multiple Nano Banana tenant connections with Gemini API.
Tenant configurations are persisted in Redis for durability across restarts.
Each tenant provides their own Gemini API key for isolation.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis

try:
    from google import genai
except ImportError:
    genai = None


class NanoBananaTenantConfig(BaseModel):
    """Configuration for a single Nano Banana tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    gemini_api_key: str = Field(..., description="Google Gemini API key for this tenant")
    model: str = Field(default="gemini-2.0-flash-exp", description="Gemini model to use")
    max_concurrent_requests: int = Field(default=10, description="Maximum concurrent requests per tenant")


class NanoBananaTenantManager:
    """Manages multiple Nano Banana tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, NanoBananaTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:nano-banana:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "6"))  # Use DB 6 for Nano Banana
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

    async def _save_to_redis(self, config: NanoBananaTenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[NanoBananaTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return NanoBananaTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, NanoBananaTenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[NanoBananaTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"NANO_BANANA_TENANT_{tenant_id.upper()}"
        
        gemini_api_key = os.getenv(f"{prefix}_GEMINI_API_KEY")
        if not gemini_api_key:
            return None
        
        return NanoBananaTenantConfig(
            tenant_id=tenant_id,
            gemini_api_key=gemini_api_key,
            model=os.getenv(f"{prefix}_MODEL", "gemini-2.0-flash-exp"),
            max_concurrent_requests=int(os.getenv(f"{prefix}_MAX_CONCURRENT", "10")),
        )

    async def register_tenant(self, config: NanoBananaTenantConfig) -> None:
        """Register a tenant and create a Gemini client."""
        if genai is None:
            raise ImportError("google-genai package is not installed. Install it with: pip install google-genai")
        
        # Create Gemini client for this tenant
        # Each tenant gets their own client with their API key
        client = genai.Client(api_key=config.gemini_api_key)
        
        # Store the client and config
        self.clients[config.tenant_id] = {
            "client": client,
            "config": config,
            "semaphore": asyncio.Semaphore(config.max_concurrent_requests),
        }
        self.configs[config.tenant_id] = config

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> Dict[str, Any]:
        """Get client and semaphore for a tenant (with concurrency control)."""
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
            if key.startswith("NANO_BANANA_TENANT_") and key.endswith("_GEMINI_API_KEY"):
                tenant_id = key.replace("NANO_BANANA_TENANT_", "").replace("_GEMINI_API_KEY", "").lower()
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    await self.register_tenant(config)

    async def close_all(self) -> None:
        """Close all connections and Redis connection."""
        # Gemini clients don't need explicit cleanup, but we clear references
        self.clients.clear()
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False

