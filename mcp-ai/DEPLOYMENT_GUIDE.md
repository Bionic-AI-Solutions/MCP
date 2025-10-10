# MCP AI Server & Kong Unified Gateway - Deployment Guide

## Overview

This guide provides complete deployment instructions for the MCP AI Server with Kong as the unified external gateway. The setup includes:

- **MCP AI Server**: Secure Model Context Protocol server with direct AI service connections
- **Kong Unified Gateway**: Single external ingress point for all services
- **Security Features**: API key authentication, rate limiting, CORS, SSL/TLS
- **Network Policies**: Proper network isolation and access controls

## Architecture

```
Internet → WAN IP → Kong Gateway (192.168.0.210) → All Services
```

### Services Managed by Kong:
- `api.askcollections.com` (MCP AI Server)
- `argocd.askcollections.com` (ArgoCD)
- `argocd.bionicaisolutions.com` (ArgoCD)
- `rancher.bionicaisolutions.com` (Rancher)
- `coder.zippio.ai` (Coder)
- `staging.fedfina.com` (FedFina)
- `harbor.bionicaisolutions.com` (Harbor)
- `mail.bionicaisolutions.com` (Mail Service)
- `op.zippio.ai` (OpenProject)
- `pg.bionicaisolutions.com` (pgAdmin)

## Prerequisites

- Kubernetes cluster with Kong installed
- Kong LoadBalancer IP: `192.168.0.210`
- AI services running on `192.168.0.20` (ports 8000-8003)
- Cert-manager with Let's Encrypt configured
- External router configured to forward traffic to Kong

## Deployment Steps

### 1. Deploy MCP AI Server

```bash
# Apply the complete MCP AI server manifest
kubectl apply -f k8s/mcp-ai-server-complete.yaml

# Verify deployment
kubectl get pods -n mcp
kubectl get svc -n mcp
```

### 2. Deploy Kong Unified Gateway

```bash
# Apply the complete Kong unified gateway manifest
kubectl apply -f k8s/kong-unified-gateway-complete.yaml

# Verify Kong ingresses
kubectl get ingress -A | grep kong
```

### 3. Verify Deployment

```bash
# Test MCP AI server
curl -H "X-API-Key: admin-key-1234567890" \
     http://192.168.0.210/health

# Test external access
curl -H "X-API-Key: admin-key-1234567890" \
     https://api.askcollections.com/health
```

## Configuration Details

### MCP AI Server Features

- **Direct AI Service Connections**: Connects directly to AI services on `192.168.0.20`
- **API Key Authentication**: Required for all requests
- **Rate Limiting**: Configurable per API key role
- **CORS Support**: Configured for specific origins
- **Health Checks**: Liveness and readiness probes
- **Resource Limits**: CPU and memory constraints

### Kong Gateway Features

- **Unified External Access**: Single point of entry for all services
- **SSL/TLS Termination**: Let's Encrypt certificates
- **Rate Limiting**: 1000/min, 10000/hour, 100000/day
- **Request Size Limiting**: 10MB maximum
- **CORS Configuration**: Cross-origin resource sharing
- **Load Balancing**: Across service replicas

### Security Configuration

#### API Keys
- `admin-key-1234567890`: Admin role (10000 requests/hour)
- `user-key-0987654321`: User role (1000 requests/hour)
- `guest-key-1122334455`: Guest role (100 requests/hour)

#### Network Policies
- MCP AI server: Allows access from Kong, nginx, and ai-infrastructure namespaces
- Mail service: Updated to allow Kong access
- Egress rules: Allow access to AI services and DNS

## API Usage

### Authentication
Include API key in requests:
```bash
# Using X-API-Key header
curl -H "X-API-Key: admin-key-1234567890" \
     https://api.askcollections.com/health

# Using Authorization header
curl -H "Authorization: Bearer admin-key-1234567890" \
     https://api.askcollections.com/health
```

### Available Endpoints

#### MCP AI Server
- `GET /health` - Health check
- `GET /` - Service information
- `GET /api/routing/*` - AI Routing API proxy
- `GET /api/vllm/*` - VLLM Service proxy
- `GET /api/stt/*` - Speech-to-Text Service proxy
- `GET /api/tts/*` - Text-to-Speech Service proxy

#### Other Services
All other services are accessible through their respective domains via Kong.

## Monitoring and Troubleshooting

### Health Checks
```bash
# Check MCP AI server health
kubectl get pods -n mcp
kubectl logs -n mcp -l app=mcp-ai-direct

# Check Kong status
kubectl get pods -n kong
kubectl logs -n kong -l app=kong
```

### Updating API Keys
1. Edit the secret: `kubectl edit secret mcp-ai-api-keys -n mcp`
2. Update the JSON structure with new keys
3. Restart the deployment: `kubectl rollout restart deployment/mcp-ai-direct -n mcp`

### Troubleshooting Common Issues

#### Connection Issues
- Verify AI services are running on `192.168.0.20`
- Check network policies allow communication
- Ensure Kong is properly configured

#### Authentication Issues
- Verify API keys are correctly configured
- Check rate limits are not exceeded
- Ensure proper headers are included

#### SSL/TLS Issues
- Verify Let's Encrypt certificates are valid
- Check cert-manager is working
- Ensure DNS is properly configured

## Security Best Practices

- Rotate API keys regularly
- Monitor rate limit usage
- Use least privilege access
- Enable audit logging
- Regular security updates
- Network segmentation
- API keys are stored as Kubernetes secrets
- All communication is encrypted
- Rate limiting prevents abuse
- CORS is properly configured

## Performance Optimization

- Use appropriate resource limits
- Monitor CPU and memory usage
- Scale based on demand
- Optimize AI service connections
- Cache frequently used data
- Use connection pooling

## Backup and Recovery

- Regular backup of configurations
- Document all customizations
- Test recovery procedures
- Version control all changes
- Monitor system health
- Automated backup scripts

## Support and Maintenance

- Regular updates and patches
- Monitor system performance
- Review security logs
- Update documentation
- Test disaster recovery
- Performance tuning

---

**Last Updated**: January 2024  
**Version**: 3.0.0  
**Maintainer**: Bionic AI Solutions