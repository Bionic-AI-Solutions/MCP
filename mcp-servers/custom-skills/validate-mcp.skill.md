---
name: validate-mcp
description: Validate all MCP servers and their tenant connectivity in the Kubernetes cluster. Use when you want to health-check MCP servers, verify tenant configurations, or confirm end-to-end connectivity after deployments or config changes.
allowed-tools: Bash, Read, Glob, Grep, TodoWrite, Task
argument-hint: "[server-name|all] [--tenant <tenant_id>] [--verbose]"
---

# MCP Server Validator

Validate MCP servers deployed in the Kubernetes `mcp` namespace and confirm their tenant connectivity end-to-end.

## Arguments

`$ARGUMENTS` contains: `[server-name|all] [--tenant <tenant_id>] [--verbose]`

- If no arguments or `all`: validate every MCP server
- If a specific server name (e.g. `postgres`, `openproject`): validate only that server
- `--tenant <id>`: validate a specific tenant (default: `base`)
- `--verbose`: show full tool listings and response payloads

If no arguments are provided, validate all servers with tenant `base`.

## Cluster Context

- K8s namespace: `mcp`
- Ingress domain: `mcp.baisoln.com`
- Internal service pattern: `mcp-<server>-server.mcp.svc.cluster.local:<port>`
- All MCP servers expose JSON-RPC over HTTP at `/mcp`

## Server Registry

Each entry: `directory-name | service-name | port | transport | tenant-model | validation-tool`

| Directory | K8s Service | Port | Stateless | Tenant Model | Validation Tool Call |
|-----------|-------------|------|-----------|--------------|---------------------|
| postgres | mcp-postgres-server | 8001 | no | multi-tenant (TenantManager) | `pg_execute_query` with `{"tenant_id":"base","query":"SELECT current_database()"}` |
| minio | mcp-minio-server | 8002 | no | multi-tenant (TenantManager) | `minio_list_buckets` with `{"tenant_id":"base"}` |
| redis | mcp-redis-server | 8010 | no | multi-tenant (TenantManager) | `redis_info` with `{"tenant_id":"base"}` |
| meilisearch | mcp-meilisearch-server | 8007 | no | multi-tenant (TenantManager) | `ms_list_indexes` with `{"tenant_id":"base"}` |
| letta | mcp-letta-server | 8012 | no | multi-tenant (TenantManager) | `lt_list_tenants` with `{}` (no tenant_id needed — lists all registered tenants) |
| langfuse | mcp-langfuse-server | 8011 | yes | multi-tenant (TenantManager) | `lf_create_trace` with `{"tenant_id":"base","name":"validation-test","tags":["validation"]}` |
| genImage | mcp-genimage-server | 8008 | no | multi-tenant (TenantManager) | `gi_generate_image` with `{"tenant_id":"base","prompt":"red circle on white","width":128,"height":128,"steps":4}` |
| mail | mcp-mail-server | 8005 | no | multi-tenant (TenantManager) | Use `tools/list` only (no safe idempotent test tool) |
| openproject | mcp-openproject-server | 8006 | yes | single-tenant (env vars) | `test_connection` with `{}` |
| ai-mcp-server | mcp-ai-mcp-server | 8009 | yes | multi-tenant (env vars) | Use `tools/list` only (GPU backend may be offline) |
| calculator | mcp-calculator-server | 8000 | no | none | `add` with `{"a":2,"b":3}` |
| pdf-generator | mcp-pdf-generator-server | 8003 | no | none | Use `tools/list` only |
| ffmpeg | mcp-ffmpeg-server | 8004 | yes | none | Use `tools/list` only |

## Step-by-Step Validation Process

Create a TodoWrite checklist with one item per server being validated. For each server, follow the phases below.

### Phase 1: Pod Health Check

```bash
kubectl get pods -n mcp -l app=<service-name> -o wide --no-headers
```

Check:
- Pod exists and is in `Running` state
- Ready column shows `1/1`
- No excessive restarts (>5 suggests crash-looping)

If the pod is not running, report the failure and check recent events:
```bash
kubectl describe pod -n mcp -l app=<service-name> | tail -20
```

### Phase 2: Log Inspection

