"""
PostgreSQL Tenant Manager

Manages multiple PostgreSQL tenant connections with connection pooling.
Tenant configurations are persisted in Redis for durability across restarts.
"""

import json
import os
import time
import uuid
import asyncio
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import psycopg
from psycopg import sql
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field
import redis.asyncio as redis

from mcp_servers.common.config_loader import load_tenant_configs_from_file


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
    max_concurrent_requests: int = Field(
        default=100, description="Maximum concurrent requests per tenant"
    )

    def get_connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        from urllib.parse import quote_plus
        ssl_mode = "require" if self.ssl else "disable"
        return (
            f"postgresql://{quote_plus(self.user)}:{quote_plus(self.password)}@{self.host}:{self.port}/"
            f"{self.database}?sslmode={ssl_mode}"
        )


@dataclass
class ActiveTransaction:
    """Tracks a pinned connection for a multi-statement transaction."""

    transaction_id: str
    tenant_id: str
    connection: psycopg.AsyncConnection
    created_at: float  # time.monotonic()
    last_activity: float  # time.monotonic(), updated on each use
    timeout_seconds: float


class PostgresTenantManager:
    """Manages multiple PostgreSQL tenant connections with pooling, concurrency control, and Redis persistence."""

    def __init__(self):
        self.pools: Dict[str, AsyncConnectionPool] = {}
        self.configs: Dict[str, PostgresTenantConfig] = {}
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.redis_client: Optional[redis.Redis] = None
        self.redis_key_prefix = "mcp:postgres:tenant:"
        self._redis_initialized = False
        # Transaction management
        self._active_transactions: Dict[str, ActiveTransaction] = {}
        self._tx_lock: asyncio.Lock = asyncio.Lock()
        self._reaper_task: Optional[asyncio.Task] = None

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

    async def _save_to_redis(self, config: PostgresTenantConfig) -> None:
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

    async def _load_from_redis(self, tenant_id: str) -> Optional[PostgresTenantConfig]:
        """Load tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return None

        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            config_json = await self.redis_client.get(key)
            if config_json:
                config_dict = json.loads(config_json)
                return PostgresTenantConfig(**config_dict)
        except Exception as e:
            print(f"Warning: Failed to load tenant config from Redis: {e}")
        return None

    async def _load_all_from_redis(self) -> Dict[str, PostgresTenantConfig]:
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

    def _load_tenants_from_config_file(self) -> Dict[str, PostgresTenantConfig]:
        """Load tenant configurations from the mounted JSON config file."""
        raw_configs = load_tenant_configs_from_file()
        configs = {}
        for tenant_id, raw in raw_configs.items():
            try:
                raw["tenant_id"] = tenant_id
                configs[tenant_id] = PostgresTenantConfig(**raw)
            except Exception as e:
                print(f"Warning: Invalid config for tenant '{tenant_id}' in config file: {e}")
        return configs

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
            max_concurrent_requests=int(os.getenv(f"{prefix}_MAX_CONCURRENT", "100")),
        )

    async def register_tenant(self, config: PostgresTenantConfig) -> None:
        """Register a tenant and create a connection pool with concurrency control.

        Validates connectivity by opening a test connection before committing
        the pool. If the connection fails, the pool is closed and the tenant
        is not registered.
        """
        # Create new connection pool with health checks and idle timeout.
        # max_idle=30 recycles connections before HAProxy's 50s timeout kills them.
        # check=AsyncConnectionPool.check_connection validates connections before use.
        pool = AsyncConnectionPool(
            config.get_connection_string(),
            min_size=config.min_pool_size,
            max_size=config.max_pool_size,
            max_idle=30.0,
            check=AsyncConnectionPool.check_connection,
            open=False,
        )

        try:
            await pool.open()
            # Validate with an actual connection before committing
            async with pool.connection(timeout=10) as conn:
                await conn.execute("SELECT 1")
        except Exception as e:
            # Connection failed — close the pool and don't register
            print(
                f"ERROR: Tenant '{config.tenant_id}' failed to connect to "
                f"{config.host}:{config.port}/{config.database}: {e}"
            )
            try:
                await pool.close()
            except Exception:
                pass
            raise

        # Connection validated — close any previous pool for this tenant
        if config.tenant_id in self.pools:
            try:
                await self.pools[config.tenant_id].close()
            except Exception:
                pass

        self.pools[config.tenant_id] = pool
        self.configs[config.tenant_id] = config

        # Create semaphore for concurrency control
        self.semaphores[config.tenant_id] = asyncio.Semaphore(config.max_concurrent_requests)

        # Persist to Redis
        await self._save_to_redis(config)

    async def get_pool(self, tenant_id: str) -> AsyncConnectionPool:
        """Get connection pool for a tenant."""
        if tenant_id not in self.pools:
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

        return self.pools[tenant_id]
    
    async def get_client(self, tenant_id: str) -> Dict[str, Any]:
        """Get client info (pool and semaphore) for a tenant (with concurrency control)."""
        if tenant_id not in self.pools:
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
            "pool": self.pools[tenant_id],
            "semaphore": self.semaphores[tenant_id],
            "config": self.configs[tenant_id],
        }

    @asynccontextmanager
    async def get_connection(
        self,
        tenant_id: str,
        role: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ):
        """Get a connection from the tenant's pool with concurrency control.

        Args:
            tenant_id: Tenant identifier.
            role: Optional PostgreSQL role to assume via SET ROLE for this
                connection. The tenant's primary database user must be a member
                of this role (use GRANT <role> TO <user>). Roles can be created
                on the fly via pg_execute_query. RESET ROLE is always executed
                before the connection is returned to the pool.
            transaction_id: If provided, uses the pinned connection from an
                active transaction instead of checking out from the pool.
        """
        if transaction_id:
            # Use the pinned transaction connection
            conn = await self.get_transaction_connection(transaction_id, tenant_id)
            if role:
                await conn.execute(
                    sql.SQL("SET ROLE {}").format(sql.Identifier(role))
                )
                try:
                    yield conn
                finally:
                    await conn.execute(sql.SQL("RESET ROLE"))
            else:
                yield conn
        else:
            # Original behavior: checkout from pool
            client_info = await self.get_client(tenant_id)
            pool = client_info["pool"]
            semaphore = client_info["semaphore"]

            async with semaphore:
                async with pool.connection() as conn:
                    if role:
                        await conn.execute(
                            sql.SQL("SET ROLE {}").format(sql.Identifier(role))
                        )
                        try:
                            yield conn
                        finally:
                            await conn.execute(sql.SQL("RESET ROLE"))
                    else:
                        yield conn

    # ========================================================================
    # Transaction Management
    # ========================================================================

    async def begin_transaction(
        self, tenant_id: str, timeout_seconds: float = 30.0
    ) -> str:
        """Begin a multi-statement transaction by pinning a connection.

        Checks out a connection from the pool, executes BEGIN, and stores it
        under a unique transaction_id. The connection is held until
        end_transaction() is called or the timeout reaper rolls it back.

        The semaphore is acquired and held for the transaction's duration,
        so active transactions count against the tenant's concurrency limit.
        """
        client_info = await self.get_client(tenant_id)
        pool = client_info["pool"]
        semaphore = client_info["semaphore"]
        config = client_info["config"]

        # Prevent transactions from starving the pool
        max_tx = config.max_pool_size // 2 or 1
        async with self._tx_lock:
            tenant_tx_count = sum(
                1 for tx in self._active_transactions.values()
                if tx.tenant_id == tenant_id
            )
            if tenant_tx_count >= max_tx:
                raise RuntimeError(
                    f"Tenant '{tenant_id}' has reached the maximum of {max_tx} "
                    f"concurrent transactions (max_pool_size={config.max_pool_size})."
                )

        # Acquire semaphore (held for transaction duration)
        await semaphore.acquire()

        try:
            conn = await pool.getconn(timeout=10.0)
            await conn.execute("BEGIN")

            transaction_id = uuid.uuid4().hex
            now = time.monotonic()

            async with self._tx_lock:
                self._active_transactions[transaction_id] = ActiveTransaction(
                    transaction_id=transaction_id,
                    tenant_id=tenant_id,
                    connection=conn,
                    created_at=now,
                    last_activity=now,
                    timeout_seconds=timeout_seconds,
                )

            return transaction_id
        except Exception:
            semaphore.release()
            raise

    async def get_transaction_connection(
        self, transaction_id: str, tenant_id: str
    ) -> psycopg.AsyncConnection:
        """Get the pinned connection for an active transaction.

        Verifies tenant ownership and checks that the connection is still alive.
        Updates last_activity to prevent timeout reaping.
        """
        async with self._tx_lock:
            tx = self._active_transactions.get(transaction_id)
            if tx is None:
                raise ValueError(
                    f"Transaction '{transaction_id}' not found. "
                    "It may have timed out or already been committed/rolled back."
                )

            # Security: prevent cross-tenant access
            if tx.tenant_id != tenant_id:
                raise ValueError(
                    f"Transaction '{transaction_id}' belongs to tenant "
                    f"'{tx.tenant_id}', not '{tenant_id}'."
                )

            # Check if connection is still alive
            if tx.connection.closed:
                self._active_transactions.pop(transaction_id)
                self.semaphores[tx.tenant_id].release()
                raise ConnectionError(
                    f"Transaction '{transaction_id}' connection was lost. "
                    "The transaction has been discarded."
                )

            tx.last_activity = time.monotonic()
            return tx.connection

    async def end_transaction(
        self, transaction_id: str, action: str = "commit"
    ) -> None:
        """Commit or rollback a transaction and return the connection to the pool."""
        async with self._tx_lock:
            tx = self._active_transactions.pop(transaction_id, None)

        if tx is None:
            raise ValueError(
                f"Transaction '{transaction_id}' not found. "
                "It may have timed out or already been committed/rolled back."
            )

        try:
            if action == "commit":
                await tx.connection.execute("COMMIT")
            else:
                await tx.connection.execute("ROLLBACK")
        finally:
            # Always return connection to pool and release semaphore
            pool = self.pools[tx.tenant_id]
            await pool.putconn(tx.connection)
            self.semaphores[tx.tenant_id].release()

    async def _start_reaper(self) -> None:
        """Start background task that auto-rollbacks timed-out transactions."""
        self._reaper_task = asyncio.create_task(self._reaper_loop())

    async def _reaper_loop(self) -> None:
        """Periodically check for and clean up timed-out transactions."""
        while True:
            try:
                await asyncio.sleep(5.0)
                await self._reap_expired_transactions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Warning: Transaction reaper error: {e}")

    async def _reap_expired_transactions(self) -> None:
        """Roll back all transactions that have exceeded their timeout."""
        now = time.monotonic()
        expired_ids = []

        async with self._tx_lock:
            for tx_id, tx in self._active_transactions.items():
                if now - tx.last_activity > tx.timeout_seconds:
                    expired_ids.append(tx_id)

        for tx_id in expired_ids:
            print(f"Warning: Auto-rolling back timed-out transaction '{tx_id}'")
            try:
                await self.end_transaction(tx_id, action="rollback")
            except Exception as e:
                print(f"Warning: Failed to rollback timed-out transaction '{tx_id}': {e}")

    async def _remove_from_redis(self, tenant_id: str) -> None:
        """Remove a tenant configuration from Redis."""
        await self._init_redis()
        if not self.redis_client:
            return
        try:
            key = f"{self.redis_key_prefix}{tenant_id}"
            await self.redis_client.delete(key)
        except Exception as e:
            print(f"Warning: Failed to remove tenant '{tenant_id}' from Redis: {e}")

    async def initialize(self) -> None:
        """Initialize tenant manager - load all tenants from Redis, config file, and environment.

        Loading priority (later sources fill gaps, not overwrite):
        1. Redis persistence (restored from previous runs)
        2. Config file (/etc/mcp/tenants.json from K8s Secret volume)
        3. Environment variables (legacy fallback for local dev / docker-compose)

        Tenants that fail to connect are skipped (and removed from Redis if stale)
        so one bad config does not block the entire server.
        """
        # Collect env-var and config-file tenant IDs for stale detection
        env_tenant_ids = set()
        for key in os.environ:
            if key.startswith("POSTGRES_TENANT_") and key.endswith("_HOST"):
                tid = key.replace("POSTGRES_TENANT_", "").replace("_HOST", "").lower()
                env_tenant_ids.add(tid)

        file_configs = self._load_tenants_from_config_file()
        known_tenant_ids = env_tenant_ids | set(file_configs.keys())

        # 1. Load all from Redis
        redis_configs = await self._load_all_from_redis()
        for config in redis_configs.values():
            try:
                await self.register_tenant(config)
            except Exception as e:
                print(
                    f"Warning: Skipping Redis tenant '{config.tenant_id}' "
                    f"({config.host}:{config.port}/{config.database}): {e}"
                )
                if config.tenant_id not in known_tenant_ids:
                    print(f"  -> Removing stale tenant '{config.tenant_id}' from Redis")
                    await self._remove_from_redis(config.tenant_id)

        # 2. Load from config file (fills gaps not covered by Redis)
        for tenant_id, config in file_configs.items():
            if tenant_id not in self.configs:
                try:
                    await self.register_tenant(config)
                except Exception as e:
                    print(
                        f"Warning: Config-file tenant '{tenant_id}' failed to connect "
                        f"({config.host}:{config.port}/{config.database}): {e}"
                    )

        # 3. Load from environment variables (legacy fallback, fills remaining gaps)
        for tenant_id in env_tenant_ids:
            if tenant_id not in self.configs:
                config = self.load_tenant_from_env(tenant_id)
                if config:
                    try:
                        await self.register_tenant(config)
                    except Exception as e:
                        print(
                            f"Warning: Env tenant '{tenant_id}' failed to connect "
                            f"({config.host}:{config.port}/{config.database}): {e}"
                        )

        # Start the transaction timeout reaper
        await self._start_reaper()

    async def close_all(self) -> None:
        """Close all connection pools and Redis connection."""
        # Stop the reaper
        if self._reaper_task:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass

        # Roll back all active transactions
        async with self._tx_lock:
            tx_ids = list(self._active_transactions.keys())
        for tx_id in tx_ids:
            try:
                await self.end_transaction(tx_id, action="rollback")
            except Exception as e:
                print(f"Warning: Failed to rollback transaction '{tx_id}' on shutdown: {e}")

        for pool in self.pools.values():
            await pool.close()
        self.pools.clear()
        self.configs.clear()
        self.semaphores.clear()

        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            self._redis_initialized = False
