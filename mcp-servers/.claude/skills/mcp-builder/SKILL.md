---
name: mcp-builder
description: Build and deploy a new MCP server to the Kubernetes cluster. Use when the user wants to create a new MCP server, add a new tool/service, or scaffold a new multi-tenant MCP server following the project patterns.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TodoWrite
argument-hint: "<server-name> [description]"
---

# MCP Server Builder

You are building a new MCP server for deployment to the Kubernetes `mcp` namespace. Follow the established patterns in this codebase exactly.

## Arguments

`$ARGUMENTS` contains: `<server-name> [description of what the server should do]`

If no arguments are provided, ask the user what MCP server they want to create.

## Project Context

Working directory: `/workspace/mcp-servers`

Current infrastructure:
- Docker registry: `docker.io/docker4zerocool`
- K8s namespace: `mcp`
- Ingress domain: `mcp.baisoln.com`
- Node selector: `kubernetes.io/hostname: ubuntu`
- Image pull secret: `dockerhub-pull-secret`
- Internal Redis for tenant persistence: `redis:6379` in mcp namespace

Current Redis DB assignments (for tenant config persistence):
!`grep -r "REDIS_DB" /workspace/mcp-servers/k8s/*/deployment.yaml 2>/dev/null | grep -oP 'REDIS_DB.*?"(\d+)"' | sort -t'"' -k2 -n | tail -20`

Current port assignments:
!`grep -r "containerPort" /workspace/mcp-servers/k8s/*/deployment.yaml 2>/dev/null | grep -oP '\d{4}' | sort -n`

## Step-by-Step Build Process

Follow these steps in order. Create a TodoWrite checklist to track progress.

### Step 1: Determine Configuration

From `$ARGUMENTS` or by asking the user, determine:
1. **Server name** (lowercase, hyphens allowed, e.g. `my-service`)
2. **Description** of what the server does
3. **Port number** — pick the next available port after the highest currently used
4. **Redis DB number** — pick the next available number after the highest currently used
5. **Tool prefix** — short abbreviation for tool names (e.g. `ms` for meilisearch, `gi` for genimage)
6. **Multi-tenant?** — almost always yes
7. **What service/API** does it connect to? Get connection details from the user or inspect their cluster
8. **What tools** should it expose? Get the CRUD operations needed

### Step 2: Create Python Server Code

Create the server package at `src/mcp_servers/<server-name>/`:

**Files to create:**

1. `__init__.py` — Module init exporting `mcp` and `main`
2. `server.py` — Main FastMCP server with tools
3. `tenant_manager.py` — Multi-tenant manager with Redis persistence

**Patterns to follow** (read existing servers for reference):

- Use `FastMCP` with a `lifespan` context manager for init/cleanup
- All tools are `async def` decorated with `@mcp.tool`
- All tools take `tenant_id: str` as first param and `ctx: Optional[Context] = None` as last
- All tools return `Dict[str, Any]` with `success: bool` and either result data or `error: str`
- Use try/except around all tool logic
- Use semaphores for concurrency control per tenant
- Tool names are prefixed: `{prefix}_{action}` (e.g. `redis_get`, `ms_search`)
- Import tenant manager with try/except for Docker vs local:
  ```python
  try:
      from mcp_servers.<name>.tenant_manager import <Name>TenantManager
  except ImportError:
      from .tenant_manager import <Name>TenantManager
  ```
- `main()` function reads transport config from env vars:
  ```python
  def main():
      import os
      transport = os.getenv("FASTMCP_TRANSPORT", "http")
      host = os.getenv("FASTMCP_HOST", "0.0.0.0")
      port = int(os.getenv("FASTMCP_PORT", "<PORT>"))
      stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
      json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
      mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)
  ```

**Tenant manager patterns:**
- Pydantic `BaseModel` for `<Name>TenantConfig`
- Redis persistence with key prefix `mcp:<server-name>:tenant:`
- Environment variable loading: `<UPPER_NAME>_TENANT_{id}_{CONFIG_KEY}`
- `initialize()` loads from Redis first, then env vars
- `register_tenant()` creates client, tests connection, stores config
- `get_client()` returns client info dict with client + semaphore
- `close_all()` cleans up all connections

### Step 3: Add Dockerfile Stage

Append a new build stage to `/workspace/mcp-servers/Dockerfile`:

