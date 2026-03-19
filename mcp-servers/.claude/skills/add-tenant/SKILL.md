---
name: add-tenant
description: Add a new tenant to all multi-tenant MCP servers (postgres, redis, minio, letta) with convention-based defaults. Just provide the tenant name.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, TodoWrite
argument-hint: "<tenant-name>"
---

# Add Tenant

Quickly add a new tenant to all multi-tenant MCP servers using convention-based defaults.

## Arguments

`$ARGUMENTS` contains the tenant name (e.g., `my-app`).

If no argument is provided, ask the user for a tenant name.

## Naming Conventions

Given a tenant name like `my-app`:

| Field | Convention | Example |
|-------|-----------|---------|
| Tenant ID | as-provided (lowercase, hyphens OK) | `my-app` |
| Postgres user | underscores instead of hyphens | `my_app` |
| Postgres database | underscores instead of hyphens | `my_app` |
| Postgres password | `<underscore_name>Th1515T0p53cr3t` | `my_appTh1515T0p53cr3t` |
| MinIO access key | hyphens removed + `user` | `myappuser` |
| MinIO secret key | `<no_hyphens>Th1515T0p53cr3t` | `myappTh1515T0p53cr3t` |
| MinIO bucket | same as tenant name | `my-app` |

## Cluster Context

- K8s namespace: `mcp`
- PostgreSQL via HAProxy: `pg-haproxy-primary.pg.svc.cluster.local:5432`
- Postgres superuser password: `1rJlrTbsgL1YaqDVors6HGK8KnaHom1n6sUFccQNTadpkpzZCN9r0s2llroTy9Tu`
- MinIO internal endpoint: `minio-tenant-hl.minio.svc.cluster.local:9000`
- MinIO admin credentials: `admin` / `Th1515T0p53cr3t`
- Redis cluster: `redis-cluster.redis.svc.cluster.local:6379`
- Letta server: `http://letta-server.letta.svc.cluster.local:8283`
- Letta password: `L3ttaS3rv3rTh1515T0p53cr3t`
- Graphiti: `http://graphiti-service.letta.svc.cluster.local:8200`

## Servers and Their Tenant Secrets

Each server reads tenants from a `tenants.json` file mounted from a K8s secret:

| Server | K8s Secret Name | Port | Redis DB |
|--------|----------------|------|----------|
| postgres | mcp-postgres-tenants | 8001 | 0 |
| redis | mcp-redis-tenants | 8010 | 4 |
| minio | mcp-minio-tenants | 8002 | 1 |
| letta | mcp-letta-tenants | 8012 | 10 |

## Execution Plan

Create a TodoWrite checklist and execute each phase in order.

### Phase 1: Pre-flight Checks

Derive all names from the tenant argument:
```
TENANT="<argument>"
PG_USER="${TENANT//-/_}"        # hyphens -> underscores
PG_DB="${TENANT//-/_}"
PG_PASS="${PG_USER}Th1515T0p53cr3t"
MINIO_KEY="${TENANT//-/}user"   # remove hyphens, append "user"
MINIO_SECRET="${TENANT//-/}Th1515T0p53cr3t"
MINIO_BUCKET="${TENANT}"
```

Verify the tenant doesn't already exist:
```bash
kubectl get secret mcp-postgres-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
if '<TENANT>' in data:
    print('ERROR: Tenant already exists in postgres')
    sys.exit(1)
print('OK: Tenant does not exist yet')
"
```

### Phase 2: Provision Postgres

Find a usable Postgres pod and create user + database:

