"""
AI MCP Tenant Manager

Manages multiple AI tenant connections with GPU-AI API.
Tenant configurations are persisted in Redis for durability across restarts.
Each tenant provides their own API base URL for isolation.
"""

import json
import os
import asyncio
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field
import redis.asyncio as redis


class AITenantConfig(BaseModel):
    """Configuration for a single AI tenant with multi-provider support."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    api_base_url: str = Field(
        default="http://192.168.0.10:8000",
        description="GPU-AI API base URL for this tenant (used for 'global' tenant)",
    )
    api_key: Optional[str] = Field(
        default=None, description="Optional API key for GPU-AI API authentication"
    )
    # Provider-specific API keys (for non-global tenants)
    openrouter_api_key: Optional[str] = Field(
        default=None, description="OpenRouter API key for LLM and STT services"
    )
    elevenlabs_api_key: Optional[str] = Field(
        default=None, description="Eleven Labs API key for TTS service"
    )
    openai_api_key: Optional[str] = Field(
        default=None, description="OpenAI API key for embeddings service"
    )
    timeout: int = Field(
        default=300, description="Request timeout in seconds"
    )
    max_concurrent_requests: int = Field(
        default=10, description="Maximum concurrent requests per tenant"
    )


class AITenantManager:
    """Manages multiple AI tenant connections with Redis persistence."""

    def __init__(self):
        self.clients: Dict[str, Any] = {}
        self.configs: Dict[str, AITenantConfig] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:ai-mcp-server:tenant:"
        self._redis_initialized = False

    async def _init_redis(self) -> None:
        """Initialize Redis connection if not already initialized."""
        if self._redis_initialized:
            return

        try:
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_db = int(os.getenv("REDIS_DB", "8"))  # Use DB 8 for AI MCP Server
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

    async def _save_to_redis(self, config: AITenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[AITenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return AITenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, AITenantConfig]:
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

    def load_tenant_from_env(self, tenant_id: str) -> Optional[AITenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"AI_MCP_SERVER_TENANT_{tenant_id.upper()}"

        api_base_url = os.getenv(f"{prefix}_API_BASE_URL")
        if not api_base_url:
            # Default to the main GPU-AI API
            api_base_url = os.getenv("AI_MCP_SERVER_DEFAULT_API_BASE_URL", "http://192.168.0.10:8000")

        return AITenantConfig(
            tenant_id=tenant_id,
            api_base_url=api_base_url,
            api_key=os.getenv(f"{prefix}_API_KEY"),
            openrouter_api_key=os.getenv(f"{prefix}_OPENROUTER_API_KEY"),
            elevenlabs_api_key=os.getenv(f"{prefix}_ELEVENLABS_API_KEY"),
            openai_api_key=os.getenv(f"{prefix}_OPENAI_API_KEY"),
            timeout=int(os.getenv(f"{prefix}_TIMEOUT", "300")),
            max_concurrent_requests=int(os.getenv(f"{prefix}_MAX_CONCURRENT", "10")),
        )

    async def register_tenant(self, config: AITenantConfig) -> None:
        """Register a tenant and create an AI client wrapper with provider support."""
        # Import here to avoid circular imports
        from .client import AIClientWrapper
        from .providers import OpenRouterClient, ElevenLabsClient, OpenAIClient

        # Create main client wrapper (for GPU-AI API or as fallback)
        wrapper = AIClientWrapper(
            api_base_url=config.api_base_url,
            api_key=config.api_key,
            timeout=config.timeout,
            semaphore=asyncio.Semaphore(config.max_concurrent_requests),
        )

        # Create provider clients for non-global tenants
        providers = {}
        if config.tenant_id != "global":
            if config.openrouter_api_key:
                providers["openrouter"] = OpenRouterClient(
                    api_key=config.openrouter_api_key,
                    timeout=config.timeout,
                )
            if config.elevenlabs_api_key:
                providers["elevenlabs"] = ElevenLabsClient(
                    api_key=config.elevenlabs_api_key,
                    timeout=config.timeout,
                )
            if config.openai_api_key:
                providers["openai"] = OpenAIClient(
                    api_key=config.openai_api_key,
                    timeout=config.timeout,
                )

        # Store the client, providers, and config
        self.clients[config.tenant_id] = {
            "client": wrapper,
            "providers": providers,
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
            if key.startswith("AI_MCP_SERVER_TENANT_") and key.endswith("_API_BASE_URL"):
                tenant_id = (
                    key.replace("AI_MCP_SERVER_TENANT_", "")
                    .replace("_API_BASE_URL", "")
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
        # Close all HTTP clients and providers
        for client_info in self.clients.values():
            wrapper = client_info.get("client")
            if wrapper:
                await wrapper.close()
            
            # Close provider clients
            providers = client_info.get("providers", {})
            for provider_client in providers.values():
                if hasattr(provider_client, "close"):
                    await provider_client.close()

        self.clients.clear()
        self.configs.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
