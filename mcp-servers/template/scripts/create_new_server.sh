#!/bin/bash
# Script to create a new MCP server from the template

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check arguments
if [ $# -lt 2 ]; then
    print_error "Usage: $0 <server-name> <port> [description]"
    echo "Example: $0 my-service 8003 'My Service MCP Server'"
    exit 1
fi

SERVER_NAME="$1"
PORT="$2"
DESCRIPTION="${3:-${SERVER_NAME^} MCP Server}"

# Validate server name (lowercase, alphanumeric and hyphens only)
if [[ ! "$SERVER_NAME" =~ ^[a-z0-9-]+$ ]]; then
    print_error "Server name must be lowercase and contain only alphanumeric characters and hyphens"
    exit 1
fi

# Generate abbreviation for tool prefixes
# Common abbreviations - extend this mapping as needed
case "$SERVER_NAME" in
    postgres)
        SERVER_NAME_ABBR="pg"
        ;;
    calculator)
        SERVER_NAME_ABBR="calc"
        ;;
    pdf-generator)
        SERVER_NAME_ABBR="pdf"
        ;;
    *)
        # Default: use first part before hyphen, or full name if no hyphen
        SERVER_NAME_ABBR=$(echo "$SERVER_NAME" | cut -d'-' -f1)
        ;;
esac

# Validate port
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 8000 ] || [ "$PORT" -gt 8999 ]; then
    print_error "Port must be a number between 8000 and 8999"
    exit 1
fi

# Check if server already exists
if [ -d "src/mcp_servers/$SERVER_NAME" ]; then
    print_error "Server '$SERVER_NAME' already exists!"
    exit 1
fi

# Check if port is already in use
if grep -q ":$PORT:" docker-compose.yml 2>/dev/null; then
    print_warn "Port $PORT appears to be in use. Please verify."
fi

print_info "Creating new MCP server: $SERVER_NAME"
print_info "Port: $PORT"
print_info "Description: $DESCRIPTION"

# Get the next available Redis DB number
MAX_REDIS_DB=$(grep -o "REDIS_DB=[0-9]*" docker-compose.yml 2>/dev/null | sed 's/REDIS_DB=//' | sort -n | tail -1 || echo "-1")
NEXT_REDIS_DB=$((MAX_REDIS_DB + 1))

print_info "Using Redis DB: $NEXT_REDIS_DB"

# Create server directory
print_info "Creating server directory..."
mkdir -p "src/mcp_servers/$SERVER_NAME"

# Copy template files
print_info "Copying template files..."
cp template/src/mcp_servers/SERVER_NAME/__init__.py "src/mcp_servers/$SERVER_NAME/__init__.py"
cp template/src/mcp_servers/SERVER_NAME/server.py "src/mcp_servers/$SERVER_NAME/server.py"
cp template/src/mcp_servers/SERVER_NAME/tenant_manager.py "src/mcp_servers/$SERVER_NAME/tenant_manager.py"
cp template/src/mcp_servers/SERVER_NAME/client.py "src/mcp_servers/$SERVER_NAME/client.py"

# Replace placeholders in all files
print_info "Replacing placeholders..."
find "src/mcp_servers/$SERVER_NAME" -type f -exec sed -i "s/SERVER_NAME/$SERVER_NAME/g" {} +
find "src/mcp_servers/$SERVER_NAME" -type f -exec sed -i "s/Server Name Server/$DESCRIPTION/g" {} +

# Update server.py to use proper case for class names
SERVER_NAME_CAMEL=$(echo "$SERVER_NAME" | sed 's/-\([a-z]\)/\U\1/g' | sed 's/^\([a-z]\)/\U\1/')
find "src/mcp_servers/$SERVER_NAME" -type f -exec sed -i "s/SERVER_NAMETenantManager/${SERVER_NAME_CAMEL}TenantManager/g" {} +
find "src/mcp_servers/$SERVER_NAME" -type f -exec sed -i "s/SERVER_NAMETenantConfig/${SERVER_NAME_CAMEL}TenantConfig/g" {} +

# Update tool names to use server abbreviation prefix
find "src/mcp_servers/$SERVER_NAME" -type f -exec sed -i "s/SERVER_NAME_ABBR/${SERVER_NAME_ABBR}_/g" {} +

# Create example file
print_info "Creating example file..."
mkdir -p "examples"
cp template/examples/example_usage.py "examples/${SERVER_NAME}_example.py"
sed -i "s/SERVER_NAME/$SERVER_NAME/g" "examples/${SERVER_NAME}_example.py"

# Generate Dockerfile snippet
print_info "Generating Dockerfile snippet..."
cat > "docker/${SERVER_NAME}_Dockerfile.snippet" << EOF
# ${SERVER_NAME^} stage
FROM base as ${SERVER_NAME}
COPY src/ ./src/
WORKDIR /app
ENV PYTHONPATH=/app/src
EXPOSE ${PORT}
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \\
    CMD curl -f http://localhost:${PORT}/health || exit 1
