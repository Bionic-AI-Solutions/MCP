"""
Redis Tenant Manager

Manages multiple Redis tenant connections.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any

import redis.asyncio as redis
from pydantic import BaseModel, Field


class RedisTenantConfig(BaseModel):
    """Configuration for a single Redis tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    host: str = Field(..., description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    password: Optional[str] = Field(default=None, description="Redis password")
    db: int = Field(default=0, description="Redis database number (0-15)")
    ssl: bool = Field(default=False, description="Use SSL/TLS")
    decode_responses: bool = Field(default=True, description="Decode responses as strings")
    max_concurrent_requests: int = Field(
        default=100, description="Maximum concurrent requests per tenant"
    )


class RedisTenantManager:
    """Manages multiple Redis tenant connections with concurrency control and Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, redis.Redis] = {}
        self.configs: Dict[str, RedisTenantConfig] = {}
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:redis:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "4"))  # Use DB 4 for Redis MCP server
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

    async def _save_to_redis(self, config: RedisTenantConfig) -> None:
        """Save tenant configuration to Redis."""
        await self._init_redis()
        if not self.redis_client:
            return

        try:
            key = f"{self.redis_key_prefix}{config.tenant_id}"
            # Store as JSON (password will be in plain text - consider encryption for production)
            config_dict = config.model_dump()
            await self.redis_client.set(key, json.dumps(config_dict))
        except Exception as e:
            print(f"Warning: Failed to save tenant config to Redis: {e}")

    async def _load_from_redis(self, tenant_id: str) -> Optional[RedisTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return RedisTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, RedisTenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[RedisTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"REDIS_TENANT_{tenant_id.upper()}"
        host = os.getenv(f"{prefix}_HOST")
        if not host:
            return None

        password = os.getenv(f"{prefix}_PASSWORD")
        return RedisTenantConfig(
            tenant_id=tenant_id,
            host=host,
            port=int(os.getenv(f"{prefix}_PORT", "6379")),
            password=password if password else None,
            db=int(os.getenv(f"{prefix}_DB", "0")),
            ssl=os.getenv(f"{prefix}_SSL", "false").lower() == "true",
            decode_responses=os.getenv(f"{prefix}_DECODE_RESPONSES", "true").lower() == "true",
            max_concurrent_requests=int(os.getenv(f"{prefix}_MAX_CONCURRENT", "100")),
        )

    async def register_tenant(self, config: RedisTenantConfig) -> None:
        """Register a tenant and create a Redis client with concurrency control."""
        client = redis.Redis(
            host=config.host,
            port=config.port,
            password=config.password,
            db=config.db,
            ssl=config.ssl,
            decode_responses=config.decode_responses,
        )
        # Test connection
        await client.ping()
        
        self.clients[config.tenant_id] = client
        self.configs[config.tenant_id] = config
        
        # Create semaphore for concurrency control
        self.semaphores[config.tenant_id] = asyncio.Semaphore(config.max_concurrent_requests)

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> Dict[str, Any]:
        """Get client info (Redis client and semaphore) for a tenant (with concurrency control)."""
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

        return {
            "client": self.clients[tenant_id],
            "semaphore": self.semaphores[tenant_id],
            "config": self.configs[tenant_id],
        }

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
            if key.startswith("REDIS_TENANT_") and key.endswith("_HOST"):
                tenant_id = key.replace("REDIS_TENANT_", "").replace("_HOST", "").lower()
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    await self.register_tenant(config)

    async def close_all(self) -> None:
        """Close all Redis connections."""
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()
        self.configs.clear()
        self.semaphores.clear()
        
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
