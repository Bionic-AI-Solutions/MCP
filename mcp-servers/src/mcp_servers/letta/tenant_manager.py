"""
Letta Tenant Manager

Manages multiple Letta AI agent platform connections.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis
import httpx

from mcp_servers.common.config_loader import load_tenant_configs_from_file


class LettaTenantConfig(BaseModel):
    """Configuration for a single Letta tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    base_url: str = Field(..., description="Letta API base URL (e.g., 'http://letta:8283' or 'https://letta.example.com/v1')")
    password: Optional[str] = Field(default=None, description="Letta API password/token for Bearer auth")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_concurrency: int = Field(default=5, description="Max concurrent requests per tenant")
    graphiti_url: Optional[str] = Field(
        default=None,
        description="Graphiti temporal memory service URL (e.g., 'http://graphiti-service:8200')",
    )
    org_identity_id: Optional[str] = Field(
        default=None,
        description="Letta org identity UUID for tenant isolation. Auto-created during registration if not provided.",
    )


class LettaTenantManager:
    """Manages multiple Letta tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, Dict[str, Any]] = {}
        self.configs: Dict[str, LettaTenantConfig] = {}
        self.graphiti_clients: Dict[str, httpx.AsyncClient] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:letta:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "10"))
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

    async def _save_to_redis(self, config: LettaTenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[LettaTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return LettaTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, LettaTenantConfig]:
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

    def _load_tenants_from_config_file(self) -> Dict[str, LettaTenantConfig]:
        """Load tenant configurations from the mounted JSON config file."""
        raw_configs = load_tenant_configs_from_file()
        configs = {}
        for tenant_id, raw in raw_configs.items():
            try:
                raw["tenant_id"] = tenant_id
                configs[tenant_id] = LettaTenantConfig(**raw)
            except Exception as e:
                print(f"Warning: Invalid config for tenant '{tenant_id}' in config file: {e}")
        return configs

    def load_tenant_from_env(self, tenant_id: str) -> Optional[LettaTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"LETTA_TENANT_{tenant_id.upper()}"

        base_url = os.getenv(f"{prefix}_BASE_URL")
        if not base_url:
            return None

        graphiti_url = os.getenv(f"{prefix}_GRAPHITI_URL")
        org_identity_id = os.getenv(f"{prefix}_ORG_IDENTITY_ID")

        return LettaTenantConfig(
            tenant_id=tenant_id,
            base_url=base_url.rstrip("/"),
            password=os.getenv(f"{prefix}_PASSWORD"),
            timeout=int(os.getenv(f"{prefix}_TIMEOUT", "30")),
            max_concurrency=int(os.getenv(f"{prefix}_MAX_CONCURRENCY", "5")),
            graphiti_url=graphiti_url.rstrip("/") if graphiti_url else None,
            org_identity_id=org_identity_id,
        )

    async def register_tenant(self, config: LettaTenantConfig) -> Dict[str, Any]:
        """Register a tenant and create an HTTP client for the Letta API."""
        headers = {"Content-Type": "application/json"}
        if config.password:
            headers["Authorization"] = f"Bearer {config.password}"

        client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True,
        )

        # Test connection with a health check
        try:
            resp = await client.get("/v1/health")
            if resp.status_code != 200:
                # Try alternate health endpoint
                resp = await client.get("/api/health")
                if resp.status_code != 200:
                    await client.aclose()
                    return {
                        "success": False,
                        "error": f"Letta health check failed with status {resp.status_code}: {resp.text[:200]}",
                    }
        except httpx.ConnectError as e:
            await client.aclose()
            return {"success": False, "error": f"Cannot connect to Letta at {config.base_url}: {str(e)}"}
        except Exception as e:
            await client.aclose()
            return {"success": False, "error": f"Health check error: {str(e)}"}

        # Ensure org identity for tenant isolation
        if not config.org_identity_id:
            try:
                identifier_key = f"mcp-tenant-{config.tenant_id}"
                identity_body = {
                    "identifier_key": identifier_key,
                    "name": f"MCP Tenant: {config.tenant_id}",
                    "identity_type": "org",
                }
                # Try create first, then upsert if already exists
                resp = await client.post("/v1/identities", json=identity_body)
                if resp.status_code == 409:
                    # Already exists — upsert to get the existing identity
                    resp = await client.put("/v1/identities", json=identity_body)
                if resp.status_code < 400:
                    identity_data = resp.json()
                    config.org_identity_id = identity_data.get("id")
                    print(f"Tenant '{config.tenant_id}': org identity created -> {config.org_identity_id}")
                else:
                    print(f"Warning: Failed to create org identity for tenant '{config.tenant_id}': "
                          f"{resp.status_code} {resp.text[:200]}")
            except Exception as e:
                print(f"Warning: Org identity creation failed for tenant '{config.tenant_id}': {e}")
        else:
            print(f"Tenant '{config.tenant_id}': using pre-configured org identity -> {config.org_identity_id}")

        semaphore = asyncio.Semaphore(config.max_concurrency)
        self.clients[config.tenant_id] = {
            "client": client,
            "semaphore": semaphore,
            "config": config,
        }
        self.configs[config.tenant_id] = config

        await self._save_to_redis(config)
        return {"success": True}

    async def get_client(self, tenant_id: str) -> Dict[str, Any]:
        """Get client info dict for a tenant (client, semaphore, config)."""
        if tenant_id not in self.clients:
            config = await self._load_from_redis(tenant_id)
            if not config:
                config = self.load_tenant_from_env(tenant_id)
            if config:
                result = await self.register_tenant(config)
                if not result.get("success"):
                    raise ValueError(result.get("error", "Failed to register tenant"))
            else:
                raise ValueError(
                    f"Tenant '{tenant_id}' not found. Register it via lt_register_tenant first."
                )
        return self.clients[tenant_id]

    async def get_graphiti_client(self, tenant_id: str) -> httpx.AsyncClient:
        """Get or create an httpx client for the Graphiti temporal memory service."""
        if tenant_id in self.graphiti_clients:
            return self.graphiti_clients[tenant_id]

        config = self.configs.get(tenant_id)
        if not config:
            config = await self._load_from_redis(tenant_id)
            if not config:
                config = self.load_tenant_from_env(tenant_id)
        if not config or not config.graphiti_url:
            raise ValueError(
                f"Tenant '{tenant_id}' has no graphiti_url configured. "
                "Re-register with graphiti_url to enable temporal memory."
            )

        client = httpx.AsyncClient(
            base_url=config.graphiti_url.rstrip("/"),
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True,
        )
        self.graphiti_clients[tenant_id] = client
        return client

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
            if key.startswith("LETTA_TENANT_") and key.endswith("_BASE_URL"):
                tid = key.replace("LETTA_TENANT_", "").replace("_BASE_URL", "").lower()
                tenant_ids.add(tid)

        for tid in tenant_ids:
            if tid not in self.configs:
                config = self.load_tenant_from_env(tid)
                if config:
                    try:
                        await self.register_tenant(config)
                    except Exception as e:
                        print(f"Warning: Env tenant '{tid}' failed: {e}")

    async def close_all(self) -> None:
        """Close all HTTP clients and Redis connection."""
        for info in self.clients.values():
            try:
                await info["client"].aclose()
            except Exception:
                pass

        for client in self.graphiti_clients.values():
            try:
                await client.aclose()
            except Exception:
                pass

        self.clients.clear()
        self.graphiti_clients.clear()
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
