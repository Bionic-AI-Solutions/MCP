"""
Redis MCP Server (Multi-tenant)

A FastMCP server providing full Redis CRUD operations with multi-tenant support.
Covers strings, hashes, lists, sets, sorted sets, key management, and server ops.

Each tool requires a tenant_id parameter to identify which Redis connection to use.
Tenants can be pre-configured via environment variables or registered dynamically
using the redis_register_tenant tool.

Supports both standalone Redis and Redis Cluster (sharded) deployments.

KEY PREFIXING / TENANT ISOLATION:
All keys are automatically namespaced per tenant. By default, the tenant_id is
used as a prefix (e.g., tenant "base" stores key "foo" as "base:foo" in Redis).
This is fully transparent — callers always use plain key names without any prefix,
and results always return plain key names with the prefix stripped. Pattern-based
tools (redis_keys, redis_scan) also auto-scope to the tenant's namespace.
The redis_execute_command tool is the only exception — it bypasses key prefixing
for raw access.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

try:
    from mcp_servers.redis.tenant_manager import RedisTenantManager
    from mcp_servers.redis.subscription_manager import SubscriptionManager
except ImportError:
    from .tenant_manager import RedisTenantManager
    from .subscription_manager import SubscriptionManager

# Initialize tenant manager and subscription manager
tenant_manager = RedisTenantManager()
subscription_manager = SubscriptionManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    await tenant_manager.initialize()
    await subscription_manager.start()
    yield
    await subscription_manager.stop()
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Redis Server", lifespan=lifespan)


# ============================================================================
# Helper
# ============================================================================

async def _get_tenant(tenant_id: str):
    """Get client, semaphore, and key prefix for a tenant."""
    info = await tenant_manager.get_client(tenant_id)
    return info["client"], info["semaphore"], info["key_prefix"]


def _pfx(prefix: str, key: str) -> str:
    """Add tenant prefix to a key."""
    return f"{prefix}{key}" if prefix else key


def _unpfx(prefix: str, key: str) -> str:
    """Strip tenant prefix from a key for display."""
    return key[len(prefix):] if prefix and key.startswith(prefix) else key


def _pfx_pattern(prefix: str, pattern: str) -> str:
    """Add tenant prefix to a glob pattern."""
    return f"{prefix}{pattern}" if prefix else pattern


def _decode(value):
    """Recursively decode bytes to strings."""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_decode(v) for v in value)
    if isinstance(value, set):
        return {_decode(v) for v in value}
    if isinstance(value, dict):
        return {_decode(k): _decode(v) for k, v in value.items()}
    return value


# ============================================================================
# Tenant Registration
# ============================================================================

@mcp.tool
async def redis_register_tenant(
    tenant_id: str,
    host: str,
    port: int = 6379,
    password: Optional[str] = None,
    db: int = 0,
    ssl: bool = False,
    cluster_mode: bool = False,
    decode_responses: bool = True,
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new Redis tenant connection for use with all other tools.

    Each tenant represents a separate Redis server or cluster. Once registered,
    use the tenant_id in any other tool to operate on that Redis instance.
    Tenant configurations are persisted in Redis so they survive server restarts.

    All keys are automatically prefixed with "{tenant_id}:" for namespace isolation.
    Callers use plain key names — prefixing is fully transparent.

    Args:
        tenant_id: Unique identifier for this tenant (e.g. "base", "production", "cache").
            This ID is used in all subsequent tool calls to target this Redis instance,
            and serves as the automatic key prefix for namespace isolation.
        host: Redis server hostname or IP address (e.g. "redis-cluster.redis.svc.cluster.local").
        port: Redis server port (default: 6379).
        password: Redis authentication password. Set to None if no auth is required (default: None).
        db: Redis database number 0-15 (default: 0). Ignored when cluster_mode is True
            because Redis Cluster only supports database 0.
        ssl: Enable SSL/TLS encrypted connection (default: False).
        cluster_mode: Set to True for Redis Cluster (sharded) deployments (default: False).
            When True, the client uses RedisCluster which automatically handles MOVED
            redirections across hash slots. When False, uses standard Redis client.
        decode_responses: Automatically decode byte responses to UTF-8 strings (default: True).
        max_concurrent_requests: Maximum number of concurrent requests allowed to this
            tenant's Redis instance. Uses a semaphore for concurrency control (default: 100).

    Returns:
        Dict with "success": True and a confirmation message, or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        from mcp_servers.redis.tenant_manager import RedisTenantConfig
    except ImportError:
        from .tenant_manager import RedisTenantConfig

    config = RedisTenantConfig(
        tenant_id=tenant_id,
        host=host,
        port=port,
        password=password,
        db=db,
        ssl=ssl,
        cluster_mode=cluster_mode,
        decode_responses=decode_responses,
        max_concurrent_requests=max_concurrent_requests,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# String Operations
# ============================================================================

@mcp.tool
async def redis_get(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the string value stored at a key.

    Returns None if the key does not exist. If the key holds a non-string data type
    (list, hash, etc.), an error is returned. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to retrieve.

    Returns:
        Dict with "success": True, "key", and "value" (string or None if key doesn't exist),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"GET {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.get(_pfx(pfx, key))
        return {"success": True, "key": key, "value": _decode(value)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_set(
    tenant_id: str,
    key: str,
    value: str,
    ttl: Optional[int] = None,
    nx: bool = False,
    xx: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set a string value at a key with optional expiration and conditional flags.

    This is the primary command for storing string values. Supports conditional
    set operations and automatic expiration. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to set.
        value: The string value to store.
        ttl: Time-to-live in seconds. The key will be automatically deleted after this
            duration. Set to None for no expiration (default: None).
        nx: Only set the key if it does NOT already exist (default: False).
            Useful for implementing locks or ensuring uniqueness.
        xx: Only set the key if it ALREADY exists (default: False).
            Useful for updating existing values without creating new keys.

    Returns:
        Dict with "success": True and "set" (boolean indicating if the value was actually set —
        may be False if nx/xx condition was not met), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SET {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            result = await client.set(_pfx(pfx, key), value, ex=ttl, nx=nx, xx=xx)
        return {
            "success": True,
            "set": result is not False and result is not None,
            "message": f"Key '{key}' set successfully" if result else f"Key '{key}' not set (condition not met)",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_mget(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the string values of multiple keys in a single call.

    Returns None for any key that does not exist. This is more efficient than
    calling redis_get multiple times. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, all keys must hash to the same slot for
    this operation to succeed. Use hash tags like {prefix}:key1, {prefix}:key2 to
    ensure keys are co-located on the same shard. Without hash tags, this command
    may fail with a cross-slot error.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of Redis keys to retrieve (e.g. ["user:1", "user:2", "user:3"]).

    Returns:
        Dict with "success": True and "results" (a dict mapping each key to its value
        or None), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"MGET {len(keys)} keys")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            values = await client.mget([_pfx(pfx, k) for k in keys])
        return {"success": True, "results": {k: _decode(v) for k, v in zip(keys, values)}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_mset(
    tenant_id: str,
    mapping: Dict[str, str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set multiple key-value pairs atomically in a single call.

    All keys are set simultaneously. This is more efficient than calling redis_set
    multiple times and guarantees atomicity (all or nothing). Keys are automatically
    namespaced per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, all keys must hash to the same slot for
    this operation to succeed. Use hash tags like {prefix}:key1, {prefix}:key2 to
    ensure keys are co-located on the same shard. Without hash tags, this command
    may fail with a cross-slot error.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        mapping: Dictionary of key-value pairs to set (e.g. {"name": "Alice", "age": "30"}).

    Returns:
        Dict with "success": True and a confirmation message, or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"MSET {len(mapping)} keys")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            await client.mset({_pfx(pfx, k): v for k, v in mapping.items()})
        return {"success": True, "message": f"{len(mapping)} keys set successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_incr(
    tenant_id: str,
    key: str,
    amount: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Increment the integer value stored at a key by a given amount.

    If the key does not exist, it is initialized to 0 before incrementing.
    The value must be representable as a 64-bit signed integer.
    Use a negative amount to decrement. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key holding an integer value.
        amount: Amount to increment by (default: 1). Use negative values to decrement.

    Returns:
        Dict with "success": True, "key", and "value" (the new integer value after increment),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"INCRBY {key} {amount}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.incrby(_pfx(pfx, key), amount)
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_append(
    tenant_id: str,
    key: str,
    value: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Append a string to the end of the value stored at a key.

    If the key does not exist, it is created with the given value (equivalent to SET).
    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to append to.
        value: The string to append.

    Returns:
        Dict with "success": True, "key", and "new_length" (total length of the string
        after appending), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"APPEND {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            length = await client.append(_pfx(pfx, key), value)
        return {"success": True, "key": key, "new_length": length}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Key Management
# ============================================================================

@mcp.tool
async def redis_delete(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete one or more keys from Redis.

    Keys that do not exist are silently ignored. Returns the count of keys
    that were actually deleted. Keys are automatically namespaced per tenant — use
    plain key names without any prefix.

    CLUSTER MODE NOTE: When deleting multiple keys in Redis Cluster, keys on
    different hash slots may cause a cross-slot error. Delete keys individually
    or use hash tags to ensure co-location.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of key names to delete (e.g. ["session:abc", "cache:xyz"]).

    Returns:
        Dict with "success": True and "deleted_count" (number of keys actually removed),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"DEL {len(keys)} keys")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            deleted = await client.delete(*[_pfx(pfx, k) for k in keys])
        return {"success": True, "deleted_count": deleted}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_exists(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Check how many of the given keys exist in Redis.

    Returns a count of existing keys. A key is counted once even if listed multiple times.
    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: When checking multiple keys in Redis Cluster, keys on different
    hash slots may cause a cross-slot error. Check keys individually or use hash tags.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of key names to check (e.g. ["user:1", "user:2"]).

    Returns:
        Dict with "success": True and "existing_count" (number of keys that exist),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"EXISTS {len(keys)} keys")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            count = await client.exists(*[_pfx(pfx, k) for k in keys])
        return {"success": True, "existing_count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_keys(
    tenant_id: str,
    pattern: str = "*",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all keys matching a glob-style pattern.

    Supported glob patterns: * (any string), ? (single char), [abc] (character class),
    [^abc] (negated class). For example: "user:*" matches all keys starting with "user:".

    WARNING: This command scans ALL keys in the database and can be slow on large datasets.
    For production use with large key spaces, prefer redis_scan which iterates incrementally.

    In Redis Cluster mode, this returns keys from all shards matching the pattern.
    Patterns are automatically scoped to the tenant's key namespace — use plain patterns
    like "*" or "user:*" without any tenant prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        pattern: Glob-style pattern to match keys against (default: "*" for all keys).
            Examples: "user:*", "session:???", "cache:[ab]*".

    Returns:
        Dict with "success": True, "pattern", "keys" (list of matching key names), and
        "count" (number of matches), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"KEYS {pattern}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            keys = await client.keys(_pfx_pattern(pfx, pattern))
        decoded_keys = [_unpfx(pfx, k) for k in _decode(keys)]
        return {"success": True, "pattern": pattern, "keys": decoded_keys, "count": len(decoded_keys)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_scan(
    tenant_id: str,
    cursor: int = 0,
    match: Optional[str] = None,
    count: int = 100,
    key_type: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Incrementally iterate through keys using a cursor (production-safe alternative to KEYS).

    SCAN does not block the server and is safe to use on large datasets. Call repeatedly
    with the returned next_cursor until "done" is True (cursor returns to 0).

    Usage pattern: Start with cursor=0, then pass the returned next_cursor in subsequent
    calls until done=True. Match patterns are automatically scoped to the tenant's key
    namespace, and returned keys have the tenant prefix stripped.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        cursor: Cursor position from a previous SCAN call. Start with 0 for the first call.
        match: Optional glob-style pattern to filter keys (e.g. "user:*", "cache:*").
        count: Hint for how many keys to return per call (default: 100). Redis may return
            more or fewer than this number.
        key_type: Filter by Redis data type. Valid values: "string", "list", "set",
            "zset", "hash", "stream" (optional).

    Returns:
        Dict with "success": True, "next_cursor" (pass this to the next call),
        "keys" (list of matching keys), "count" (keys returned this batch),
        and "done" (True when iteration is complete, i.e. next_cursor is 0),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SCAN cursor={cursor} match={match}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        if match:
            match = _pfx_pattern(pfx, match)
        kwargs = {"cursor": cursor, "count": count}
        if match:
            kwargs["match"] = match
        async with sem:
            if key_type:
                # redis-py scan doesn't support _type directly, use execute_command
                args = [cursor]
                if match:
                    args.extend(["MATCH", match])
                args.extend(["COUNT", count, "TYPE", key_type])
                result = await client.execute_command("SCAN", *args)
                next_cursor = result[0] if isinstance(result[0], int) else int(result[0])
                keys = _decode(result[1])
            else:
                next_cursor, keys = await client.scan(**kwargs)
                keys = _decode(keys)
        keys = [_unpfx(pfx, k) for k in keys]
        return {
            "success": True,
            "next_cursor": next_cursor,
            "keys": keys,
            "count": len(keys),
            "done": next_cursor == 0,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_type(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the data type of the value stored at a key.

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to check.

    Returns:
        Dict with "success": True, "key", and "type" — one of: "string", "list", "set",
        "zset", "hash", "stream", or "none" (if the key does not exist),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"TYPE {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            key_type = await client.type(_pfx(pfx, key))
        return {"success": True, "key": key, "type": _decode(key_type)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_ttl(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the remaining time-to-live (TTL) of a key in seconds.

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to check.

    Returns:
        Dict with "success": True, "key", "ttl" (seconds remaining, -1 if no expiry,
        -2 if key doesn't exist), "persistent" (True if key has no expiration),
        and "exists" (True if the key exists), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"TTL {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            ttl = await client.ttl(_pfx(pfx, key))
        return {
            "success": True,
            "key": key,
            "ttl": ttl,
            "persistent": ttl == -1,
            "exists": ttl != -2,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_expire(
    tenant_id: str,
    key: str,
    seconds: int,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set a time-to-live (expiration) on a key. The key will be automatically deleted
    after the specified number of seconds. Keys are automatically namespaced per tenant —
    use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to set expiration on.
        seconds: Number of seconds until the key expires and is deleted.

    Returns:
        Dict with "success": True, "key", and "ttl_set" (True if the timeout was set,
        False if the key does not exist), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"EXPIRE {key} {seconds}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            result = await client.expire(_pfx(pfx, key), seconds)
        return {"success": True, "key": key, "ttl_set": bool(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_persist(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove the expiration (TTL) from a key, making it persistent (never expires).

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The Redis key to make persistent.

    Returns:
        Dict with "success": True, "key", and "persisted" (True if the timeout was removed,
        False if the key does not exist or had no timeout), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"PERSIST {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            result = await client.persist(_pfx(pfx, key))
        return {"success": True, "key": key, "persisted": bool(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_rename(
    tenant_id: str,
    key: str,
    new_key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Rename a key to a new name. If new_key already exists, it is overwritten.

    Returns an error if the source key does not exist. Keys are automatically namespaced
    per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, both the source and destination keys must
    hash to the same slot. Use hash tags like {prefix}:oldname and {prefix}:newname
    to ensure co-location.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The current key name.
        new_key: The new key name.

    Returns:
        Dict with "success": True, "old_key", and "new_key",
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"RENAME {key} -> {new_key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            await client.rename(_pfx(pfx, key), _pfx(pfx, new_key))
        return {"success": True, "old_key": key, "new_key": new_key}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Hash Operations
# ============================================================================

@mcp.tool
async def redis_hset(
    tenant_id: str,
    key: str,
    mapping: Dict[str, str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set one or more field-value pairs in a hash. Creates the hash if it doesn't exist.

    Existing fields are overwritten. New fields are added. This is the primary way
    to create and update hash data structures (similar to dictionaries/objects). Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").
        mapping: Dictionary of field-value pairs to set
            (e.g. {"name": "Alice", "email": "alice@example.com", "role": "admin"}).

    Returns:
        Dict with "success": True, "key", and "fields_added" (number of NEW fields added,
        does not count updated existing fields), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HSET {key} ({len(mapping)} fields)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            added = await client.hset(_pfx(pfx, key), mapping=mapping)
        return {"success": True, "key": key, "fields_added": added}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hget(
    tenant_id: str,
    key: str,
    field: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the value of a single field in a hash.

    Returns None if the hash or field does not exist. Keys are automatically namespaced
    per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").
        field: The field name to retrieve (e.g. "email").

    Returns:
        Dict with "success": True, "key", "field", and "value" (the field's value or
        None if not found), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HGET {key} {field}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.hget(_pfx(pfx, key), field)
        return {"success": True, "key": key, "field": field, "value": _decode(value)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hgetall(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get all fields and values from a hash as a dictionary.

    Returns an empty dict if the hash does not exist. For hashes with many fields,
    consider using redis_hget for specific fields instead. Keys are automatically
    namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").

    Returns:
        Dict with "success": True, "key", "data" (dict of all field-value pairs),
        and "field_count" (number of fields), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HGETALL {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            data = await client.hgetall(_pfx(pfx, key))
        return {"success": True, "key": key, "data": _decode(data), "field_count": len(data)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hdel(
    tenant_id: str,
    key: str,
    fields: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete one or more fields from a hash.

    Fields that do not exist are silently ignored. If all fields are removed,
    the hash key itself is deleted. Keys are automatically namespaced per tenant — use
    plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").
        fields: List of field names to delete (e.g. ["temp_token", "old_email"]).

    Returns:
        Dict with "success": True, "key", and "deleted_count" (number of fields
        actually removed), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HDEL {key} ({len(fields)} fields)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            deleted = await client.hdel(_pfx(pfx, key), *fields)
        return {"success": True, "key": key, "deleted_count": deleted}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hexists(
    tenant_id: str,
    key: str,
    field: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Check if a specific field exists in a hash.

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").
        field: The field name to check (e.g. "email").

    Returns:
        Dict with "success": True, "key", "field", and "exists" (True/False),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HEXISTS {key} {field}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            exists = await client.hexists(_pfx(pfx, key), field)
        return {"success": True, "key": key, "field": field, "exists": bool(exists)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hkeys(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get all field names in a hash (without values).

    Useful for discovering the structure of a hash without retrieving all values. Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").

    Returns:
        Dict with "success": True, "key", "fields" (list of field names), and "count",
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HKEYS {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            fields = await client.hkeys(_pfx(pfx, key))
        return {"success": True, "key": key, "fields": _decode(fields), "count": len(fields)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_hincrby(
    tenant_id: str,
    key: str,
    field: str,
    amount: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Increment the integer value of a hash field by a given amount.

    If the field does not exist, it is initialized to 0 before incrementing.
    Use a negative amount to decrement. Keys are automatically namespaced per tenant —
    use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The hash key name (e.g. "user:123").
        field: The field to increment (e.g. "login_count").
        amount: Amount to increment by (default: 1). Use negative to decrement.

    Returns:
        Dict with "success": True, "key", "field", and "value" (new integer value
        after increment), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"HINCRBY {key} {field} {amount}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.hincrby(_pfx(pfx, key), field, amount)
        return {"success": True, "key": key, "field": field, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# List Operations
# ============================================================================

@mcp.tool
async def redis_lpush(
    tenant_id: str,
    key: str,
    values: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Push one or more values to the head (left/front) of a list.

    Creates the list if it does not exist. Values are inserted in order,
    so the last value in the list will be at the head of the Redis list.
    Lists are useful for queues, stacks, and ordered collections. Keys are automatically
    namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name (e.g. "queue:emails").
        values: List of string values to push (e.g. ["msg1", "msg2"]).

    Returns:
        Dict with "success": True, "key", and "list_length" (total length after push),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"LPUSH {key} ({len(values)} values)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            length = await client.lpush(_pfx(pfx, key), *values)
        return {"success": True, "key": key, "list_length": length}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_rpush(
    tenant_id: str,
    key: str,
    values: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Push one or more values to the tail (right/end) of a list.

    Creates the list if it does not exist. Values are appended in order.
    Use RPUSH + LPOP for a FIFO queue pattern. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name (e.g. "queue:tasks").
        values: List of string values to push (e.g. ["task1", "task2"]).

    Returns:
        Dict with "success": True, "key", and "list_length" (total length after push),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"RPUSH {key} ({len(values)} values)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            length = await client.rpush(_pfx(pfx, key), *values)
        return {"success": True, "key": key, "list_length": length}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_lpop(
    tenant_id: str,
    key: str,
    count: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove and return elements from the head (left/front) of a list.

    Returns None if the list is empty or does not exist.
    Use with RPUSH for a FIFO queue pattern (add to right, take from left). Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name.
        count: Number of elements to pop (default: 1).

    Returns:
        Dict with "success": True, "key", and "value" (the popped element(s) — a single
        string if count=1, or a list if count > 1, or None if empty),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"LPOP {key} count={count}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.lpop(_pfx(pfx, key), count)
        return {"success": True, "key": key, "value": _decode(value)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_rpop(
    tenant_id: str,
    key: str,
    count: int = 1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove and return elements from the tail (right/end) of a list.

    Returns None if the list is empty or does not exist.
    Use with LPUSH for a LIFO stack pattern (add to left, take from right). Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name.
        count: Number of elements to pop (default: 1).

    Returns:
        Dict with "success": True, "key", and "value" (the popped element(s) — a single
        string if count=1, or a list if count > 1, or None if empty),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"RPOP {key} count={count}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            value = await client.rpop(_pfx(pfx, key), count)
        return {"success": True, "key": key, "value": _decode(value)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_lrange(
    tenant_id: str,
    key: str,
    start: int = 0,
    stop: int = -1,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a range of elements from a list by index without removing them.

    Indices are 0-based. Negative indices count from the end (-1 is the last element).
    Use start=0, stop=-1 to get all elements. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name.
        start: Start index, inclusive (default: 0, the first element).
        stop: Stop index, inclusive (default: -1, the last element).

    Returns:
        Dict with "success": True, "key", "values" (list of elements in the range),
        and "count" (number of elements returned), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"LRANGE {key} {start} {stop}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            values = await client.lrange(_pfx(pfx, key), start, stop)
        return {"success": True, "key": key, "values": _decode(values), "count": len(values)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_llen(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the number of elements in a list.

    Returns 0 if the key does not exist. Keys are automatically namespaced per tenant —
    use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name.

    Returns:
        Dict with "success": True, "key", and "length" (number of elements),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"LLEN {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            length = await client.llen(_pfx(pfx, key))
        return {"success": True, "key": key, "length": length}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_lset(
    tenant_id: str,
    key: str,
    index: int,
    value: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set the value of a list element at a specific index.

    The index must be within the bounds of the list. An error is returned if
    the index is out of range or the key does not exist. Keys are automatically
    namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The list key name.
        index: The 0-based index of the element to set. Negative indices count from
            the end (-1 is the last element).
        value: The new string value to set at that position.

    Returns:
        Dict with "success": True, "key", and "index",
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"LSET {key}[{index}]")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            await client.lset(_pfx(pfx, key), index, value)
        return {"success": True, "key": key, "index": index}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Set Operations
# ============================================================================

@mcp.tool
async def redis_sadd(
    tenant_id: str,
    key: str,
    members: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add one or more members to an unordered set.

    Creates the set if it does not exist. Members that already exist are ignored.
    Sets are useful for tags, unique collections, and membership testing. Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The set key name (e.g. "tags:article:42").
        members: List of member values to add (e.g. ["python", "redis", "mcp"]).

    Returns:
        Dict with "success": True, "key", and "added_count" (number of NEW members
        actually added, excluding already-existing members),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SADD {key} ({len(members)} members)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            added = await client.sadd(_pfx(pfx, key), *members)
        return {"success": True, "key": key, "added_count": added}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_srem(
    tenant_id: str,
    key: str,
    members: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove one or more members from a set.

    Members that do not exist are silently ignored. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The set key name.
        members: List of member values to remove.

    Returns:
        Dict with "success": True, "key", and "removed_count" (number of members
        actually removed), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SREM {key} ({len(members)} members)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            removed = await client.srem(_pfx(pfx, key), *members)
        return {"success": True, "key": key, "removed_count": removed}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_smembers(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get all members of a set.

    Returns an empty list if the set does not exist. Order of members is not guaranteed.
    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The set key name.

    Returns:
        Dict with "success": True, "key", "members" (list of all member values),
        and "count" (number of members), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SMEMBERS {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            members = await client.smembers(_pfx(pfx, key))
        decoded = _decode(members)
        return {"success": True, "key": key, "members": list(decoded) if isinstance(decoded, set) else decoded, "count": len(members)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_sismember(
    tenant_id: str,
    key: str,
    member: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Check if a value is a member of a set. O(1) time complexity.

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The set key name.
        member: The value to check for membership.

    Returns:
        Dict with "success": True, "key", "member", and "is_member" (True/False),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SISMEMBER {key} {member}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            is_member = await client.sismember(_pfx(pfx, key), member)
        return {"success": True, "key": key, "member": member, "is_member": bool(is_member)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_scard(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the number of members in a set (cardinality).

    Returns 0 if the set does not exist. Keys are automatically namespaced per tenant —
    use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The set key name.

    Returns:
        Dict with "success": True, "key", and "cardinality" (number of members),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SCARD {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            count = await client.scard(_pfx(pfx, key))
        return {"success": True, "key": key, "cardinality": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_sunion(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Return the union of multiple sets (all unique members across all sets).

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, all set keys must hash to the same slot.
    Use hash tags like {group}:set1, {group}:set2 to ensure co-location.
    Without hash tags, this command will fail with a cross-slot error.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of set key names to union (e.g. ["tags:article:1", "tags:article:2"]).

    Returns:
        Dict with "success": True, "members" (list of all unique members across all sets),
        and "count", or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SUNION {len(keys)} sets")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            members = await client.sunion(*[_pfx(pfx, k) for k in keys])
        decoded = _decode(members)
        return {"success": True, "members": list(decoded) if isinstance(decoded, set) else decoded, "count": len(members)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_sinter(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Return the intersection of multiple sets (members common to ALL sets).

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, all set keys must hash to the same slot.
    Use hash tags like {group}:set1, {group}:set2 to ensure co-location.
    Without hash tags, this command will fail with a cross-slot error.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of set key names to intersect (e.g. ["users:active", "users:premium"]).

    Returns:
        Dict with "success": True, "members" (list of members common to all sets),
        and "count", or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SINTER {len(keys)} sets")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            members = await client.sinter(*[_pfx(pfx, k) for k in keys])
        decoded = _decode(members)
        return {"success": True, "members": list(decoded) if isinstance(decoded, set) else decoded, "count": len(members)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_sdiff(
    tenant_id: str,
    keys: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Return the set difference: members in the first set that are NOT in any of the other sets.

    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    CLUSTER MODE NOTE: In Redis Cluster, all set keys must hash to the same slot.
    Use hash tags like {group}:set1, {group}:set2 to ensure co-location.
    Without hash tags, this command will fail with a cross-slot error.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        keys: List of set key names. The first set is the base, and members present
            in any subsequent set are subtracted (e.g. ["all_users", "banned_users"]).

    Returns:
        Dict with "success": True, "members" (list of members unique to the first set),
        and "count", or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"SDIFF {len(keys)} sets")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            members = await client.sdiff(*[_pfx(pfx, k) for k in keys])
        decoded = _decode(members)
        return {"success": True, "members": list(decoded) if isinstance(decoded, set) else decoded, "count": len(members)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Sorted Set Operations
# ============================================================================

@mcp.tool
async def redis_zadd(
    tenant_id: str,
    key: str,
    members: Dict[str, float],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add one or more members to a sorted set with scores.

    Sorted sets (zsets) maintain members ordered by score. If a member already exists,
    its score is updated. Useful for leaderboards, priority queues, time-series indices,
    and range queries. Keys are automatically namespaced per tenant — use plain key names
    without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name (e.g. "leaderboard:game1").
        members: Dictionary mapping member names to their numeric scores
            (e.g. {"alice": 100.0, "bob": 85.5, "charlie": 92.0}).

    Returns:
        Dict with "success": True, "key", and "added_count" (number of NEW members
        added, does not count score updates to existing members),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZADD {key} ({len(members)} members)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            added = await client.zadd(_pfx(pfx, key), members)
        return {"success": True, "key": key, "added_count": added}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zrem(
    tenant_id: str,
    key: str,
    members: List[str],
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove one or more members from a sorted set.

    Members that do not exist are silently ignored. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        members: List of member names to remove.

    Returns:
        Dict with "success": True, "key", and "removed_count" (number of members
        actually removed), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZREM {key} ({len(members)} members)")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            removed = await client.zrem(_pfx(pfx, key), *members)
        return {"success": True, "key": key, "removed_count": removed}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zrange(
    tenant_id: str,
    key: str,
    start: int = 0,
    stop: int = -1,
    withscores: bool = False,
    rev: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a range of members from a sorted set ordered by rank (position).

    By default returns members with the lowest scores first. Use rev=True
    for highest scores first (useful for leaderboards). Keys are automatically namespaced
    per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        start: Start rank, inclusive (default: 0, the lowest-scored member).
        stop: Stop rank, inclusive (default: -1, the last member). Use 0 to 9
            for the top/bottom 10.
        withscores: If True, include the score for each member (default: False).
        rev: If True, return in reverse order — highest scores first (default: False).

    Returns:
        Dict with "success": True, "key", "members" (list of member strings if
        withscores=False, or list of {"member": str, "score": float} dicts if
        withscores=True), and "count", or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZRANGE {key} {start} {stop}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            if rev:
                result = await client.zrevrange(_pfx(pfx, key), start, stop, withscores=withscores)
            else:
                result = await client.zrange(_pfx(pfx, key), start, stop, withscores=withscores)
        if withscores:
            members = [{"member": _decode(m), "score": s} for m, s in result]
        else:
            members = _decode(result)
        return {"success": True, "key": key, "members": members, "count": len(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zscore(
    tenant_id: str,
    key: str,
    member: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the score of a specific member in a sorted set.

    Returns None if the member or sorted set does not exist. Keys are automatically
    namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        member: The member whose score to retrieve.

    Returns:
        Dict with "success": True, "key", "member", and "score" (float or None),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZSCORE {key} {member}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            score = await client.zscore(_pfx(pfx, key), member)
        return {"success": True, "key": key, "member": member, "score": score}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zrank(
    tenant_id: str,
    key: str,
    member: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the rank (0-based position) of a member in a sorted set, ordered by ascending score.

    The member with the lowest score has rank 0. Returns None if the member does not exist.
    Keys are automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        member: The member whose rank to retrieve.

    Returns:
        Dict with "success": True, "key", "member", and "rank" (0-based integer or None
        if member not found), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZRANK {key} {member}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            rank = await client.zrank(_pfx(pfx, key), member)
        return {"success": True, "key": key, "member": member, "rank": rank}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zcard(
    tenant_id: str,
    key: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the number of members in a sorted set (cardinality).

    Returns 0 if the sorted set does not exist. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.

    Returns:
        Dict with "success": True, "key", and "cardinality" (number of members),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZCARD {key}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            count = await client.zcard(_pfx(pfx, key))
        return {"success": True, "key": key, "cardinality": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zrangebyscore(
    tenant_id: str,
    key: str,
    min_score: str = "-inf",
    max_score: str = "+inf",
    withscores: bool = False,
    offset: int = 0,
    count: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get members from a sorted set whose scores fall within a range.

    Useful for time-range queries (if timestamps are used as scores), price filtering,
    or any numeric range lookup. Supports pagination via offset/count. Keys are
    automatically namespaced per tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        min_score: Minimum score as a string (default: "-inf" for no lower bound).
            Use a number like "100" for an inclusive lower bound, or "(100" for exclusive.
        max_score: Maximum score as a string (default: "+inf" for no upper bound).
            Use a number like "200" for an inclusive upper bound, or "(200" for exclusive.
        withscores: If True, include the score for each member (default: False).
        offset: Number of results to skip for pagination (default: 0).
        count: Maximum number of results to return (default: 100).

    Returns:
        Dict with "success": True, "key", "members" (list of strings or list of
        {"member": str, "score": float} dicts if withscores=True), and "count",
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZRANGEBYSCORE {key} {min_score} {max_score}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            result = await client.zrangebyscore(
                _pfx(pfx, key), min_score, max_score,
                withscores=withscores, start=offset, num=count,
            )
        if withscores:
            members = [{"member": _decode(m), "score": s} for m, s in result]
        else:
            members = _decode(result)
        return {"success": True, "key": key, "members": members, "count": len(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_zincrby(
    tenant_id: str,
    key: str,
    member: str,
    amount: float = 1.0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Increment the score of a member in a sorted set.

    If the member does not exist, it is added with the given amount as its score.
    Use a negative amount to decrement the score. Keys are automatically namespaced per
    tenant — use plain key names without any prefix.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        key: The sorted set key name.
        member: The member whose score to increment.
        amount: Amount to add to the score (default: 1.0). Use negative to decrement.

    Returns:
        Dict with "success": True, "key", "member", and "new_score" (the updated score),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"ZINCRBY {key} {member} {amount}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            new_score = await client.zincrby(_pfx(pfx, key), amount, member)
        return {"success": True, "key": key, "member": member, "new_score": new_score}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Server / Utility Operations
# ============================================================================

@mcp.tool
async def redis_ping(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Ping the Redis server to test connectivity.

    Returns True if the server is reachable and responding. Use this to verify
    that a tenant connection is healthy.

    Args:
        tenant_id: Tenant identifier (e.g. "1").

    Returns:
        Dict with "success": True and "pong" (True if server responded),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"PING")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            result = await client.ping()
        return {"success": True, "pong": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_info(
    tenant_id: str,
    section: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information and statistics about the Redis server.

    In Redis Cluster mode, returns info from the connected node. Use redis_execute_command
    with "CLUSTER INFO" for cluster-wide information.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        section: Optional section to filter. Valid sections: "server" (version, uptime),
            "clients" (connected clients), "memory" (usage stats), "stats" (hit/miss ratios),
            "replication" (master/replica info), "cpu" (usage), "keyspace" (per-db key counts),
            "cluster" (cluster state), "all" (everything). Defaults to all sections if omitted.

    Returns:
        Dict with "success": True, "section", and "info" (dict of server statistics),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"INFO {section or 'all'}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            info = await client.info(section)
        return {"success": True, "section": section or "all", "info": info}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_dbsize(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the number of keys belonging to this tenant (scoped to the tenant's namespace).

    In Redis Cluster mode, this counts the tenant's keys across all shards.

    Args:
        tenant_id: Tenant identifier (e.g. "1").

    Returns:
        Dict with "success": True and "key_count" (total number of keys),
        or "success": False with "error".
    """
    if ctx:
        await ctx.info("DBSIZE")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            count = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=_pfx_pattern(pfx, "*"), count=500)
                count += len(keys)
                if cursor == 0:
                    break
        return {"success": True, "key_count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_flushdb(
    tenant_id: str,
    confirm: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete all keys belonging to this tenant. Only removes keys within the tenant's namespace — other tenants' data is not affected. THIS IS A DESTRUCTIVE OPERATION.

    Requires confirm=True as a safety measure to prevent accidental data loss.
    In Redis Cluster mode, this flushes all shards.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        confirm: Must be explicitly set to True to execute. This is a safety guard
            to prevent accidental deletion of all data.

    Returns:
        Dict with "success": True and a confirmation message if confirm=True,
        or "success": False with a safety warning if confirm=False,
        or "success": False with "error" on failure.
    """
    if not confirm:
        return {"success": False, "error": "Safety guard: set confirm=True to flush the database"}
    if ctx:
        await ctx.info("FLUSHDB")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            deleted = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor=cursor, match=_pfx_pattern(pfx, "*"), count=500)
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        return {"success": True, "message": f"Flushed {deleted} keys for tenant", "deleted": deleted}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_execute_command(
    tenant_id: str,
    command: str,
    args: Optional[List[str]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Execute any arbitrary Redis command not covered by the dedicated tools.

    This is an escape hatch for advanced Redis commands such as CLUSTER INFO,
    CLIENT LIST, CONFIG GET, MEMORY USAGE, OBJECT ENCODING, XADD (streams),
    and any other Redis command.

    Note: This tool bypasses automatic key prefixing. Keys in command arguments are used as-is.

    Args:
        tenant_id: Tenant identifier (e.g. "1").
        command: The Redis command to execute (e.g. "CLIENT LIST", "CLUSTER INFO",
            "CONFIG GET", "MEMORY USAGE", "OBJECT ENCODING").
        args: Optional list of string arguments for the command
            (e.g. ["maxmemory"] for "CONFIG GET", ["mykey"] for "MEMORY USAGE").

    Returns:
        Dict with "success": True and "result" (the command's response, type varies
        by command), or "success": False with "error".
    """
    if ctx:
        await ctx.info(f"Executing: {command}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        async with sem:
            if args:
                result = await client.execute_command(command, *args)
            else:
                result = await client.execute_command(command)
        return {"success": True, "result": _decode(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Pub/Sub Tools
# ============================================================================

@mcp.tool
async def redis_publish(
    tenant_id: str,
    channel: str,
    message: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Publish a message to a Redis pub/sub channel for real-time event broadcasting.

    Sends the given message to all active subscribers listening on the specified
    channel. This is Redis's native publish/subscribe mechanism, enabling
    real-time cross-process communication. Any subscriber (created via
    ``redis_subscribe``) on the same channel will receive the message in their
    buffer and can retrieve it via ``redis_poll``.

    Channel names are automatically prefixed with the tenant's namespace for
    isolation — different tenants publishing to the same channel name go to
    completely separate Redis channels. Callers never see or need to know about
    the prefix.

    Typical workflow::

        1. redis_subscribe(tenant_id="base", channel="events")  →  {subscription_id}
        2. redis_publish(tenant_id="base", channel="events", message='{"type":"order_created","id":42}')
        3. redis_poll(subscription_id)  →  [{"channel":"events","data":"{...}"}]

    Args:
        tenant_id (str): Tenant identifier whose Redis connection to use. The
            tenant must already be registered via redis_register_tenant or
            pre-configured in the environment/Redis.
        channel (str): Channel name to publish to (e.g. "notifications",
            "events.orders"). This is the unprefixed name — tenant namespacing
            is applied automatically.
        message (str): The message string to publish. Can be plain text or
            serialized JSON. Redis pub/sub treats all messages as strings.
        ctx (Optional[Context], default=None): MCP context for logging.
            Automatically provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the publish succeeded.
        - channel (str): The channel name (unprefixed) that was published to.
        - receivers (int): Number of subscribers that received the message.
            Returns 0 if no subscribers are listening on this channel.
    """
    if ctx:
        await ctx.info(f"Publishing to channel: {channel}")
    try:
        client, sem, pfx = await _get_tenant(tenant_id)
        prefixed_channel = _pfx(pfx, channel)
        async with sem:
            # RedisCluster doesn't have .publish(); use execute_command instead
            from redis.asyncio.cluster import RedisCluster
            if isinstance(client, RedisCluster):
                receivers = await client.execute_command("PUBLISH", prefixed_channel, message)
            else:
                receivers = await client.publish(prefixed_channel, message)
        return {"success": True, "channel": channel, "receivers": receivers}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_subscribe(
    tenant_id: str,
    channel: str,
    pattern: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Subscribe to a Redis pub/sub channel and start buffering messages server-side.

    Creates a persistent background subscription that listens for messages on the
    specified channel and buffers them in memory. Because MCP operates over
    stateless HTTP, the subscription lives server-side — the client retrieves
    buffered messages by calling ``redis_poll`` with the returned
    ``subscription_id``, and cleans up with ``redis_unsubscribe``.

    Channel names are automatically prefixed with the tenant's namespace for
    isolation. Different tenants subscribing to the same channel name receive
    only messages published by their own tenant.

    Supports both exact channel subscriptions and glob-pattern subscriptions
    (``pattern=True``). Pattern subscriptions use Redis PSUBSCRIBE and match
    channel names using glob-style wildcards (``*``, ``?``, ``[...]``).

    Subscriptions that are not polled within 5 minutes are automatically cleaned
    up to prevent resource leaks. Each subscription buffers up to 1000 messages;
    older messages are discarded if the buffer fills before polling.

    Workflow::

        1. redis_subscribe(tenant_id="base", channel="orders.*", pattern=True)
           → {subscription_id: "abc123"}
        2. [some other process publishes to "orders.created", "orders.updated"]
        3. redis_poll(subscription_id="abc123")
           → {messages: [{channel: "orders.created", data: "..."}], count: 1}
        4. redis_unsubscribe(subscription_id="abc123")

    Args:
        tenant_id (str): Tenant identifier whose Redis connection to use. The
            tenant must already be registered via redis_register_tenant or
            pre-configured in the environment/Redis.
        channel (str): Channel name or glob pattern to subscribe to. For exact
            subscriptions (``pattern=False``): a literal channel name like
            "notifications". For pattern subscriptions (``pattern=True``): a
            glob pattern like "events.*" or "user.??.updates".
        pattern (bool, default=False): If True, use pattern-based subscription
            (Redis PSUBSCRIBE). The ``channel`` parameter is treated as a glob
            pattern that can match multiple channel names. If False, subscribe
            to the exact channel name.
        ctx (Optional[Context], default=None): MCP context for logging.
            Automatically provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the subscription was created.
        - subscription_id (str): Token to use with redis_poll and
            redis_unsubscribe. Keep this value — it is required for all
            subsequent operations on this subscription.
        - channel (str): The channel name or pattern (unprefixed).
        - pattern (bool): Whether this is a pattern subscription.
        - message (str): Guidance on next steps.
    """
    if ctx:
        await ctx.info(f"Subscribing to {'pattern' if pattern else 'channel'}: {channel}")
    try:
        info = await tenant_manager.get_client(tenant_id)
        client = info["client"]
        pfx = info["key_prefix"]
        tenant_config = info.get("config")
        if pattern:
            prefixed = _pfx_pattern(pfx, channel)
        else:
            prefixed = _pfx(pfx, channel)

        # Pass config dict for cluster mode (needs password for standalone connection)
        config_dict = None
        if tenant_config:
            config_dict = {"password": tenant_config.password}

        sub_id = await subscription_manager.subscribe(
            tenant_id=tenant_id,
            client=client,
            channel=prefixed,
            display_channel=channel,
            is_pattern=pattern,
            config=config_dict,
        )
        return {
            "success": True,
            "subscription_id": sub_id,
            "channel": channel,
            "pattern": pattern,
            "message": "Subscription created. Use redis_poll to retrieve messages.",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_poll(
    subscription_id: str,
    timeout: float = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Poll for buffered messages from an active Redis pub/sub subscription.

    Drains and returns all messages that have been received since the last poll
    (or since the subscription was created). Messages are returned in
    chronological order (oldest first). After polling, the internal buffer is
    cleared — calling poll again immediately will return an empty list unless
    new messages have arrived.

    This is the only way to retrieve messages from a subscription created via
    ``redis_subscribe``. The subscription continues to buffer new messages
    after each poll until ``redis_unsubscribe`` is called.

    Supports **long-polling**: set ``timeout`` to hold the request open until a
    message arrives or the timeout expires. This avoids busy-loop polling and
    delivers messages with near-zero latency. With ``timeout=0`` (default),
    the call returns immediately even if no messages are available.

    Recommended patterns::

        # Immediate poll (non-blocking)
        redis_poll(subscription_id="abc123")

        # Long-poll — wait up to 10s for messages
        redis_poll(subscription_id="abc123", timeout=10)

        # Continuous consumer loop (pseudo-code)
        while True:
            result = redis_poll(subscription_id="abc123", timeout=15)
            for msg in result["messages"]:
                process(msg)

    Args:
        subscription_id (str): The subscription token returned by
            ``redis_subscribe``. Must be an active subscription — if the
            subscription has been cleaned up (via unsubscribe or idle timeout),
            an error is returned.
        timeout (float, default=0): Maximum seconds to wait for messages when
            the buffer is empty. The server holds the HTTP request open until
            a message arrives or the timeout expires. Set to 0 for immediate
            (non-blocking) poll. Capped at 30 seconds.
        ctx (Optional[Context], default=None): MCP context for logging.
            Automatically provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the poll succeeded.
        - messages (List[Dict]): List of received messages in chronological
            order. Each message contains:
            - channel (str): The channel the message was received on (unprefixed).
            - data (str): The message content as published.
            - timestamp (float): Unix timestamp when the message was received.
            - pattern (str, optional): For pattern subscriptions, the pattern
              that matched this message.
        - count (int): Number of messages returned in this poll.
    """
    if ctx:
        await ctx.info(f"Polling subscription: {subscription_id}")
    try:
        messages = await subscription_manager.poll(subscription_id, timeout=timeout)
        return {"success": True, "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def redis_unsubscribe(
    subscription_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Unsubscribe from a Redis pub/sub channel and clean up all resources.

    Cancels the background listener task, closes the dedicated Redis PubSub
    connection, and discards any buffered messages that have not been polled.
    After this call, the ``subscription_id`` is permanently invalid and cannot
    be reused.

    Always call this when you are done consuming messages to free server
    resources. If you forget, idle subscriptions are automatically cleaned up
    after 5 minutes of inactivity (no polls).

    Args:
        subscription_id (str): The subscription token returned by
            ``redis_subscribe``. If the subscription has already been cleaned
            up (double-unsubscribe or idle timeout), ``removed`` will be False
            but no error is raised.
        ctx (Optional[Context], default=None): MCP context for logging.
            Automatically provided by the framework; callers should not set this.

    Returns:
        Dict with:
        - success (bool): Whether the operation completed without error.
        - removed (bool): True if the subscription was found and removed,
            False if it was already gone (idempotent).
    """
    if ctx:
        await ctx.info(f"Unsubscribing: {subscription_id}")
    try:
        removed = await subscription_manager.unsubscribe(subscription_id)
        return {"success": True, "removed": removed}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("redis://{tenant_id}/keys")
async def get_keys_resource(tenant_id: str) -> str:
    """Get list of keys for a tenant as a resource."""
    result = await redis_keys(tenant_id)
    return json.dumps(result, indent=2)


@mcp.resource("redis://info")
def redis_info_resource() -> str:
    """Get information about the Redis MCP server."""
    return "Redis MCP Server - Multi-tenant Redis CRUD operations (strings, hashes, lists, sets, sorted sets)"


def main():
    """Run the Redis server with HTTP transport for remote access."""
    import os
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8010"))
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()
