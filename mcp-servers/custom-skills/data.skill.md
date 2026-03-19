---
name: data
description: Data operations hub — routes to /db (PostgreSQL), /cache (Redis), or /search (MeiliSearch) based on your needs.
allowed-tools: Bash, TodoWrite
argument-hint: "<description of what you need>"
---

# Data Operations

This is a routing skill. Based on what you need, invoke the appropriate specialized skill:

## Available Data Skills

| Skill | Server | When to Use |
|-------|--------|-------------|
| `/db` | PostgreSQL | SQL queries, table operations, transactions, schema inspection |
| `/cache` | Redis | Key-value storage, hashes, lists, sets, sorted sets, pub/sub messaging |
| `/search` | MeiliSearch | Full-text search, indexing documents, faceted search |

## Routing Guide

Analyze `$ARGUMENTS` and invoke the matching skill:

- **SQL, query, table, schema, transaction, database** → Invoke `/db` with the user's request
- **Cache, key-value, hash, list, set, pub/sub, Redis, TTL** → Invoke `/cache` with the user's request
- **Search, index, documents, full-text, filter** → Invoke `/search` with the user's request
- **Unclear or multiple** → Ask the user which data store they need, or use `/mcp` for discovery

All three servers are multi-tenant. Default tenant: `base`.
