---
name: manage-tenants
description: Create, list, update, or delete tenants across all multi-tenant MCP servers (postgres, redis, minio, langfuse, letta). Handles K8s secrets, deployment env vars, infrastructure provisioning (Postgres DB/user, MinIO bucket/policy/user), and MCP server registration in one workflow.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TodoWrite, AskUserQuestion
argument-hint: "<create|list|update|delete> <tenant_id> [--servers postgres,redis,minio,langfuse,letta]"
---

# MCP Tenant Manager

Manage tenants across all multi-tenant MCP servers in the Kubernetes `mcp` namespace. Supports full CRUD lifecycle: create, list, update, and delete.

## Arguments

`$ARGUMENTS` contains: `<operation> <tenant_id> [--servers <csv>] [additional flags]`

**Operations:**

| Operation | Description |
|-----------|-------------|
| `create <tenant_id>` | Provision infrastructure, patch K8s secrets, update deployment YAMLs, restart pods, verify registration |
| `list [tenant_id]` | List all tenants across servers, or show config details for a specific tenant |
| `update <tenant_id>` | Update an existing tenant's configuration (re-register with new values) |
| `delete <tenant_id>` | Remove tenant from K8s secrets, Redis persistence, deployment YAMLs, restart pods |

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

| Server | K8s Service | Port | Secret Name | Redis DB | Env Var Prefix | Config Fields |
|--------|-------------|------|-------------|----------|----------------|---------------|
| postgres | mcp-postgres-server | 8001 | mcp-postgres-secrets | 0 | `POSTGRES_TENANT_{ID}_` | HOST, PORT, DB, USER, PASSWORD, MIN_POOL_SIZE, MAX_POOL_SIZE, SSL |
| redis | mcp-redis-server | 8010 | _(inline values)_ | 4 | `REDIS_TENANT_{ID}_` | HOST, PORT, DB, CLUSTER_MODE, SSL, MAX_CONCURRENT |
| minio | mcp-minio-server | 8002 | mcp-minio-secrets | 1 | `MINIO_TENANT_{ID}_` | ENDPOINT, ACCESS_KEY, SECRET_KEY, SECURE, REGION |
| langfuse | mcp-langfuse-server | 8011 | mcp-langfuse-secrets | 9 | `LANGFUSE_TENANT_{ID}_` | SECRET_KEY, PUBLIC_KEY, BASE_URL |
| letta | mcp-letta-server | 8012 | mcp-letta-secrets | 10 | `LETTA_TENANT_{ID}_` | BASE_URL, PASSWORD, TIMEOUT, MAX_CONCURRENCY, GRAPHITI_URL, ORG_IDENTITY_ID |

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

**Redis** — No infrastructure provisioning needed (uses shared cluster).
**Langfuse** — No infrastructure provisioning needed (keys are created in Langfuse UI).
**Letta** — Org identity is auto-created during tenant registration (Phase 4).

### Phase 3: Patch K8s Secrets and Deployment YAMLs

**Patch secrets** (never overwrite — always use `--type merge`):

For **postgres**:
```bash
kubectl patch secret mcp-postgres-secrets -n mcp --type merge -p \
  '{"stringData":{
    "tenant-<id>-host":"pg-haproxy-primary.pg.svc.cluster.local",
    "tenant-<id>-port":"5432",
    "tenant-<id>-db":"<database>",
    "tenant-<id>-user":"<user>",
    "tenant-<id>-password":"<password>"
  }}'
```

For **minio**:
```bash
kubectl patch secret mcp-minio-secrets -n mcp --type merge -p \
  '{"stringData":{
    "tenant-<id>-endpoint":"minio-tenant-hl.minio.svc.cluster.local:9000",
    "tenant-<id>-access-key":"<access_key>",
    "tenant-<id>-secret-key":"<secret_key>"
  }}'
```

For **langfuse**:
```bash
kubectl patch secret mcp-langfuse-secrets -n mcp --type merge -p \
  '{"stringData":{
    "tenant-<id>-secret-key":"<secret_key>",
    "tenant-<id>-public-key":"<public_key>"
  }}'
```

