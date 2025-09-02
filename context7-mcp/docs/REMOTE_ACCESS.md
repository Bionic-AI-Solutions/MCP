# Context7 MCP Server - Remote Access Guide

This guide explains how to access the context7 MCP server from other machines on your network or over the internet.

## 🌐 Current Server Configuration

Your context7 MCP server is configured to accept connections from all network interfaces:
- **Local Access**: `http://localhost:8080`
- **Network Access**: `http://192.168.0.21:8080` (your server's IP)
- **Port**: 8080

## 🔧 Remote Machine Configuration

### For Cursor on Different Machine

Add this to your `~/.cursor/mcp.json` on the remote machine:

```json
{
  "mcpServers": {
    "context7": {
      "url": "http://192.168.0.21:8080/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### For VS Code on Different Machine

Add this to your VS Code MCP configuration:

```json
{
  "mcpServers": {
    "context7": {
      "url": "http://192.168.0.21:8080/mcp",
      "headers": {
        "CONTEXT7_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

## 🌍 Network Access Options

### Option 1: Local Network Access (Recommended)

**Use your server's local IP address:**
- **URL**: `http://192.168.0.21:8080/mcp`
- **Pros**: Fast, secure within your network
- **Cons**: Only works when both machines are on the same network

### Option 2: Internet Access via Port Forwarding

If you want to access from anywhere on the internet:

1. **Configure your router** to forward port 8080 to your server (192.168.0.21)
2. **Use your public IP address** or domain name
3. **URL**: `http://your-public-ip:8080/mcp` or `http://yourdomain.com:8080/mcp`

⚠️ **Security Warning**: Exposing to the internet requires proper security measures!

### Option 3: VPN Access

1. **Set up a VPN** (WireGuard, OpenVPN, etc.)
2. **Connect both machines** to the VPN
3. **Use the VPN IP address** for connection

## 🔒 Security Considerations

### For Local Network Access
- ✅ Generally safe within trusted networks
- ✅ No additional security needed for home/office networks

### For Internet Access
- 🔒 **Required**: Firewall rules
- 🔒 **Required**: Rate limiting
- 🔒 **Recommended**: API key authentication
- 🔒 **Recommended**: HTTPS (SSL/TLS)

## 🧪 Testing Remote Access

### Test from Remote Machine

```bash
# Test health endpoint
curl http://192.168.0.21:8080/ping

# Test MCP endpoint
curl http://192.168.0.21:8080/mcp
```

### Test from Different Network

If you have access to a different network (e.g., mobile hotspot):

```bash
# Connect to different network
# Then test the connection
curl http://192.168.0.21:8080/ping
```

## 🚀 Advanced Configuration

### Custom Port Mapping

If you want to use a different external port:

```yaml
# In docker-compose.yml
ports:
  - "0.0.0.0:9090:8080"  # External port 9090, internal port 8080
```

Then use: `http://192.168.0.21:9090/mcp`

### Multiple Network Interfaces

If your server has multiple network interfaces, you can bind to specific ones:

```yaml
# In docker-compose.yml
ports:
  - "192.168.0.21:8080:8080"  # Bind to specific interface
```

## 🔍 Troubleshooting Remote Access

### Common Issues

1. **Connection Refused**
   ```bash
   # Check if server is listening on all interfaces
   netstat -tlnp | grep :8080
   # Should show: 0.0.0.0:8080
   ```

2. **Firewall Blocking**
   ```bash
   # Check firewall status
   sudo ufw status
   
   # Allow port 8080
   sudo ufw allow 8080
   ```

3. **Router Blocking**
   - Check router settings
   - Ensure port forwarding is configured
   - Verify the server IP is correct

4. **Network Configuration**
   ```bash
   # Check server IP
   hostname -I
   
   # Test local connectivity
   ping 192.168.0.21
   ```

### Debug Commands

```bash
# Check server status
./scripts/docker-helper.sh status

# View server logs
./scripts/docker-helper.sh logs

# Check network binding
netstat -tlnp | grep :8080

# Test from server itself
curl http://localhost:8080/ping
curl http://192.168.0.21:8080/ping
```

## 📱 Mobile/Tablet Access

You can also access the server from mobile devices on the same network:

- **Health Check**: `http://192.168.0.21:8080/ping`
- **MCP Endpoint**: `http://192.168.0.21:8080/mcp`

## 🌐 Domain Name Setup (Optional)

For easier access, you can set up a domain name:

1. **Register a domain** (e.g., `mycontext7.com`)
2. **Point it to your server's IP** (192.168.0.21)
3. **Use the domain**: `http://mycontext7.com:8080/mcp`

## 📋 Quick Reference

| Access Type | URL | Use Case |
|-------------|-----|----------|
| **Local** | `http://localhost:8080/mcp` | Same machine |
| **Network** | `http://192.168.0.21:8080/mcp` | Same network |
| **Internet** | `http://your-public-ip:8080/mcp` | Anywhere (with port forwarding) |
| **VPN** | `http://vpn-ip:8080/mcp` | VPN-connected machines |

## 🔄 Updating Configuration

After making changes to the server configuration:

1. **Restart the server**:
   ```bash
   ./scripts/docker-helper.sh restart
   ```

2. **Update client configurations** on remote machines

3. **Test the connection** from remote machines

## 📞 Support

For issues with remote access:
- Check the [main Docker setup guide](./DOCKER_SETUP.md)
- Verify network connectivity
- Check firewall and router settings
- Review server logs for errors