```dockerfile
# <Server Name> stage
FROM base AS <server-name>
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE <PORT>
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:<PORT>/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/<server-name>/server.py", "--transport", "http", "--port", "<PORT>", "--host", "0.0.0.0"]
```

If the server needs additional pip packages not in the base image, note them — the user will need to add them to the base `RUN uv pip install` line.

### Step 4: Add Docker Compose Service

Append to `/workspace/mcp-servers/docker-compose.yml` (before the `networks:` section):

Follow the exact pattern of existing services (see `mcp-redis-server` entry for reference).

### Step 5: Create Kubernetes Deployment

Create `k8s/<server-name>/deployment.yaml` with:
- ConfigMap (SERVER_NAME, REDIS_HOST, REDIS_PORT, REDIS_DB, PYTHONPATH)
- Deployment (nodeSelector: ubuntu, imagePullSecrets, container with envFrom + env, resources, probes)
- Service (ClusterIP)
- Secret (if needed for credentials)

Follow the exact structure of `k8s/redis/deployment.yaml` or `k8s/postgres/deployment.yaml`.

### Step 6: Create Kong Ingress Route

Create `k8s/kong/<server-name>-routes.yaml` with:
- Ingress for `mcp.baisoln.com/<server-name>/mcp` (and /sse, /, /messages, /health)
- CORS KongPlugin
- Rate limiting KongPlugin
- Path rewrite KongPlugin (rewrites `/<server-name>/mcp` to `/mcp`)

Follow the exact structure of `k8s/kong/redis-routes.yaml` or `k8s/kong/postgres-routes.yaml`.

### Step 7: Update Kustomization

Add to `k8s/kustomization.yaml`:
- `<server-name>/deployment.yaml` in the resources section
- `kong/<server-name>-routes.yaml` in the Kong routes section
- Image transformer entry in the images section

### Step 8: Build Docker Image

```bash
cd /workspace/mcp-servers
docker build --target <server-name> -t docker.io/docker4zerocool/mcp-servers-<server-name>:latest .
```

### Step 9: Push Docker Image

```bash
docker push docker.io/docker4zerocool/mcp-servers-<server-name>:latest
```

### Step 10: Deploy to Kubernetes

```bash
kubectl apply -f k8s/<server-name>/deployment.yaml
kubectl apply -f k8s/kong/<server-name>-routes.yaml
```

Wait for the pod to be ready:
```bash
kubectl rollout status deployment/mcp-<server-name>-server -n mcp --timeout=120s
```

Verify:
```bash
kubectl get pods -n mcp -l app=mcp-<server-name>-server
kubectl logs -n mcp -l app=mcp-<server-name>-server --tail=15
```

### Step 11: Report

Tell the user:
- MCP endpoint URL: `https://mcp.baisoln.com/<server-name>/mcp`
- List of tools created
- How to register tenants
- Pod status

## Redis Cluster Mode vs Standalone

When building an MCP server that connects to Redis, you must determine whether the target is a **standalone Redis** instance or a **Redis Cluster** (sharded deployment).

### How to Detect

Inspect the target Redis deployment:
```bash
# Check if it's a Redis Cluster (StatefulSet with multiple replicas, or RedisCluster CRD)
kubectl get statefulset -n <namespace>
kubectl get pods -n <namespace> -l app=redis

# Verify by connecting and checking cluster status
kubectl exec -n <namespace> <redis-pod> -- redis-cli CLUSTER INFO
# If "cluster_enabled:1" → it's a cluster
# If "cluster_enabled:0" or connection refused → standalone
```

### Tenant Manager: cluster_mode Support

The tenant config model must include a `cluster_mode` field:

```python
class MyTenantConfig(BaseModel):
    # ... other fields ...
    cluster_mode: bool = Field(default=False, description="Connect as Redis Cluster client (handles MOVED redirections)")
```

In `register_tenant()`, select the client type based on `cluster_mode`:

```python
async def register_tenant(self, config: MyTenantConfig) -> None:
    if config.cluster_mode:
        from redis.asyncio.cluster import RedisCluster
        client = RedisCluster(
            host=config.host,
            port=config.port,
            password=config.password,
            ssl=config.ssl,
            decode_responses=config.decode_responses,
        )
    else:
        client = redis.Redis(
            host=config.host,
            port=config.port,
            password=config.password,
            db=config.db,  # db is ignored in cluster mode
            ssl=config.ssl,
            decode_responses=config.decode_responses,
        )
    await client.ping()
    # ... store client, config, semaphore
```

