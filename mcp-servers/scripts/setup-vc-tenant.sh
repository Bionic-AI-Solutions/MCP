#!/bin/bash
# Setup script for VC tenant provisioning
# This script creates the necessary resources in Postgres and MinIO for the vc tenant.
#
# Prerequisites:
#   - kubectl access to the cluster
#   - psql client (or exec into a postgres pod)
#   - mc (MinIO client) configured, or exec into a MinIO pod
#
# Usage: bash scripts/setup-vc-tenant.sh

set -euo pipefail

echo "========================================="
echo " VC Tenant Provisioning"
echo "========================================="

# -----------------------------------------------
# 1. PostgreSQL: Create vc database and user
# -----------------------------------------------
echo ""
echo "[1/2] Setting up PostgreSQL database and user..."
echo ""

# Option A: Via kubectl exec into a postgres pod
# Adjust the pod name/namespace as needed
POSTGRES_POD=$(kubectl get pods -n pg -l app=postgres -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
if [ -z "$POSTGRES_POD" ]; then
    # Try patroni/stolon-based naming
    POSTGRES_POD=$(kubectl get pods -n pg -l role=master -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
fi

if [ -n "$POSTGRES_POD" ]; then
    echo "Found PostgreSQL pod: $POSTGRES_POD"
    kubectl exec -n pg "$POSTGRES_POD" -- psql -U postgres -c "
        -- Create vc user if not exists
        DO \$\$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'vc') THEN
                CREATE ROLE vc WITH LOGIN PASSWORD 'vcTh1515T0p53cr3t';
            END IF;
        END
        \$\$;

        -- Create vc database if not exists
        SELECT 'CREATE DATABASE vc OWNER vc'
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'vc')
        \gexec

        -- Grant privileges
        GRANT ALL PRIVILEGES ON DATABASE vc TO vc;
    "
    echo "PostgreSQL vc database and user created successfully."
else
    echo "WARNING: Could not find PostgreSQL pod automatically."
    echo "Please run the following SQL manually on your PostgreSQL primary:"
    echo ""
    echo "  -- Connect as superuser (postgres)"
    echo "  CREATE ROLE vc WITH LOGIN PASSWORD 'vcTh1515T0p53cr3t';"
    echo "  CREATE DATABASE vc OWNER vc;"
    echo "  GRANT ALL PRIVILEGES ON DATABASE vc TO vc;"
    echo ""
fi

# -----------------------------------------------
# 2. MinIO: Create bucket, policy, and user
# -----------------------------------------------
echo ""
echo "[2/2] Setting up MinIO bucket, policy, and user..."
echo ""

# Check if mc (MinIO client) is available
if command -v mc &> /dev/null; then
    MC_CMD="mc"
elif command -v kubectl &> /dev/null; then
    # Try to exec into a MinIO pod
    MC_CMD=""
    echo "mc not found locally, will attempt kubectl exec..."
else
    MC_CMD=""
fi

# MinIO connection details
MINIO_ALIAS="mcp-minio"
MINIO_ENDPOINT="https://minio.bionicaisolutions.com"
MINIO_ADMIN_ACCESS_KEY="admin"
MINIO_ADMIN_SECRET_KEY="Th1515T0p53cr3t"

if [ -n "$MC_CMD" ]; then
    # Configure mc alias
    $MC_CMD alias set "$MINIO_ALIAS" "$MINIO_ENDPOINT" "$MINIO_ADMIN_ACCESS_KEY" "$MINIO_ADMIN_SECRET_KEY" 2>/dev/null || true

    # Create vc bucket
    echo "Creating vc bucket..."
    $MC_CMD mb "${MINIO_ALIAS}/vc-data" --ignore-existing

    # Create restricted policy for vc tenant
    echo "Creating vc-restricted policy..."
    cat > /tmp/vc-policy.json << 'POLICY_EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:ListMultipartUploadParts",
                "s3:AbortMultipartUpload"
            ],
            "Resource": [
                "arn:aws:s3:::vc-data",
                "arn:aws:s3:::vc-data/*"
            ]
        }
    ]
}
POLICY_EOF

    $MC_CMD admin policy create "$MINIO_ALIAS" vc-restricted /tmp/vc-policy.json
    rm -f /tmp/vc-policy.json

    # Create vc user
    echo "Creating vc user..."
    $MC_CMD admin user add "$MINIO_ALIAS" vcuser "vcTh1515T0p53cr3t"

    # Attach policy to user
    echo "Attaching vc-restricted policy to vc user..."
    $MC_CMD admin policy attach "$MINIO_ALIAS" vc-restricted --user vcuser

    echo "MinIO vc bucket, policy, and user created successfully."
else
    echo "mc (MinIO client) not found. Please run these commands manually:"
    echo ""
    echo "  # Set up mc alias"
    echo "  mc alias set mcp-minio ${MINIO_ENDPOINT} ${MINIO_ADMIN_ACCESS_KEY} ${MINIO_ADMIN_SECRET_KEY}"
    echo ""
    echo "  # Create vc bucket"
    echo "  mc mb mcp-minio/vc-data --ignore-existing"
    echo ""
    echo "  # Create vc-restricted policy (save as /tmp/vc-policy.json first):"
    cat << 'POLICY_DISPLAY'
  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Effect": "Allow",
              "Action": [
                  "s3:GetObject",
                  "s3:PutObject",
                  "s3:DeleteObject",
                  "s3:ListBucket",
                  "s3:GetBucketLocation",
                  "s3:ListMultipartUploadParts",
                  "s3:AbortMultipartUpload"
              ],
              "Resource": [
                  "arn:aws:s3:::vc-data",
                  "arn:aws:s3:::vc-data/*"
              ]
          }
      ]
  }
POLICY_DISPLAY
    echo ""
    echo "  mc admin policy create mcp-minio vc-restricted /tmp/vc-policy.json"
    echo ""
    echo "  # Create vc user and attach policy"
    echo "  mc admin user add mcp-minio vcuser vcTh1515T0p53cr3t"
    echo "  mc admin policy attach mcp-minio vc-restricted --user vcuser"
    echo ""
fi

echo ""
echo "========================================="
echo " VC Tenant Provisioning Complete"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Apply K8s configs: kubectl apply -k k8s/"
echo "  2. Restart MCP server pods to pick up new tenant configs"
echo "  3. Verify with: kubectl logs -n mcp <pod-name> | grep -i 'vc'"
