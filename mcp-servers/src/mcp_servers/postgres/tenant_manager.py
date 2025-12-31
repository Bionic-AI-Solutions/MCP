"""
PostgreSQL Tenant Manager

Manages multiple PostgreSQL tenant connections with connection pooling.
"""

import os
from typing import Optional, Dict
from contextlib import asynccontextmanager

import psycopg
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field


class PostgresTenantConfig(BaseModel):
    """Configuration for a single PostgreSQL tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    host: str = Field(..., description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    database: str = Field(..., description="Database name")
    user: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    min_pool_size: int = Field(default=2, description="Minimum connection pool size")
    max_pool_size: int = Field(default=10, description="Maximum connection pool size")
    ssl: bool = Field(default=False, description="Use SSL/TLS")

    def get_connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        ssl_mode = "require" if self.ssl else "disable"
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/"
            f"{self.database}?sslmode={ssl_mode}"
        )


class PostgresTenantManager:
    """Manages multiple PostgreSQL tenant connections with pooling."""

    def __init__(self):
        self.pools: Dict[str, AsyncConnectionPool] = {}
        self.configs: Dict[str, PostgresTenantConfig] = {}

    def load_tenant_from_env(self, tenant_id: str) -> Optional[PostgresTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"POSTGRES_TENANT_{tenant_id.upper()}"
        host = os.getenv(f"{prefix}_HOST")
        if not host:
            return None

        return PostgresTenantConfig(
            tenant_id=tenant_id,
            host=host,
            port=int(os.getenv(f"{prefix}_PORT", "5432")),
            database=os.getenv(f"{prefix}_DB", os.getenv(f"{prefix}_DATABASE", "")),
            user=os.getenv(f"{prefix}_USER", "postgres"),
            password=os.getenv(f"{prefix}_PASSWORD", ""),
            min_pool_size=int(os.getenv(f"{prefix}_MIN_POOL_SIZE", "2")),
            max_pool_size=int(os.getenv(f"{prefix}_MAX_POOL_SIZE", "10")),
            ssl=os.getenv(f"{prefix}_SSL", "false").lower() == "true",
        )

    async def register_tenant(self, config: PostgresTenantConfig) -> None:
        """Register a tenant and create a connection pool."""
        if config.tenant_id in self.pools:
            # Close existing pool
            await self.pools[config.tenant_id].close()

        # Create new connection pool
        pool = AsyncConnectionPool(
            config.get_connection_string(),
            min_size=config.min_pool_size,
            max_size=config.max_pool_size,
            open=False,
        )
        await pool.open()
        self.pools[config.tenant_id] = pool
        self.configs[config.tenant_id] = config

    async def get_pool(self, tenant_id: str) -> AsyncConnectionPool:
        """Get connection pool for a tenant."""
        if tenant_id not in self.pools:
            # Try to load from environment
            config = self.load_tenant_from_env(tenant_id)
            if config:
                await self.register_tenant(config)
            else:
                raise ValueError(f"Tenant '{tenant_id}' not found. Configure it via environment variables.")

        return self.pools[tenant_id]

    @asynccontextmanager
    async def get_connection(self, tenant_id: str):
        """Get a connection from the tenant's pool."""
        pool = await self.get_pool(tenant_id)
        async with pool.connection() as conn:
            yield conn

    async def close_all(self) -> None:
        """Close all connection pools."""
        for pool in self.pools.values():
            await pool.close()
        self.pools.clear()
        self.configs.clear()

