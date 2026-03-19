---
name: cache
description: Read, write, and manage Redis data structures (strings, hashes, lists, sets, sorted sets, pub/sub) via the Redis MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<get|set|hset|lpush|sadd|zadd|publish|...> [args] [--tenant <id>]"
---

# Redis MCP Server

Server: `redis` at `redis/mcp` (stateful transport)
Alternate domain: `mcp.bionicaisolutions.com`
Multi-tenant. Default tenant: `base`. 55 tools organized by data type.
All tools take `tenant_id` as the first parameter. Keys are automatically prefixed with `{tenant_id}:` for data isolation.

## Tool Inventory

### Strings (6 tools)
`redis_get`, `redis_set` (with ttl/nx/xx options), `redis_mget`, `redis_mset`, `redis_incr`, `redis_append`
-- Standard key-value operations. `redis_set` supports TTL expiry and NX/XX conditional writes.

### Keys (9 tools)
`redis_delete`, `redis_exists`, `redis_keys`, `redis_scan`, `redis_type`, `redis_ttl`, `redis_expire`, `redis_persist`, `redis_rename`
-- Key management: check existence, list/scan keys by pattern, set/remove expiry, rename keys.

### Hashes (7 tools)
`redis_hset`, `redis_hget`, `redis_hgetall`, `redis_hdel`, `redis_hexists`, `redis_hkeys`, `redis_hincrby`
-- Hash map operations for storing structured field-value pairs under a single key.

### Lists (7 tools)
`redis_lpush`, `redis_rpush`, `redis_lpop`, `redis_rpop`, `redis_lrange`, `redis_llen`, `redis_lset`
-- Ordered list operations: push/pop from either end, range queries, set by index.

### Sets (8 tools)
`redis_sadd`, `redis_srem`, `redis_smembers`, `redis_sismember`, `redis_scard`, `redis_sunion`, `redis_sinter`, `redis_sdiff`
-- Unordered unique collections: add/remove members, membership checks, set algebra.

### Sorted Sets (8 tools)
`redis_zadd`, `redis_zrem`, `redis_zrange`, `redis_zscore`, `redis_zrank`, `redis_zcard`, `redis_zrangebyscore`, `redis_zincrby`
-- Score-ordered sets: add with scores, range by rank or score, increment scores.

### Server (5 tools)
`redis_ping`, `redis_info`, `redis_dbsize`, `redis_flushdb`, `redis_execute_command`
-- Server diagnostics and raw command execution. `redis_flushdb` only deletes the current tenant's keys. `redis_execute_command` bypasses key prefixing.

### Pub/Sub (4 tools)
`redis_publish`, `redis_subscribe`, `redis_poll`, `redis_unsubscribe`
-- Publish/subscribe messaging: publish to channels, subscribe, poll for messages, unsubscribe.

### Admin (1 tool)
`redis_register_tenant` -- Register a new tenant with connection details (host, port, db, password, cluster_mode, ssl).

## Usage Examples

Set and get a value:
```bash
~/.claude/bin/mcp-rpc call redis redis_set '{"tenant_id": "base", "key": "greeting", "value": "hello world", "ttl": 3600}'
~/.claude/bin/mcp-rpc call redis redis_get '{"tenant_id": "base", "key": "greeting"}'
```

Store and retrieve a hash:
```bash
~/.claude/bin/mcp-rpc call redis redis_hset '{"tenant_id": "base", "key": "user:1", "field": "name", "value": "Alice"}'
~/.claude/bin/mcp-rpc call redis redis_hgetall '{"tenant_id": "base", "key": "user:1"}'
```

Publish a message to a channel:
```bash
~/.claude/bin/mcp-rpc call redis redis_publish '{"tenant_id": "base", "channel": "events", "message": "deployment complete"}'
```

## Notes

- Keys are automatically namespaced per tenant (`{tenant_id}:key`). Clients never see the prefix.
- `redis_execute_command` bypasses prefixing and sends raw Redis commands.
- `redis_flushdb` with `confirm=true` only deletes the current tenant's keys, not all keys.
- Multi-key operations (mget, mset, sunion, sinter, sdiff, rename) require all keys on the same hash slot in cluster mode. Use `{hashtag}` in key names for co-location.
- `redis_set` supports `nx=true` (set only if not exists) and `xx=true` (set only if exists).