```bash
# Create user via HAProxy primary
kubectl run -n mcp pg-mkuser-<TENANT> --rm -i --restart=Never --image=postgres:16 \
  --env="PGPASSWORD=1rJlrTbsgL1YaqDVors6HGK8KnaHom1n6sUFccQNTadpkpzZCN9r0s2llroTy9Tu" -- \
  psql -h pg-haproxy-primary.pg.svc.cluster.local -U postgres \
  -c "CREATE ROLE <PG_USER> WITH LOGIN PASSWORD '<PG_PASS>'"

# Create database
kubectl run -n mcp pg-mkdb-<TENANT> --rm -i --restart=Never --image=postgres:16 \
  --env="PGPASSWORD=1rJlrTbsgL1YaqDVors6HGK8KnaHom1n6sUFccQNTadpkpzZCN9r0s2llroTy9Tu" -- \
  psql -h pg-haproxy-primary.pg.svc.cluster.local -U postgres \
  -c "CREATE DATABASE <PG_DB> OWNER <PG_USER>"

# Grant privileges
kubectl run -n mcp pg-grant-<TENANT> --rm -i --restart=Never --image=postgres:16 \
  --env="PGPASSWORD=1rJlrTbsgL1YaqDVors6HGK8KnaHom1n6sUFccQNTadpkpzZCN9r0s2llroTy9Tu" -- \
  psql -h pg-haproxy-primary.pg.svc.cluster.local -U postgres \
  -c "GRANT ALL PRIVILEGES ON DATABASE <PG_DB> TO <PG_USER>"
```

Verify:
```bash
kubectl run -n mcp pg-verify-<TENANT> --rm -i --restart=Never --image=postgres:16 \
  --env="PGPASSWORD=<PG_PASS>" -- \
  psql -h pg-haproxy-primary.pg.svc.cluster.local -U <PG_USER> -d <PG_DB> \
  -c "SELECT current_database(), current_user;"
```

### Phase 3: Provision MinIO

```bash
# Set up mc alias
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc alias set local http://minio-tenant-hl.minio.svc.cluster.local:9000 admin Th1515T0p53cr3t

# Create bucket
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc mb local/<MINIO_BUCKET> --ignore-existing

# Create restricted policy
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- sh -c 'cat > /tmp/<TENANT>-policy.json << EOF
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
            "arn:aws:s3:::<MINIO_BUCKET>",
            "arn:aws:s3:::<MINIO_BUCKET>/*"
        ]
    }]
}
EOF
mc admin policy create local <TENANT>-restricted /tmp/<TENANT>-policy.json'

# Create user and attach policy
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc admin user add local <MINIO_KEY> <MINIO_SECRET>
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- \
  mc admin policy attach local <TENANT>-restricted --user <MINIO_KEY>
```

Verify:
```bash
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- mc admin user info local <MINIO_KEY>
kubectl exec -n minio minio-tenant-pool-0-0 -c minio -- mc ls local/<MINIO_BUCKET>/
```

### Phase 4: Patch All K8s Tenant Secrets

For each server, read the existing `tenants.json`, add the new tenant entry, and apply:

**Postgres:**
```bash
kubectl get secret mcp-postgres-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['<TENANT>'] = {
    'host': 'pg-haproxy-primary.pg.svc.cluster.local',
    'port': 5432,
    'database': '<PG_DB>',
    'user': '<PG_USER>',
    'password': '<PG_PASS>',
    'ssl': False,
    'min_pool_size': 2,
    'max_pool_size': 10
}
print(json.dumps(data))
" | kubectl create secret generic mcp-postgres-tenants -n mcp \
    --from-file=tenants.json=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

**Redis:**
```bash
kubectl get secret mcp-redis-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['<TENANT>'] = {
    'host': 'redis-cluster.redis.svc.cluster.local',
    'port': 6379,
    'db': 0,
    'cluster_mode': True,
    'ssl': False,
    'max_concurrent_requests': 100
}
print(json.dumps(data))
" | kubectl create secret generic mcp-redis-tenants -n mcp \
    --from-file=tenants.json=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

**MinIO:**
```bash
kubectl get secret mcp-minio-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['<TENANT>'] = {
    'endpoint': 'minio-tenant-hl.minio.svc.cluster.local:9000',
    'access_key': '<MINIO_KEY>',
    'secret_key': '<MINIO_SECRET>',
    'secure': False,
    'region': 'us-east-1'
}
print(json.dumps(data))
" | kubectl create secret generic mcp-minio-tenants -n mcp \
    --from-file=tenants.json=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

**Letta:**
```bash
kubectl get secret mcp-letta-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['<TENANT>'] = {
    'base_url': 'http://letta-server.letta.svc.cluster.local:8283',
    'password': 'L3ttaS3rv3rTh1515T0p53cr3t',
    'timeout': 30,
    'max_concurrency': 5,
    'graphiti_url': 'http://graphiti-service.letta.svc.cluster.local:8200'
}
print(json.dumps(data))
" | kubectl create secret generic mcp-letta-tenants -n mcp \
    --from-file=tenants.json=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

