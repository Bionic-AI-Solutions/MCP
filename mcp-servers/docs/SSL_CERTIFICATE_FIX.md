# SSL Certificate Fix for MCP Servers

## Problem

Cursor was unable to connect to the MCP servers due to a self-signed SSL certificate error:

```
TypeError: fetch failed: self-signed certificate
```

## Solution

A Let's Encrypt certificate has been provisioned for `mcp.baisoln.com` using cert-manager.

### Certificate Status

- **Certificate Name**: `mcp-baisoln-com-tls`
- **Namespace**: `mcp`
- **Issuer**: `letsencrypt-prod` (Let's Encrypt Production)
- **Status**: ✅ Ready and automatically renewing

### Configuration Files

1. **Certificate Resource**: `/home/skadam/git/MCP/mcp-servers/k8s/certificate.yaml`
   - Automatically provisions Let's Encrypt certificate
   - Auto-renews before expiration

2. **Ingress Configuration**: Updated to use the TLS secret
   - Added `cert-manager.io/cluster-issuer: "letsencrypt-prod"` annotation
   - Added `tls` section with secret reference

### Verification

Test the certificate:

```bash
# Should work without -k flag (no insecure SSL)
curl https://mcp.baisoln.com/calculator/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
```

### Next Steps

1. **Restart Cursor** completely to clear the cached SSL error
2. **Verify connection** - Cursor should now connect without SSL errors
3. **Check MCP logs** in Cursor (View > Output > MCP) - should show successful connection

### Certificate Renewal

The certificate is automatically renewed by cert-manager before expiration. No manual intervention required.

### Troubleshooting

If certificate provisioning fails:

1. **Check certificate status**:
   ```bash
   kubectl get certificate -n mcp mcp-baisoln-com-tls
   kubectl describe certificate -n mcp mcp-baisoln-com-tls
   ```

2. **Check certificate request**:
   ```bash
   kubectl get certificaterequest -n mcp
   kubectl describe certificaterequest -n mcp <request-name>
   ```

3. **Check ACME challenges**:
   ```bash
   kubectl get challenges -n mcp
   kubectl describe challenge -n mcp <challenge-name>
   ```

4. **Verify DNS**:
   - Ensure `mcp.baisoln.com` resolves to the correct IP
   - Let's Encrypt must be able to reach the domain for validation

### Related Files

- Certificate: `/home/skadam/git/MCP/mcp-servers/k8s/certificate.yaml`
- Ingress: `/home/skadam/git/MCP/mcp-servers/k8s/kong/calculator-routes.yaml`
