For **letta**:
```bash
kubectl patch secret mcp-letta-secrets -n mcp --type merge -p \
  '{"stringData":{
    "tenant-<id>-base-url":"http://letta-server.letta.svc.cluster.local:8283",
    "tenant-<id>-password":"L3ttaS3rv3rTh1515T0p53cr3t",
    "tenant-<id>-graphiti-url":"http://graphiti-service.letta.svc.cluster.local:8200",
    "tenant-<id>-org-identity-id":""
  }}'
```

**Redis** uses inline env values (no secret needed).

**Update deployment YAMLs** — Add the new tenant's env var block to each server's `k8s/<server>/deployment.yaml`:

For each server, add a block of environment variables after the last existing tenant block in the Deployment container spec. Follow the exact pattern of the existing tenants (secretKeyRef for sensitive values, inline for non-sensitive).

Also add the corresponding entries to the Secret's `stringData` section in the same YAML file.

**Apply deployment changes:**
```bash
kubectl apply -f k8s/postgres/deployment.yaml
kubectl apply -f k8s/redis/deployment.yaml
kubectl apply -f k8s/minio/deployment.yaml
kubectl apply -f k8s/langfuse/deployment.yaml
kubectl apply -f k8s/letta/deployment.yaml
```

**Wait for rollouts:**
```bash
kubectl rollout status deployment/mcp-postgres-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-redis-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-minio-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-langfuse-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-letta-server -n mcp --timeout=120s
```

### Phase 4: Verify Tenant Registration

After pods restart, verify each server registered the tenant.

**Check env vars are injected:**
```bash
kubectl exec -n mcp deployment/mcp-<server>-server -- env | grep -i "<PREFIX>_TENANT_<ID>"
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

For **letta** — check logs for org identity creation:
```bash
kubectl logs -n mcp deployment/mcp-letta-server --tail=30 | grep -i "<tenant_id>"
```

Then backfill the Letta org identity ID into the K8s secret and deployment YAML:
```bash
# Extract auto-created org ID from Redis
ORG_ID=$(kubectl run redis-org --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n 10 get "mcp:letta:tenant:<id>" 2>/dev/null | \
  python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('org_identity_id',''))")

# Patch back into secret
kubectl patch secret mcp-letta-secrets -n mcp --type merge -p \
  "{\"stringData\":{\"tenant-<id>-org-identity-id\":\"$ORG_ID\"}}"
