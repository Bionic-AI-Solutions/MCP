---
name: manage-tenants
description: Create, list, update, or delete tenants across all multi-tenant MCP servers (postgres, redis, minio, langfuse, letta). Uses centralized JSON config secrets — adding a tenant updates ONE K8s secret per server, no deployment YAML changes needed.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TodoWrite, AskUserQuestion
argument-hint: "<create|list|update|delete> <tenant_id> [--servers postgres,redis,minio,langfuse,letta]"
---

# MCP Tenant Manager

Manage tenants across all multi-tenant MCP servers in the Kubernetes `mcp` namespace. Supports full CRUD lifecycle: create, list, update, and delete.

## Architecture

Each MCP server reads tenant configs from a JSON file mounted as a K8s Secret volume at `/etc/mcp/tenants.json`. Adding/removing a tenant only requires updating this JSON secret and restarting the pod — **no deployment YAML changes are needed**.

**Config loading priority** (in each tenant manager's `initialize()`):
1. Redis persistence (restored from previous runs)
2. Config file (`/etc/mcp/tenants.json` from K8s Secret volume)
3. Environment variables (legacy fallback for local dev)

## Arguments

`$ARGUMENTS` contains: `<operation> <tenant_id> [--servers <csv>] [additional flags]`

**Operations:**

| Operation | Description |
|-----------|-------------|
| `create <tenant_id>` | Provision infrastructure, update K8s tenant secret, restart pods, verify registration |
| `list [tenant_id]` | List all tenants across servers, or show config details for a specific tenant |
| `update <tenant_id>` | Update an existing tenant's configuration |
| `delete <tenant_id>` | Remove tenant from K8s secrets and Redis, restart pods |

**Flags:**

- `--servers <csv>` — Comma-separated list of servers to target (default: all five)
  Valid values: `postgres`, `redis`, `minio`, `langfuse`, `letta`, or `all`
- Additional config values are gathered interactively via AskUserQuestion

If `$ARGUMENTS` is empty or unclear, ask the user what operation they want to perform.

## Cluster Context

- K8s namespace: `mcp`
- Internal service pattern: `mcp-<server>-server.mcp.svc.cluster.local:<port>`
- Internal Redis for tenant persistence: `redis:6379` in mcp namespace
- PostgreSQL via HAProxy: `pg-haproxy-primary.pg.svc.cluster.local:5432`
- MinIO internal endpoint: `minio-tenant-hl.minio.svc.cluster.local:9000`
- Letta internal endpoint: `http://letta-server.letta.svc.cluster.local:8283`
- Graphiti internal endpoint: `http://graphiti-service.letta.svc.cluster.local:8200`
- Langfuse default base URL: `https://langfuse.bionicaisolutions.com`

## Server Registry

| Server | K8s Service | Port | Tenant Secret Name | Redis DB | Config Fields |
|--------|-------------|------|---------------------|----------|---------------|
| postgres | mcp-postgres-server | 8001 | mcp-postgres-tenants | 0 | host, port, database, user, password, min_pool_size, max_pool_size, ssl |
| minio | mcp-minio-server | 8002 | mcp-minio-tenants | 1 | endpoint, access_key, secret_key, secure, region |
| pdf-generator | mcp-pdf-generator-server | 8003 | mcp-pdf-generator-tenants | 2 | storage_path |
| ffmpeg | mcp-ffmpeg-server | 8004 | mcp-ffmpeg-tenants | 3 | (minimal — tenant_id only) |
| redis | mcp-redis-server | 8010 | mcp-redis-tenants | 4 | host, port, db, cluster_mode, ssl, password, max_concurrent_requests, key_prefix |
| meilisearch | mcp-meilisearch-server | 8007 | mcp-meilisearch-tenants | 5 | url, api_key, timeout |
| mail | mcp-mail-server | 8005 | mcp-mail-tenants | 6 | api_key, mail_api_url, default_from_email, default_from_name |
| genImage | mcp-genimage-server | 8008 | mcp-genimage-tenants | 7 | runware_api_key, base_url, max_concurrent_requests |
| ai-mcp-server | mcp-ai-mcp-server | 8009 | mcp-ai-mcp-server-tenants | 8 | api_base_url, api_key, openrouter_api_key, elevenlabs_api_key, openai_api_key, timeout, max_concurrent_requests |
| langfuse | mcp-langfuse-server | 8011 | mcp-langfuse-tenants | 9 | secret_key, public_key, base_url |
| letta | mcp-letta-server | 8012 | mcp-letta-tenants | 10 | base_url, password, timeout, max_concurrency, graphiti_url, org_identity_id |

## Helper: Read and Update Tenant Secret

All CRUD operations use this common pattern to read/modify the JSON tenant config:

**Read current tenants.json from a server's secret:**
```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d
```

**Update tenants.json (add/modify/remove a tenant, then replace the secret):**
```bash
# 1. Read current config
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/tenants.json

# 2. Modify with python (example: add a tenant)
python3 -c "
import json
with open('/tmp/tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    # ... tenant config fields ...
}
with open('/tmp/tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"

# 3. Replace the secret
kubectl create secret generic <SECRET_NAME> -n mcp \
  --from-file=tenants.json=/tmp/tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Clean up temp files
rm -f /tmp/tenants.json /tmp/tenants-updated.json

# 5. Restart the pod to pick up the updated config
kubectl rollout restart deployment/<DEPLOYMENT_NAME> -n mcp
kubectl rollout status deployment/<DEPLOYMENT_NAME> -n mcp --timeout=120s
```

**No deployment YAML file changes are needed when adding/removing tenants.**

## Operation: CREATE

Create a TodoWrite checklist with items for each phase. Execute phases in order.

### Phase 1: Gather Configuration

Use AskUserQuestion (or parse from `$ARGUMENTS`) to collect the required config for each targeted server.

**Postgres** — required fields:
- `user` — Postgres username for this tenant
- `password` — Postgres password
- `database` — Database name (often same as tenant_id, but min 1 char)
- Defaults: host=`pg-haproxy-primary.pg.svc.cluster.local`, port=5432, ssl=false, pool 2-10

**Redis** — uses same cluster as base tenant, defaults are usually sufficient:
- Defaults: host=`redis-cluster.redis.svc.cluster.local`, port=6379, db=0, cluster_mode=true, ssl=false
- Key prefixing: automatic `{tenant_id}:` prefix on all keys for data isolation (no config needed)

**MinIO** — required fields:
- `access_key` — MinIO access key (min 3 chars)
- `secret_key` — MinIO secret key
- `bucket_name` — Bucket to create (min 3 chars per S3 rules)
- Defaults: endpoint=`minio-tenant-hl.minio.svc.cluster.local:9000`, secure=false, region=us-east-1

**Langfuse** — required fields:
- `secret_key` — Langfuse secret key (`sk-lf-...`)
- `public_key` — Langfuse public key (`pk-lf-...`)
- Defaults: base_url=`https://langfuse.bionicaisolutions.com`

**Letta** — mostly uses shared infrastructure:
- Defaults: base_url=`http://letta-server.letta.svc.cluster.local:8283`, password=same as base, graphiti_url=`http://graphiti-service.letta.svc.cluster.local:8200`
- org_identity_id is auto-created during registration and backfilled

### Phase 2: Provision Infrastructure

**Postgres — Create database and user:**

Find the primary pod (the one NOT in recovery):
```bash
for pod in $(kubectl get pods -n pg -o name | grep pg-ceph); do
  is_replica=$(kubectl exec -n pg $pod -- psql -U postgres -tAc "SELECT pg_is_in_recovery();" 2>/dev/null)
  if [ "$is_replica" = "f" ]; then
    echo "Primary: $pod"
    break
  fi
done
```

Then create the user and database:
```bash
kubectl exec -n pg <primary-pod> -- psql -U postgres -c "
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '<user>') THEN
      CREATE ROLE <user> WITH LOGIN PASSWORD '<password>';
    END IF;
  END \$\$;
"
kubectl exec -n pg <primary-pod> -- psql -U postgres -c "
  SELECT 'CREATE DATABASE <database> OWNER <user>'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '<database>') \gexec
"
kubectl exec -n pg <primary-pod> -- psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE <database> TO <user>;"
```

Verify:
```bash
kubectl run -n mcp pg-verify-<tenant> --rm -i --restart=Never --image=postgres:16 \
  --env="PGPASSWORD=<password>" -- \
  psql -h pg-haproxy-primary.pg.svc.cluster.local -U <user> -d <database> \
  -c "SELECT current_database(), current_user;"
```

**MinIO — Create bucket, restricted policy, and user:**

S3/MinIO naming rules: bucket names and access keys must be at least 3 characters.

```bash
# Set up mc alias inside MinIO pod
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc alias set local http://minio-tenant-hl.minio.svc.cluster.local:9000 admin Th1515T0p53cr3t

# Create bucket
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc mb local/<bucket_name> --ignore-existing

# Create restricted policy
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- sh -c 'cat > /tmp/<tenant>-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
            "s3:ListBucket", "s3:GetBucketLocation",
            "s3:ListMultipartUploadParts", "s3:AbortMultipartUpload"
        ],
        "Resource": [
            "arn:aws:s3:::<bucket_name>",
            "arn:aws:s3:::<bucket_name>/*"
        ]
    }]
}
EOF
mc admin policy create local <tenant>-restricted /tmp/<tenant>-policy.json'

# Create user and attach policy
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc admin user add local <access_key> <secret_key>
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc admin policy attach local <tenant>-restricted --user <access_key>
```

Verify:
```bash
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- mc admin user info local <access_key>
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- mc ls local/<bucket_name>/
```

**Redis** — No infrastructure provisioning needed (uses shared cluster). Each tenant's keys are automatically prefixed with `{tenant_id}:` for data isolation — all tenants share DB 0 but their keys are namespaced.
**Langfuse** — No infrastructure provisioning needed (keys are created in Langfuse UI).
**Letta** — Org identity is auto-created during tenant registration (Phase 4).

### Phase 3: Update K8s Tenant Secrets and Restart Pods

For each targeted server, update the tenant JSON secret and restart.

**Postgres:**
```bash
kubectl get secret mcp-postgres-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/pg-tenants.json
python3 -c "
import json
with open('/tmp/pg-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    'host': 'pg-haproxy-primary.pg.svc.cluster.local',
    'port': 5432,
    'database': '<database>',
    'user': '<user>',
    'password': '<password>',
    'ssl': False,
    'min_pool_size': 2,
    'max_pool_size': 10
}
with open('/tmp/pg-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-postgres-tenants -n mcp \
  --from-file=tenants.json=/tmp/pg-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/pg-tenants.json /tmp/pg-tenants-updated.json
kubectl rollout restart deployment/mcp-postgres-server -n mcp
kubectl rollout status deployment/mcp-postgres-server -n mcp --timeout=120s
```

**Redis:**
```bash
kubectl get secret mcp-redis-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/redis-tenants.json
python3 -c "
import json
with open('/tmp/redis-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    'host': 'redis-cluster.redis.svc.cluster.local',
    'port': 6379,
    'db': 0,
    'cluster_mode': True,
    'ssl': False,
    'max_concurrent_requests': 100
}
with open('/tmp/redis-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-redis-tenants -n mcp \
  --from-file=tenants.json=/tmp/redis-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/redis-tenants.json /tmp/redis-tenants-updated.json
kubectl rollout restart deployment/mcp-redis-server -n mcp
kubectl rollout status deployment/mcp-redis-server -n mcp --timeout=120s
```

**MinIO:**
```bash
kubectl get secret mcp-minio-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/minio-tenants.json
python3 -c "
import json
with open('/tmp/minio-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    'endpoint': 'minio-tenant-hl.minio.svc.cluster.local:9000',
    'access_key': '<access_key>',
    'secret_key': '<secret_key>',
    'secure': False,
    'region': 'us-east-1'
}
with open('/tmp/minio-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-minio-tenants -n mcp \
  --from-file=tenants.json=/tmp/minio-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/minio-tenants.json /tmp/minio-tenants-updated.json
kubectl rollout restart deployment/mcp-minio-server -n mcp
kubectl rollout status deployment/mcp-minio-server -n mcp --timeout=120s
```

**Langfuse:**
```bash
kubectl get secret mcp-langfuse-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/lf-tenants.json
python3 -c "
import json
with open('/tmp/lf-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    'secret_key': '<secret_key>',
    'public_key': '<public_key>',
    'base_url': 'https://langfuse.bionicaisolutions.com'
}
with open('/tmp/lf-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-langfuse-tenants -n mcp \
  --from-file=tenants.json=/tmp/lf-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/lf-tenants.json /tmp/lf-tenants-updated.json
kubectl rollout restart deployment/mcp-langfuse-server -n mcp
kubectl rollout status deployment/mcp-langfuse-server -n mcp --timeout=120s
```

**Letta:**
```bash
kubectl get secret mcp-letta-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/letta-tenants.json
python3 -c "
import json
with open('/tmp/letta-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>'] = {
    'base_url': 'http://letta-server.letta.svc.cluster.local:8283',
    'password': 'L3ttaS3rv3rTh1515T0p53cr3t',
    'timeout': 30,
    'max_concurrency': 5,
    'graphiti_url': 'http://graphiti-service.letta.svc.cluster.local:8200'
}
with open('/tmp/letta-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-letta-tenants -n mcp \
  --from-file=tenants.json=/tmp/letta-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/letta-tenants.json /tmp/letta-tenants-updated.json
kubectl rollout restart deployment/mcp-letta-server -n mcp
kubectl rollout status deployment/mcp-letta-server -n mcp --timeout=120s
```

### Phase 4: Verify Tenant Registration

After pods restart, verify each server registered the tenant.

**Check config file is mounted:**
```bash
kubectl exec -n mcp deployment/mcp-<server>-server -- cat /etc/mcp/tenants.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"
```

**Check Redis persistence** (tenant config stored in server's Redis DB):
```bash
kubectl run redis-check-<server> --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n <REDIS_DB> get "mcp:<server>:tenant:<tenant_id>"
```

**Test MCP tool call** to exercise the tenant:

For **postgres**:
```bash
kubectl run mcp-test-pg --rm -i --restart=Never -n mcp --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-postgres-server:8001/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"pg_execute_query","arguments":{"tenant_id":"<id>","query":"SELECT current_database(), current_user"}}}'
```

For **redis**:
```bash
kubectl run mcp-test-redis --rm -i --restart=Never -n mcp --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-redis-server:8010/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"redis_execute_command","arguments":{"tenant_id":"<id>","command":"PING"}}}'
```

For **minio**:
```bash
kubectl run mcp-test-minio --rm -i --restart=Never -n mcp --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-minio-server:8002/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"minio_list_buckets","arguments":{"tenant_id":"<id>"}}}'
```

For **langfuse**:
```bash
kubectl run mcp-test-lf --rm -i --restart=Never -n mcp --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-langfuse-server:8011/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lf_create_trace","arguments":{"tenant_id":"<id>","name":"tenant-verify","tags":["setup"]}}}'
```

For **letta** — check logs for org identity creation, then backfill:
```bash
kubectl logs -n mcp deployment/mcp-letta-server --tail=30 | grep -i "<tenant_id>"

# Extract auto-created org ID from Redis and show it
kubectl run redis-org --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n 10 get "mcp:letta:tenant:<id>"
```

If the Letta org_identity_id was auto-created, backfill it into the tenant secret:
```bash
# Get the org_identity_id from the Redis output above, then update the secret
kubectl get secret mcp-letta-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/letta-tenants.json
python3 -c "
import json
with open('/tmp/letta-tenants.json') as f:
    tenants = json.load(f)
tenants['<tenant_id>']['org_identity_id'] = '<ORG_ID_FROM_REDIS>'
with open('/tmp/letta-tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic mcp-letta-tenants -n mcp \
  --from-file=tenants.json=/tmp/letta-tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/letta-tenants.json /tmp/letta-tenants-updated.json
```

### Phase 5: Report Results

Produce a summary table:

```
| Server   | Infra Created | Secret Updated | Pod Restarted | Tenant Verified | Status |
|----------|---------------|----------------|---------------|-----------------|--------|
| postgres | DB + user     | tenants.json   | Running 1/1   | query OK        | PASS   |
| redis    | N/A           | tenants.json   | Running 1/1   | PING OK         | PASS   |
| minio    | bucket+policy | tenants.json   | Running 1/1   | list_buckets OK | PASS   |
| langfuse | N/A           | tenants.json   | Running 1/1   | create_trace OK | PASS   |
| letta    | org identity  | tenants.json   | Running 1/1   | org created     | PASS   |
```

---

## Operation: LIST

### List all tenants

Query the JSON tenant secret for each server:

```bash
for secret_info in "mcp-postgres-tenants:postgres" "mcp-redis-tenants:redis" "mcp-minio-tenants:minio" "mcp-langfuse-tenants:langfuse" "mcp-letta-tenants:letta"; do
  secret=${secret_info%%:*}
  server=${secret_info##*:}
  echo "=== $server ==="
  kubectl get secret $secret -n mcp -o jsonpath='{.data.tenants\.json}' 2>/dev/null | base64 -d | python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(f'  {k}' for k in sorted(d.keys())))" 2>/dev/null || echo "  (secret not found)"
done
```

### Show specific tenant

If a `tenant_id` is provided, fetch the full config from each server's secret:

```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | \
  python3 -c "
import json, sys
tenants = json.load(sys.stdin)
config = tenants.get('<tenant_id>')
if config:
    # Mask sensitive fields
    for key in config:
        val = str(config[key])
        if any(s in key.lower() for s in ['password', 'secret', 'key', 'token']):
            if len(val) > 8:
                config[key] = val[:4] + '****' + val[-4:]
            else:
                config[key] = '****'
    print(json.dumps(config, indent=2))
else:
    print('Tenant not found')
"
```

---

## Operation: UPDATE

Update follows the same flow as CREATE but:

1. **Skip infrastructure provisioning** (database, bucket already exist) unless the user explicitly requests it
2. **Read current config from secret** to show existing values
3. **Only update the changed fields** — merge new values into existing config
4. **Replace the secret and restart** the affected server pods
5. **Verify** the updated config is active

For partial updates (e.g., only changing a password), read the current config first:
```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | \
  python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin).get('<tenant_id>',{}), indent=2))"
```

Then update only the changed fields:
```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/tenants.json
python3 -c "
import json
with open('/tmp/tenants.json') as f:
    tenants = json.load(f)
# Merge only changed fields
tenants['<tenant_id>'].update({
    '<field>': '<new_value>'
})
with open('/tmp/tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic <SECRET_NAME> -n mcp \
  --from-file=tenants.json=/tmp/tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/tenants.json /tmp/tenants-updated.json
kubectl rollout restart deployment/<DEPLOYMENT_NAME> -n mcp
kubectl rollout status deployment/<DEPLOYMENT_NAME> -n mcp --timeout=120s
```

---

## Operation: DELETE

### Phase 1: Confirm Deletion

Always ask for confirmation before deleting:
- Show what will be removed (which servers, what resources)
- Warn about data loss (Postgres database will NOT be dropped — only the MCP tenant config is removed)

### Phase 2: Remove from K8s Tenant Secrets

For each targeted server, remove the tenant from the JSON config:

```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d > /tmp/tenants.json
python3 -c "
import json
with open('/tmp/tenants.json') as f:
    tenants = json.load(f)
tenants.pop('<tenant_id>', None)
with open('/tmp/tenants-updated.json', 'w') as f:
    json.dump(tenants, f, indent=2)
"
kubectl create secret generic <SECRET_NAME> -n mcp \
  --from-file=tenants.json=/tmp/tenants-updated.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/tenants.json /tmp/tenants-updated.json
```

### Phase 3: Remove from Redis Persistence

```bash
for db_info in "0:postgres" "1:minio" "4:redis" "9:langfuse" "10:letta"; do
  db=${db_info%%:*}
  server=${db_info##*:}
  kubectl run redis-del-$server --rm -i --restart=Never -n mcp --image=redis:7 -- \
    redis-cli -h redis -p 6379 -n $db DEL "mcp:$server:tenant:<tenant_id>"
done
```

### Phase 4: Restart Pods

```bash
kubectl rollout restart deployment/mcp-<server>-server -n mcp
kubectl rollout status deployment/mcp-<server>-server -n mcp --timeout=120s
```

### Phase 5: Verify Removal

Confirm the tenant is gone from the secret:
```bash
kubectl get secret <SECRET_NAME> -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('<tenant_id>' not in d)"
```

And from Redis:
```bash
kubectl run redis-verify --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n <REDIS_DB> exists "mcp:<server>:tenant:<tenant_id>"
```

### What DELETE Does NOT Do (by design)

- Does NOT drop the Postgres database or user (data preservation)
- Does NOT delete the MinIO bucket or its contents (data preservation)
- Does NOT delete the MinIO user or policy (can be done manually)
- Does NOT delete the Letta org identity (agents may still reference it)

If the user wants to also destroy infrastructure, they must explicitly request it and confirm.

---

## Error Recovery

1. **Secret not found**: The tenant secret may not exist yet. Create it:
   ```bash
   kubectl create secret generic <SECRET_NAME> -n mcp \
     --from-literal='tenants.json={}' --dry-run=client -o yaml | kubectl apply -f -
   ```
2. **Pod won't start after rollout**: Check events (`kubectl describe pod -n mcp -l app=<service>`). Common cause: secret doesn't exist or has no `tenants.json` key.
3. **Tenant not appearing in Redis**: The server loads tenants on startup from the config file. Trigger a restart to force reload.
4. **MinIO bucket name too short**: S3 requires min 3 characters. Suggest `<tenant>-data` pattern.
5. **MinIO access key too short**: MinIO requires min 3 characters. Suggest `<tenant>user` pattern.
6. **Letta org identity not backfilled**: Extract from Redis DB 10 and update the tenant secret.

## Important Notes

- **No deployment YAML changes needed** when adding/removing tenants — only K8s secrets are updated
- Tenant secrets are stored in `mcp-<server>-tenants` K8s Secrets (NOT committed to git)
- Deployment YAMLs in `k8s/<server>/deployment.yaml` only need changes for infrastructure updates (ports, images, resources)
- Redis persistence is the runtime cache (populated from config file on startup)
- Config file at `/etc/mcp/tenants.json` is the primary source of truth (from K8s Secret volume)
- Tenant IDs must be lowercase alphanumeric
- Test pod names in `kubectl run` must be unique — use pattern `<server>-<op>-<tenant>` and always use `--rm -i --restart=Never`