```bash
kubectl logs deployment/<service-name> -n mcp --tail=15
```

Check for:
- Successful startup messages (e.g. "Uvicorn running on", "Starting MCP server")
- No ERROR or CRITICAL log lines
- For OpenProject: "API connection test successful!"
- For servers with tenants: tenant registration/discovery messages

### Phase 3: MCP Protocol Validation

#### 3a: Initialize Session

For **stateless** servers (langfuse, ffmpeg, ai-mcp-server, openproject), no session management is needed. Send requests directly.

For **stateful** servers (all others), you must first initialize to get a session ID:

```bash
kubectl run <server>-validate --rm -i --restart=Never --image=curlimages/curl -n mcp -- \
  -s -v -X POST http://<service-name>.mcp.svc.cluster.local:<port>/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"validator","version":"1.0"}}}'
```

Extract the `mcp-session-id` header from the response (use `-v` flag and grep for it).

#### 3b: List Tools

Call `tools/list` to verify the server is responding to MCP protocol:

```bash
kubectl run <server>-tools --rm -i --restart=Never --image=curlimages/curl -n mcp -- \
  -s -X POST http://<service-name>.mcp.svc.cluster.local:<port>/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  [-H "Mcp-Session-Id: <session-id>"]  \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

Verify:
- Response contains `"result"` with `"tools"` array
- Tool count is > 0
- If `--verbose`, list all tool names

#### 3c: Tenant Connectivity Test

Using the **Validation Tool Call** from the Server Registry table above, invoke the appropriate tool:

```bash
kubectl run <server>-tenant --rm -i --restart=Never --image=curlimages/curl -n mcp -- \
  -s -X POST http://<service-name>.mcp.svc.cluster.local:<port>/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  [-H "Mcp-Session-Id: <session-id>"] \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"<tool-name>","arguments":<arguments-json>}}'
```

Verify:
- Response contains `"success": true` in the result content
- No `"isError": true` in the response envelope
- For specific servers, check meaningful data is returned:
  - **postgres**: should return database name
  - **minio**: should return a list of buckets
  - **redis**: should return server info with version
  - **openproject**: should return "API connection successful!"
  - **langfuse**: should return a trace ID
  - **calculator**: should return `{"result": 5}`

**Important notes on test pod names:**
- Use unique pod names to avoid conflicts: `<server>-val-<phase>` pattern (e.g. `postgres-val-init`, `postgres-val-tools`, `postgres-val-tenant`)
- Always use `--rm -i --restart=Never` to auto-clean test pods
- Set a timeout of 30s for most calls, 120s for genImage (image generation takes time)

### Phase 4: Report Results

After validating each server, mark its TodoWrite item as completed.

Once all servers are validated, produce a summary table:

```
| Server | Pod Status | MCP Init | Tools | Tenant Test | Result |
|--------|-----------|----------|-------|-------------|--------|
| postgres | Running (1/1) | OK | 12 tools | pg_execute_query: OK | PASS |
| minio | Running (1/1) | OK | 8 tools | list_buckets: OK (6 buckets) | PASS |
| ... | ... | ... | ... | ... | ... |
```

Use these result markers:
- **PASS**: All phases succeeded
- **WARN**: Pod running but tenant test skipped (no API key, or tools/list only)
- **FAIL**: Any phase failed — include the error message

## Error Recovery

If a validation fails:

1. **Pod not running**: Check `kubectl describe` and recent events. Report but continue to next server.
2. **MCP init fails**: The server may still be starting. Wait 10s and retry once.
3. **Session ID required but missing**: Parse the error for "Missing session ID" — this means the server is stateful. Re-run with the initialize+session flow.
4. **Tenant not found**: The tenant may not be registered. Check if env vars are set:
   ```bash
   kubectl exec deployment/<service-name> -n mcp -- env | grep -i TENANT
   ```
5. **Connection refused on tool call**: Check if the backend service the tenant points to is reachable from within the cluster.

## Portable Script

A standalone validation script is available at:
`/workspace/mcp-servers/scripts/validate-mcp-servers.sh`

Run it directly: `bash /workspace/mcp-servers/scripts/validate-mcp-servers.sh [server-name|all]`