```

Update the deployment YAML's Secret stringData section with the org identity value.

### Phase 5: Report Results

Produce a summary table:

```
| Server   | Secret Patched | Infra Created | Pod Restarted | Tenant Verified | Status |
|----------|---------------|---------------|---------------|-----------------|--------|
| postgres | tenant-<id>-* | DB + user     | Running 1/1   | query OK        | PASS   |
| redis    | (inline)      | N/A           | Running 1/1   | PING OK         | PASS   |
| minio    | tenant-<id>-* | bucket+policy | Running 1/1   | list_buckets OK | PASS   |
| langfuse | tenant-<id>-* | N/A           | Running 1/1   | create_trace OK | PASS   |
| letta    | tenant-<id>-* | org identity  | Running 1/1   | org created     | PASS   |
```

---

## Operation: LIST

### List all tenants

Query Redis persistence for each server to enumerate all registered tenants:

```bash
# For each server, query its Redis DB
for db_info in "0:postgres" "1:minio" "4:redis" "9:langfuse" "10:letta"; do
  db=${db_info%%:*}
  server=${db_info##*:}
  echo "=== $server (Redis DB $db) ==="
  kubectl run redis-list-$server --rm -i --restart=Never -n mcp --image=redis:7 -- \
    redis-cli -h redis -p 6379 -n $db keys "mcp:$server:tenant:*"
done
```

### Show specific tenant

If a `tenant_id` is provided, fetch the full config from each server's Redis DB:

```bash
kubectl run redis-show --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n <REDIS_DB> get "mcp:<server>:tenant:<tenant_id>"
```

Display the config with sensitive fields masked (show first 4 + last 4 chars of passwords/keys).

Also check K8s secrets to confirm the entries exist:
```bash
kubectl get secret <secret-name> -n mcp -o jsonpath='{.data}' | \
  python3 -c "import sys,json; d=json.load(sys.stdin); [print(k) for k in sorted(d.keys()) if '<tenant_id>' in k]"
```

---

## Operation: UPDATE

Update follows the same flow as CREATE but:

1. **Skip infrastructure provisioning** (database, bucket already exist) unless the user explicitly requests it
2. **Patch K8s secrets** with the new values (merge overwrites existing keys)
3. **Update deployment YAML** files with any changed values
4. **Apply and restart** the affected server pods
5. **Verify** the updated config is active

For partial updates (e.g., only changing a password), only patch the changed fields — do NOT re-prompt for unchanged values. Read the current config from Redis first to show existing values.

To read current config:
```bash
kubectl run redis-read --rm -i --restart=Never -n mcp --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n <REDIS_DB> get "mcp:<server>:tenant:<tenant_id>"
```

---

## Operation: DELETE

### Phase 1: Confirm Deletion

Always ask for confirmation before deleting:
- Show what will be removed (which servers, what resources)
- Warn about data loss (Postgres database will NOT be dropped — only the MCP tenant config is removed)

### Phase 2: Remove from K8s Secrets

For each targeted server, remove the tenant's secret keys. Since `kubectl patch` can't delete individual keys from a Secret, use the annotation approach:

```bash
# Get current secret, remove tenant keys, re-apply
kubectl get secret <secret-name> -n mcp -o json | \
  python3 -c "
import sys, json, base64
secret = json.load(sys.stdin)
keys_to_remove = [k for k in secret['data'] if k.startswith('tenant-<id>-')]
for k in keys_to_remove:
    del secret['data'][k]
# Remove resourceVersion to allow update
secret['metadata'].pop('resourceVersion', None)
secret['metadata'].pop('uid', None)
secret['metadata'].pop('creationTimestamp', None)
json.dump(secret, sys.stdout)
" | kubectl apply -f -
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

### Phase 4: Remove from Deployment YAMLs

Edit each `k8s/<server>/deployment.yaml` to remove the tenant's env var block and secret entries.

### Phase 5: Apply and Restart

```bash
kubectl apply -f k8s/<server>/deployment.yaml
kubectl rollout status deployment/mcp-<server>-server -n mcp --timeout=120s
```

### Phase 6: Verify Removal

Confirm the tenant is gone from Redis:
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

1. **Secret patch fails**: Check if the secret exists (`kubectl get secret <name> -n mcp`). Create it if missing.
2. **Pod won't start after rollout**: Check events (`kubectl describe pod -n mcp -l app=<service>`). Common causes: missing secret keys, invalid YAML.
3. **Tenant not appearing in Redis**: The server loads tenants lazily. Trigger a tool call to the tenant to force registration.
4. **MinIO bucket name too short**: S3 requires min 3 characters. Suggest `<tenant>-data` pattern.
5. **MinIO access key too short**: MinIO requires min 3 characters. Suggest `<tenant>user` pattern.
6. **Postgres connection fails via MCP but psql works**: This is a known psycopg pool issue. The tenant config is correct — verify via direct psql connection.
7. **Letta org identity not backfilled**: Extract from Redis DB 10 and patch into the secret.

## Important Notes

- Always use `kubectl patch --type merge` for secrets to avoid overwriting existing tenant entries
- Deployment YAMLs in `k8s/<server>/deployment.yaml` are the source of truth for K8s manifests
- Redis persistence is the runtime source of truth (loaded on pod startup)
- Environment variables from secrets take precedence over Redis on restart
- Tenant IDs must be lowercase alphanumeric (the env var prefix is uppercased automatically)
- Test pod names in `kubectl run` must be unique — use pattern `<server>-<op>-<tenant>` and always use `--rm -i --restart=Never`