CMD ["fastmcp", "run", "src/mcp_servers/${SERVER_NAME}/server.py", "--transport", "http", "--port", "${PORT}", "--host", "0.0.0.0"]
EOF

# Generate docker-compose snippet
print_info "Generating docker-compose snippet..."
cat > "docker/${SERVER_NAME}_docker-compose.snippet" << EOF
  # ${DESCRIPTION}
  mcp-${SERVER_NAME}-server:
    build:
      context: .
      dockerfile: Dockerfile
      target: ${SERVER_NAME}
    container_name: mcp-${SERVER_NAME}-server
    ports:
      - "${PORT}:${PORT}"
    environment:
      - SERVER_NAME=${DESCRIPTION}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=${NEXT_REDIS_DB}
      # Add your tenant environment variables here
      # Example:
      # - ${SERVER_NAME^^}_TENANT_1_API_KEY=\${${SERVER_NAME^^}_TENANT_1_API_KEY:-default_key}
    restart: unless-stopped
    networks:
      - mcp-network
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:${PORT}/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
EOF

# Generate nginx snippet
print_info "Generating nginx snippet..."
cat > "nginx/${SERVER_NAME}_nginx.snippet" << EOF
        # ${DESCRIPTION}
        # Route: mcp.bionicaisolutions.com/${SERVER_NAME}/mcp
        location = /${SERVER_NAME}/mcp {
            proxy_pass http://mcp_${SERVER_NAME}_backend/mcp;
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_set_header Accept "application/json, text/event-stream";
            proxy_buffering off;
            proxy_cache off;
        }

        location = /${SERVER_NAME}/ {
            proxy_set_header Mcp-Session-Id \$mcp_session_id;
            proxy_http_version 1.1;
            proxy_set_header Host 127.0.0.1:8000;
            proxy_set_header Accept "application/json, text/event-stream";
            
            if (\$request_method = POST) {
                rewrite ^ /mcp break;
                proxy_pass http://mcp_${SERVER_NAME}_backend;
                break;
            }
            return 301 /${SERVER_NAME}/sse;
        }
        
        location = /${SERVER_NAME}/sse {
            proxy_http_version 1.1;
            proxy_set_header Host 127.0.0.1:8000;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_set_header Accept "application/json, text/event-stream";
            proxy_set_header Mcp-Session-Id \$mcp_session_id;
            proxy_buffering off;
            proxy_cache off;
            
            if (\$request_method = POST) {
                rewrite ^ /mcp break;
            }
            rewrite ^/${SERVER_NAME}/(.*) /\$1 break;
            proxy_pass http://mcp_${SERVER_NAME}_backend;
        }
        
        location ~ ^/${SERVER_NAME}/messages {
            rewrite ^/${SERVER_NAME}/messages(.*)\$ /messages/\$1 break;
            proxy_pass http://mcp_${SERVER_NAME}_backend;
            proxy_http_version 1.1;
            proxy_set_header Host 127.0.0.1:8000;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_buffering off;
            proxy_cache off;
        }
        
        location ~ ^/${SERVER_NAME}/message(?:s)?/? {
            rewrite ^/${SERVER_NAME}/message(s)?(.*)\$ /messages\$2 break;
            proxy_pass http://mcp_${SERVER_NAME}_backend;
            proxy_http_version 1.1;
            proxy_set_header Host 127.0.0.1:8000;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_buffering off;
            proxy_cache off;
        }
        
        location /${SERVER_NAME}/ {
            rewrite ^/${SERVER_NAME}/(.*) /\$1 break;
            proxy_pass http://mcp_${SERVER_NAME}_backend;
            proxy_http_version 1.1;
            proxy_set_header Host 127.0.0.1:8000;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto \$scheme;
            proxy_set_header Accept "application/json, text/event-stream";
            proxy_buffering off;
            proxy_cache off;
        }

        location /${SERVER_NAME}/health {
            proxy_pass http://mcp_${SERVER_NAME}_backend/health;
            proxy_http_version 1.1;
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        }
EOF

print_info "Server created successfully!"
echo ""
print_info "Next steps:"
echo "  1. Review and customize: src/mcp_servers/${SERVER_NAME}/"
echo "  2. Add Dockerfile stage from: docker/${SERVER_NAME}_Dockerfile.snippet"
echo "  3. Add docker-compose service from: docker/${SERVER_NAME}_docker-compose.snippet"
echo "  4. Add nginx upstream: upstream mcp_${SERVER_NAME}_backend { server mcp-${SERVER_NAME}-server:${PORT}; keepalive 32; }"
echo "  5. Add nginx locations from: nginx/${SERVER_NAME}_nginx.snippet"
echo "  6. Update mcp_client_config_cursor_remote.json with:"
echo "     \"${SERVER_NAME}-mcp-remote\": {"
echo "       \"url\": \"https://mcp.bionicaisolutions.com/${SERVER_NAME}/mcp\""
echo "     }"
echo "  7. Build and test: docker compose build mcp-${SERVER_NAME}-server"
echo "  8. Start: docker compose up -d mcp-${SERVER_NAME}-server"

