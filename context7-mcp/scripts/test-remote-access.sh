#!/bin/bash

# Test Remote Access to Context7 MCP Server
# This script tests connectivity from different network perspectives

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get server IP
SERVER_IP=$(hostname -I | awk '{print $1}')
PORT=8080

print_status "Testing remote access to Context7 MCP Server"
print_status "Server IP: $SERVER_IP"
print_status "Port: $PORT"
echo ""

# Test 1: Localhost access
print_status "Test 1: Localhost access"
if curl -s http://localhost:$PORT/ping > /dev/null; then
    print_success "✓ Localhost access working"
else
    print_error "✗ Localhost access failed"
fi
echo ""

# Test 2: Network interface access
print_status "Test 2: Network interface access ($SERVER_IP)"
if curl -s http://$SERVER_IP:$PORT/ping > /dev/null; then
    print_success "✓ Network interface access working"
else
    print_error "✗ Network interface access failed"
fi
echo ""

# Test 3: Check network binding
print_status "Test 3: Network binding check"
if netstat -tlnp 2>/dev/null | grep -q ":$PORT.*LISTEN.*0.0.0.0"; then
    print_success "✓ Server listening on all interfaces (0.0.0.0:$PORT)"
else
    print_warning "⚠ Server may not be listening on all interfaces"
fi
echo ""

# Test 4: MCP endpoint accessibility
print_status "Test 4: MCP endpoint accessibility"
if curl -s -I http://$SERVER_IP:$PORT/mcp | grep -q "HTTP"; then
    print_success "✓ MCP endpoint accessible"
else
    print_error "✗ MCP endpoint not accessible"
fi
echo ""

# Test 5: SSE endpoint accessibility
print_status "Test 5: SSE endpoint accessibility"
if curl -s -I http://$SERVER_IP:$PORT/sse | grep -q "HTTP"; then
    print_success "✓ SSE endpoint accessible"
else
    print_error "✗ SSE endpoint not accessible"
fi
echo ""

# Summary
print_status "Remote Access Summary:"
print_status "For Cursor on different machine, use:"
echo "  http://$SERVER_IP:$PORT/mcp"
echo ""
print_status "For VS Code on different machine, use:"
echo "  http://$SERVER_IP:$PORT/mcp"
echo ""
print_status "Health check:"
echo "  http://$SERVER_IP:$PORT/ping"
echo ""

# Check if server is running
if docker ps | grep -q "context7-mcp-server"; then
    print_success "✓ Context7 MCP server is running"
else
    print_error "✗ Context7 MCP server is not running"
    print_status "Start it with: ./scripts/docker-helper.sh start"
fi
