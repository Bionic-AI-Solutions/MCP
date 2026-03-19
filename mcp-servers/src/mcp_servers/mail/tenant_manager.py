"""
Mail Tenant Manager

Manages multiple mail service tenant connections.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
from typing import Optional, Dict

from pydantic import BaseModel, Field
import redis.asyncio as redis
from mcp_servers.common.config_loader import load_tenant_configs_from_file
import httpx


class MailTenantConfig(BaseModel):
    """Configuration for a single mail service tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    api_key: str = Field(..., description="JWT token for mail API authentication")
    mail_api_url: str = Field(
        default="http://mail-service.mail",
        description="Base URL for mail service (default: Kubernetes internal DNS)",
    )
    default_from_email: Optional[str] = Field(
        default=None, description="Default sender email address"
    )
    default_from_name: Optional[str] = Field(
        default=None, description="Default sender name"
    )


class MailTenantManager:
    """Manages multiple mail service tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, httpx.AsyncClient] = {}
        self.configs: Dict[str, MailTenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:mail:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "6"))  # Use DB 6 for Mail
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

    async def _save_to_redis(self, config: MailTenantConfig) -> None:
        """Save tenant configuration to Redis."""
        await self._init_redis()
        if not self.redis_client:
            return

        try:
            key = f"{self.redis_key_prefix}{config.tenant_id}"
            # Store as JSON (api_key will be in plain text - consider encryption for production)
            config_dict = config.model_dump()
            await self.redis_client.set(key, json.dumps(config_dict))
        except Exception as e:
            print(f"Warning: Failed to save tenant config to Redis: {e}")

    async def _load_from_redis(self, tenant_id: str) -> Optional[MailTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return MailTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, MailTenantConfig]:
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

    def _load_tenants_from_config_file(self) -> Dict[str, MailTenantConfig]:
        """Load tenant configurations from the mounted JSON config file."""
        raw_configs = load_tenant_configs_from_file()
        configs = {}
        for tenant_id, raw in raw_configs.items():
            try:
                raw["tenant_id"] = tenant_id
                configs[tenant_id] = MailTenantConfig(**raw)
            except Exception as e:
                print(f"Warning: Invalid config for tenant '{tenant_id}' in config file: {e}")
        return configs

    def load_tenant_from_env(self, tenant_id: str) -> Optional[MailTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"MAIL_TENANT_{tenant_id.upper()}"
        api_key = os.getenv(f"{prefix}_API_KEY")
        if not api_key:
            return None

        return MailTenantConfig(
            tenant_id=tenant_id,
            api_key=api_key,
            mail_api_url=os.getenv(
                f"{prefix}_MAIL_API_URL", "http://mail-service.mail"
            ),
            default_from_email=os.getenv(f"{prefix}_DEFAULT_FROM_EMAIL"),
            default_from_name=os.getenv(f"{prefix}_DEFAULT_FROM_NAME"),
        )

    async def register_tenant(self, config: MailTenantConfig) -> None:
        """Register a tenant and create an HTTP client."""
        # Create HTTP client with JWT authentication
        headers = {"Authorization": f"Bearer {config.api_key}"}
        client = httpx.AsyncClient(
            base_url=config.mail_api_url,
            headers=headers,
            timeout=30.0,
        )
        self.clients[config.tenant_id] = client
        self.configs[config.tenant_id] = config

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_client(self, tenant_id: str) -> httpx.AsyncClient:
        """Get HTTP client for a tenant."""
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
        tenant_ids = set()
        for key in os.environ:
            if key.startswith("MAIL_TENANT_") and key.endswith("_API_KEY"):
                tenant_id = (
                    key.replace("MAIL_TENANT_", "").replace("_API_KEY", "").lower()
                )
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
        """Close all HTTP clients and Redis connection."""
        # Close all HTTP clients
        for client in self.clients.values():
            await client.aclose()
        self.clients.clear()

        # Close Redis connection
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False