### Phase 5: Restart Pods and Wait

```bash
kubectl rollout restart deployment/mcp-postgres-server deployment/mcp-redis-server \
  deployment/mcp-minio-server deployment/mcp-letta-server -n mcp

kubectl rollout status deployment/mcp-postgres-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-redis-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-minio-server -n mcp --timeout=120s
kubectl rollout status deployment/mcp-letta-server -n mcp --timeout=120s
```

### Phase 6: Verify All Servers

Run MCP tool calls against each server to confirm the tenant works:

**Postgres:**
```bash
kubectl run -n mcp mcp-verify-pg-<TENANT> --rm -i --restart=Never --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-postgres-server:8001/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"pg_execute_query","arguments":{"tenant_id":"<TENANT>","query":"SELECT current_database(), current_user"}}}'
```
Expected: `current_database=<PG_DB>`, `current_user=<PG_USER>`

**Redis:**
```bash
kubectl run -n mcp mcp-verify-redis-<TENANT> --rm -i --restart=Never --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-redis-server:8010/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"redis_execute_command","arguments":{"tenant_id":"<TENANT>","command":"PING"}}}'
```
Expected: `result: true`

**MinIO:**
```bash
kubectl run -n mcp mcp-verify-minio-<TENANT> --rm -i --restart=Never --image=curlimages/curl:latest -- \
  -s -X POST http://mcp-minio-server:8002/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"minio_list_buckets","arguments":{"tenant_id":"<TENANT>"}}}'
```
Expected: bucket `<MINIO_BUCKET>` in list

**Letta:**
```bash
kubectl logs -n mcp deployment/mcp-letta-server --tail=30 | grep -i "<TENANT>"
```
Expected: log line showing org identity created for the tenant.

Then backfill the org identity ID:
```bash
# Extract from Redis
ORG_ID=$(kubectl run -n mcp redis-org-<TENANT> --rm -i --restart=Never --image=redis:7 -- \
  redis-cli -h redis -p 6379 -n 10 get "mcp:letta:tenant:<TENANT>" 2>/dev/null | \
  python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('org_identity_id',''))")

# Patch back into secret
kubectl get secret mcp-letta-tenants -n mcp -o jsonpath='{.data.tenants\.json}' | base64 -d | python3 -c "
import sys, json
data = json.load(sys.stdin)
data['<TENANT>']['org_identity_id'] = '$ORG_ID'
print(json.dumps(data))
" | kubectl create secret generic mcp-letta-tenants -n mcp \
    --from-file=tenants.json=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

### Phase 7: Summary Report

Print a summary table:

```
Tenant: <TENANT>
============================================================
| Server   | Infra Created       | Secret Patched | Verified |
|----------|--------------------:|:--------------:|:--------:|
| postgres | DB + user           | YES            | PASS     |
| redis    | N/A (shared)        | YES            | PASS     |
| minio    | bucket + policy     | YES            | PASS     |
| letta    | org identity        | YES            | PASS     |

Credentials:
  Postgres: user=<PG_USER> db=<PG_DB>
  MinIO:    key=<MINIO_KEY> bucket=<MINIO_BUCKET>
  Redis:    shared cluster (db=0)
  Letta:    org_identity_id=<ORG_ID>
```

## Error Recovery

- **Postgres user already exists**: Skip creation, just ensure DB exists and grants are in place
- **MinIO bucket already exists**: `--ignore-existing` handles this
- **MinIO user already exists**: `mc admin user add` will update the password
- **Pod won't start**: Check `kubectl describe pod -n mcp -l app=<service>` and `kubectl logs`
- **Tenant already in tenants.json**: Abort with error in pre-flight check
- **kubectl run pod name conflict**: Use unique names with tenant suffix, always `--rm -i --restart=Never`