Environment variable loading must include `CLUSTER_MODE`:
```python
cluster_mode=os.getenv(f"{prefix}_CLUSTER_MODE", "false").lower() == "true",
```

### K8s Deployment for Cluster Mode

In the deployment.yaml, set the cluster mode env var for the tenant:
```yaml
env:
  - name: MYSERVICE_TENANT_1_HOST
    value: "redis-cluster.<namespace>.svc.cluster.local"
  - name: MYSERVICE_TENANT_1_PORT
    value: "6379"
  - name: MYSERVICE_TENANT_1_CLUSTER_MODE
    value: "true"
```

### Cross-Slot Limitations in Cluster Mode

Redis Cluster shards data across hash slots (0–16383). **Multi-key operations** (MGET, MSET, SUNION, SINTER, SDIFF, RENAME, etc.) require ALL keys to reside on the same hash slot, or Redis returns a `CROSSSLOT` error.

**Document this in tool descriptions** for any multi-key tool. Advise users to use hash tags for key co-location: keys like `{user}:name` and `{user}:email` will both hash to the same slot because Redis uses the `{...}` portion for hashing.

### Stale Config Persistence Pitfall

Tenant configs are persisted in the internal Redis (DB assigned to the server). On startup, `initialize()` loads from Redis first, then env vars. **If a stale config exists in Redis (e.g. with `cluster_mode: false`), it will be used instead of the updated env var.**

To fix: delete the stale key from the persistence Redis:
```bash
kubectl exec -n mcp deployment/redis -- redis-cli -n <DB_NUMBER> DEL "mcp:<server-name>:tenant:<tenant_id>"
```

Then restart the pod so it reloads from env vars.

## Enhanced Tool Descriptions (MANDATORY)

Every tool in every MCP server **must** have a comprehensive docstring that serves as the tool's description for MCP clients. This is critical because MCP clients (LLMs, agents) use these descriptions to understand what tools do, how to call them, and what to expect back. Poor descriptions lead to incorrect tool usage.

### Required Docstring Structure

Every `@mcp.tool` function must include a docstring with ALL of the following sections:

```python
@mcp.tool
async def prefix_action_name(
    tenant_id: str,
    required_param: str,
    optional_param: str = "default",
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """One-line summary of what this tool does in imperative mood.

    Extended description (2-4 sentences) explaining behavior, when to use this tool,
    and how it relates to other tools in this server. Mention any prerequisites
    (e.g., "The bucket must exist first — use prefix_create_bucket to create one").

    Args:
        tenant_id: Identifier for the tenant whose <service> connection to use.
                   Must be registered via prefix_register_tenant first.
        required_param: Clear description of the parameter including:
                        - Type and format expectations (e.g., "ISO-8601 datetime string")
                        - Valid value ranges or constraints (e.g., "1-1000", "max 255 chars")
                        - Example values where helpful (e.g., "e.g., 'my-bucket-name'")
        optional_param: Description of what this controls.
                        Defaults to "default". When set to X, does Y.

    Returns:
        dict: A JSON-serializable dictionary with the following structure:
            On success:
                - success (bool): True
                - <result_field> (type): Description of the returned data
                - <other_field> (type): Description of other returned fields
            On failure:
                - success (bool): False
                - error (str): Human-readable error message describing what went wrong

    Notes:
        - Any important caveats, limitations, or edge cases
        - Performance considerations (e.g., "May be slow for large datasets")
        - Security notes (e.g., "Executes raw SQL — use parameterized queries in production")
        - Cross-references to related tools (e.g., "See also: prefix_other_tool")
    """
```

### Docstring Quality Checklist

For each tool, verify:

1. **Summary line** — Clear, imperative, tells what the tool does (not how)
2. **Extended description** — Explains when/why to use this tool, prerequisites, behavior
3. **All parameters documented** — Every parameter has type info, constraints, and examples
4. **Return structure documented** — Both success and failure response shapes are shown
5. **Defaults specified** — For optional params, state the default and what changing it does
6. **Cross-references included** — Related tools are mentioned (e.g., "create before you can list")
7. **Caveats documented** — Edge cases, limitations, performance, security considerations
8. **Examples for complex params** — For params with specific formats (dates, JSON, regex), show examples

### Examples from Existing Servers

