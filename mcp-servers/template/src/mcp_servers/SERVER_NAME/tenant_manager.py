"""
SERVER_NAME Tenant Manager

Manages multiple SERVER_NAME tenant connections.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
from typing import Any, Optional, Dict
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field
import redis.asyncio as redis

from mcp_servers.common.config_loader import load_tenant_configs_from_file

# Import your service client library here
# Example:
# from your_service_library import Client
# import httpx


class SERVER_NAMETenantConfig(BaseModel):
    """Configuration for a single SERVER_NAME tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    
    # Add your tenant configuration fields here
    # Example for API-based service:
    # api_key: str = Field(..., description="API key for authentication")
    # api_url: str = Field(..., description="API base URL")
    # timeout: int = Field(default=30, description="Request timeout in seconds")
    
    # Example for database service:
    # host: str = Field(..., description="Database host")
    # port: int = Field(default=5432, description="Database port")
    # database: str = Field(..., description="Database name")
    # user: str = Field(..., description="Username")
    # password: str = Field(..., description="Password")
    # ssl: bool = Field(default=False, description="Use SSL/TLS")
    
    # Example for connection pooling:
    # min_pool_size: int = Field(default=2, description="Minimum connection pool size")
    # max_pool_size: int = Field(default=10, description="Maximum connection pool size")


class SERVER_NAMETenantManager:
    """Manages multiple SERVER_NAME tenant connections with Redis persistence."""

    def __init__(self):
        # Store your tenant clients/connections here
        # Example:
        # self.clients: Dict[str, Client] = {}
        # self.connections: Dict[str, Connection] = {}
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, SERVER_NAMETenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:SERVER_NAME:tenant:"
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

    async def _save_to_redis(self, config: SERVER_NAMETenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[SERVER_NAMETenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return SERVER_NAMETenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, SERVER_NAMETenantConfig]:
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

    def _load_tenants_from_config_file(self) -> Dict[str, SERVER_NAMETenantConfig]:
        """Load tenant configurations from the mounted JSON config file."""
        raw_configs = load_tenant_configs_from_file()
        configs = {}
        for tenant_id, raw in raw_configs.items():
            try:
                raw["tenant_id"] = tenant_id
                configs[tenant_id] = SERVER_NAMETenantConfig(**raw)
            except Exception as e:
                print(f"Warning: Invalid config for tenant '{tenant_id}' in config file: {e}")
        return configs

    def load_tenant_from_env(self, tenant_id: str) -> Optional[SERVER_NAMETenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"SERVER_NAME_TENANT_{tenant_id.upper()}"
        
        # Check if tenant is configured via environment variables
        # Example:
        # api_key = os.getenv(f"{prefix}_API_KEY")
        # if not api_key:
        #     return None
        
        # return SERVER_NAMETenantConfig(
        #     tenant_id=tenant_id,
        #     api_key=api_key,
        #     api_url=os.getenv(f"{prefix}_API_URL", ""),
        #     timeout=int(os.getenv(f"{prefix}_TIMEOUT", "30")),
        # )
        
        # For now, return None - implement based on your needs
        return None

    async def register_tenant(self, config: SERVER_NAMETenantConfig) -> None:
        """Register a tenant and create a client/connection."""
        # Create your service client/connection here
        # Example for API client:
        # client = Client(
        #     api_key=config.api_key,
        #     base_url=config.api_url,
        #     timeout=config.timeout,
        # )
        
        # Example for database connection:
        # connection = create_connection(
        #     host=config.host,
        #     port=config.port,
        #     database=config.database,
        #     user=config.user,
        #     password=config.password,
        #     ssl=config.ssl,
        # )
        
        # Store the client/connection
        # self.clients[config.tenant_id] = client
        # self.connections[config.tenant_id] = connection
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

        # 3. Load from environment variables (legacy fallback)
        # Adjust the suffix ("_API_KEY") based on your config's primary anchor field
        tenant_ids = set()
        for key in os.environ:
            if key.startswith("SERVER_NAME_TENANT_") and key.endswith("_API_KEY"):
                tenant_id = key.replace("SERVER_NAME_TENANT_", "").replace("_API_KEY", "").lower()
                tenant_ids.add(tenant_id)

        for tenant_id in tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    try:
                        await self.register_tenant(config)
                    except Exception as e:
                        print(f"Warning: Env tenant '{tenant_id}' failed: {e}")

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

