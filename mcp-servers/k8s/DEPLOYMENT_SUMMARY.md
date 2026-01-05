# MCP Servers - Kubernetes Deployment Summary

## Overview

Complete Kubernetes manifests have been created for deploying all 4 MCP servers to a Kubernetes cluster with Kong as the ingress gateway.

## Created Resources

### 1. Namespace
- **File**: `namespace.yaml`
- Creates the `mcp` namespace for all MCP server resources

### 2. Redis Service
- **File**: `redis-service.yaml`
- Redis deployment and service for tenant configuration storage
- Required by: postgres, minio, pdf-generator servers

### 3. MCP Server Deployments

#### Calculator Server
- **Files**: `calculator/deployment.yaml`
- **Service**: `mcp-calculator-server:8000`
- **Endpoints**:
  - `https://mcp.baisoln.com/calculator/mcp` (HTTP)
  - `https://mcp.baisoln.com/calculator/sse` (SSE)
  - `https://mcp.baisoln.com/calculator/health` (Health)

#### Postgres Server
- **Files**: `postgres/deployment.yaml`
- **Service**: `mcp-postgres-server:8001`
- **Endpoints**:
  - `https://mcp.baisoln.com/postgres/mcp` (HTTP)
  - `https://mcp.baisoln.com/postgres/sse` (SSE)
  - `https://mcp.baisoln.com/postgres/health` (Health)
- **Config**: ConfigMap + Secrets for tenant database credentials

#### MinIO Server
- **Files**: `minio/deployment.yaml`
- **Service**: `mcp-minio-server:8002`
- **Endpoints**:
  - `https://mcp.baisoln.com/minio/mcp` (HTTP)
  - `https://mcp.baisoln.com/minio/sse` (SSE)
  - `https://mcp.baisoln.com/minio/health` (Health)
- **Config**: ConfigMap + Secrets for tenant MinIO credentials

#### PDF Generator Server
- **Files**: `pdf-generator/deployment.yaml`
- **Service**: `mcp-pdf-generator-server:8003`
- **Endpoints**:
  - `https://mcp.baisoln.com/pdf-generator/mcp` (HTTP)
  - `https://mcp.baisoln.com/pdf-generator/sse` (SSE)
  - `https://mcp.baisoln.com/pdf-generator/health` (Health)
- **Config**: ConfigMap for PDF generation settings
- **Note**: Supports 50MB request body size

### 4. Kong Ingress Routes

Each server has a dedicated Kong Ingress configuration with:
- **CORS Plugin**: Cross-origin resource sharing enabled
- **Rate Limiting Plugin**: 1000/min, 10k/hour, 100k/day
- **SSL/TLS**: HTTPS termination at Kong
- **Multiple Paths**: `/mcp`, `/sse`, `/messages`, `/health`

**Files**:
- `kong/calculator-routes.yaml`
- `kong/postgres-routes.yaml`
- `kong/minio-routes.yaml`
- `kong/pdf-generator-routes.yaml`

### 5. Deployment Tools

- **kustomization.yaml**: Kustomize configuration for easy deployment
- **deploy.sh**: Automated deployment script
- **build-images.sh**: Docker image build script
- **README.md**: Comprehensive documentation
- **QUICK_START.md**: Quick reference guide

## Deployment Structure

```
k8s/
├── namespace.yaml                    # MCP namespace
├── redis-service.yaml                # Redis for tenant storage
├── kustomization.yaml                # Kustomize config
├── deploy.sh                         # Deployment script
├── build-images.sh                   # Image build script
├── README.md                         # Full documentation
├── QUICK_START.md                    # Quick start guide
├── calculator/
│   └── deployment.yaml              # Calculator server
├── postgres/
│   └── deployment.yaml              # Postgres server
├── minio/
│   └── deployment.yaml              # MinIO server
├── pdf-generator/
│   └── deployment.yaml              # PDF Generator server
└── kong/
    ├── calculator-routes.yaml       # Calculator Kong routes
    ├── postgres-routes.yaml         # Postgres Kong routes
    ├── minio-routes.yaml            # MinIO Kong routes
    └── pdf-generator-routes.yaml    # PDF Generator Kong routes
```

## Key Features

### High Availability
- All deployments configured with 2 replicas
- Health checks (liveness and readiness probes)
- Resource limits and requests

### Security
- Secrets for sensitive data (database credentials, MinIO keys)
- ConfigMaps for non-sensitive configuration
- Kong rate limiting and CORS protection
- HTTPS/TLS termination at Kong

### Scalability
- Horizontal scaling ready (can add HPA)
- Resource limits configured
- Connection pooling for database services

### Observability
- Health check endpoints for all services
- Structured logging ready
- Kong plugins for monitoring

## Next Steps

1. **Build Images**: Run `./k8s/build-images.sh` to build Docker images
2. **Update Images**: Edit `k8s/kustomization.yaml` with your registry
3. **Configure Secrets**: Update tenant secrets if needed
4. **Deploy**: Run `./k8s/deploy.sh` or `kubectl apply -k k8s/`
5. **Verify**: Test endpoints using the health check URLs

## Kong Routes Created

All routes are configured under `mcp.baisoln.com`:

| Server | HTTP Endpoint | SSE Endpoint | Health Endpoint |
|--------|--------------|--------------|-----------------|
| Calculator | `/calculator/mcp` | `/calculator/sse` | `/calculator/health` |
| Postgres | `/postgres/mcp` | `/postgres/sse` | `/postgres/health` |
| MinIO | `/minio/mcp` | `/minio/sse` | `/minio/health` |
| PDF Generator | `/pdf-generator/mcp` | `/pdf-generator/sse` | `/pdf-generator/health` |

## Notes

- All servers use the same base Docker image with different entrypoints
- Redis is required for multi-tenant servers (postgres, minio, pdf-generator)
- Kong handles SSL/TLS termination and routing
- Rate limiting is configured per server
- CORS is enabled for all servers to allow cross-origin requests