**Simple tool (calculator):**
```python
@mcp.tool
def calc_divide(a: float, b: float) -> float:
    """Divide one number by another and return the quotient.

    Performs standard floating-point division of a by b. Use this for any
    division operation. For modular arithmetic, see calc_modulo instead.

    Args:
        a: The dividend (float). The number to be divided.
        b: The divisor (float). The number to divide by. Must not be zero.

    Returns:
        float: The quotient a / b.

    Raises:
        ValueError: If b is zero (division by zero is undefined).

    Notes:
        - Performs true division, not floor/integer division.
        - Returns IEEE 754 float; very large/small results may lose precision.
    """
```

**Multi-tenant tool with complex params (meilisearch):**
```python
@mcp.tool
async def ms_search(
    tenant_id: str,
    index_uid: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
    filter: Optional[str] = None,
    sort: Optional[List[str]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search documents in a MeiliSearch index using full-text, typo-tolerant search.

    Executes a search query against the specified index and returns matching documents
    ranked by relevance. MeiliSearch provides typo-tolerant, prefix-based search out
    of the box. The index must already exist — use ms_create_index to create one first.

    Args:
        tenant_id: Identifier for the tenant whose MeiliSearch instance to query.
                   Must be registered via ms_register_tenant first.
        index_uid: The unique identifier of the index to search (e.g., "movies", "products").
        query: The search query string. Supports typo tolerance and prefix matching.
               An empty string returns all documents (useful with filters).
        limit: Maximum number of results to return per page. Defaults to 20.
               Range: 1–1000. Use with offset for pagination.
        offset: Number of results to skip before returning. Defaults to 0.
                Use with limit for pagination (e.g., offset=20, limit=20 for page 2).
        filter: Optional filter expression to narrow results.
                Syntax: 'field = value', 'field > 10', 'field IN ["a","b"]'.
                Combine with AND/OR: 'genre = "action" AND year > 2000'.
                The field must be in the index's filterable attributes.
        sort: Optional list of sort expressions. Each is "field:asc" or "field:desc".
              Example: ["year:desc", "title:asc"]. Fields must be in sortable attributes.

    Returns:
        dict: On success: {"success": True, "hits": [...], "query": str,
              "estimatedTotalHits": int, "limit": int, "offset": int}
              On failure: {"success": False, "error": str}

    Notes:
        - Filter and sort fields must be configured in index settings first.
        - Empty query with a filter is a valid way to browse/filter documents.
    """
```

**Registration tool (always include connection details):**
```python
@mcp.tool
async def prefix_register_tenant(
    tenant_id: str,
    host: str,
    port: int = 5432,
    password: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant connection for the <Service> server.

    Creates and validates a new client connection to a <Service> instance. The connection
    is tested immediately (ping/health check) and, if successful, persisted to Redis so
    it survives server restarts. All other tools require a valid tenant_id registered
    through this tool first.

    Args:
        tenant_id: A unique identifier for this tenant (e.g., "production", "staging").
                   Must be alphanumeric with hyphens/underscores. Used in all subsequent
                   tool calls to route to the correct <Service> instance.
        host: Hostname or IP of the <Service> instance
              (e.g., "my-service.namespace.svc.cluster.local" for in-cluster).
        port: Port number. Defaults to <default_port>.
        password: Optional authentication password/token. Omit for unauthenticated instances.

    Returns:
        dict: On success: {"success": True, "message": "Tenant registered", "tenant_id": str}
              On failure: {"success": False, "error": str}

    Notes:
        - The connection is validated before registration; fails fast if unreachable.
        - Config persists in Redis DB <N> under key "mcp:<server>:tenant:<tenant_id>".
        - To update a tenant, call this again with the same tenant_id (overwrites).
    """
```

### Anti-patterns to Avoid

- **One-line descriptions**: `"""List all buckets."""` — too brief, no args/returns documented
- **Missing return structure**: Callers don't know what shape the response will be
- **Undocumented defaults**: `limit=20` without saying what 20 means or what range is valid
- **No cross-references**: Tools that require other tools first (e.g., register before use) must say so
- **Generic param descriptions**: `query: The query` — not helpful. Say what format, what it searches, etc.

## Important Notes

- Always read existing server implementations for reference before writing code
- Check if any additional Python packages are needed and inform the user
- If the server connects to a service in the cluster, use `kubectl` to discover the correct hostname, port, and credentials
- Test connectivity before finalizing deployment configuration
- Use the build-images.sh pattern for the build step
- The Dockerfile already has `ffmpeg`, `weasyprint`, `postgresql-client` etc in the base — only flag truly new dependencies
