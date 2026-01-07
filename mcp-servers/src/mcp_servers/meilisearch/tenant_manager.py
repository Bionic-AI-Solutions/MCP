"""
MeiliSearch Tenant Manager

Manages multiple MeiliSearch tenant connections.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis

try:
    from meilisearch import Client as MeiliSearchClient
except ImportError:
    MeiliSearchClient = None


class MeiliSearchTenantConfig(BaseModel):
    """Configuration for a single MeiliSearch tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    url: str = Field(..., description="MeiliSearch server URL (e.g., 'http://meilisearch.meilisearch:7700')")
    api_key: Optional[str] = Field(default=None, description="MeiliSearch API key (master key or search key)")
    timeout: int = Field(default=5, description="Request timeout in seconds")


class MeiliSearchTenantManager:
    """Manages multiple MeiliSearch tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, MeiliSearchTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:meilisearch:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "5"))  # Use DB 5 for MeiliSearch
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

    async def _save_to_redis(self, config: MeiliSearchTenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[MeiliSearchTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return MeiliSearchTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, MeiliSearchTenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[MeiliSearchTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"MEILISEARCH_TENANT_{tenant_id.upper()}"
        
        url = os.getenv(f"{prefix}_URL")
        if not url:
            return None
        
        return MeiliSearchTenantConfig(
            tenant_id=tenant_id,
            url=url,
            api_key=os.getenv(f"{prefix}_API_KEY"),
            timeout=int(os.getenv(f"{prefix}_TIMEOUT", "5")),
        )

    async def register_tenant(self, config: MeiliSearchTenantConfig) -> None:
        """Register a tenant and create a MeiliSearch client."""
        if MeiliSearchClient is None:
            raise ImportError("meilisearch package is not installed. Install it with: pip install meilisearch")
        
        # Create MeiliSearch client
        client = MeiliSearchClient(
            url=config.url,
            api_key=config.api_key,
            timeout=config.timeout,
        )
        
        # Store the client
        self.clients[config.tenant_id] = client
        self.configs[config.tenant_id] = config

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> Any:
        """Get client/connection for a tenant."""
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
            if key.startswith("MEILISEARCH_TENANT_") and key.endswith("_URL"):
                tenant_id = key.replace("MEILISEARCH_TENANT_", "").replace("_URL", "").lower()
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    await self.register_tenant(config)

    async def close_all(self) -> None:
        """Close all connections and Redis connection."""
        # Close your service clients/connections here
        # Example:
        # for client in self.clients.values():
        #     await client.close()
        # for connection in self.connections.values():
        #     await connection.close()
        
        self.clients.clear()
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False

