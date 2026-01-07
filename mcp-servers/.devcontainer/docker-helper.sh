#!/bin/bash
# Helper script for Docker operations in devcontainer

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to login to Docker Hub
docker_login() {
    if [ -z "$DOCKER_USERNAME" ] || [ -z "$DOCKER_PASSWORD" ]; then
        echo -e "${YELLOW}⚠️  DOCKER_USERNAME and DOCKER_PASSWORD environment variables not set${NC}"
        echo "Please set them or run: docker login"
        return 1
    fi
    
    echo -e "${GREEN}🔐 Logging in to Docker Hub...${NC}"
    echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin
    echo -e "${GREEN}✅ Logged in successfully${NC}"
}

# Function to build and push an image
build_and_push() {
    local SERVER_NAME=$1
    local IMAGE_TAG=${2:-latest}
    local DOCKER_REGISTRY=${DOCKER_REGISTRY:-docker.io/docker4zerocool}
    local IMAGE_NAME="${DOCKER_REGISTRY}/mcp-servers-${SERVER_NAME}:${IMAGE_TAG}"
    
    if [ -z "$SERVER_NAME" ]; then
        echo "Usage: build_and_push <server-name> [tag]"
        echo "Example: build_and_push openproject latest"
        return 1
    fi
    
    echo -e "${GREEN}🔨 Building image: ${IMAGE_NAME}${NC}"
    docker build --target "${SERVER_NAME}" -t "${IMAGE_NAME}" .
    
    echo -e "${GREEN}📤 Pushing image: ${IMAGE_NAME}${NC}"
    docker push "${IMAGE_NAME}"
    
    echo -e "${GREEN}✅ Successfully built and pushed ${IMAGE_NAME}${NC}"
}

# Function to build all server images
build_all() {
    local TAG=${1:-latest}
    local DOCKER_REGISTRY=${DOCKER_REGISTRY:-docker.io/docker4zerocool}
    
    echo -e "${GREEN}🔨 Building all MCP server images...${NC}"
    
    local SERVERS=("calculator" "postgres" "minio" "pdf-generator" "ffmpeg" "mail" "openproject")
    
    for server in "${SERVERS[@]}"; do
        echo -e "${GREEN}Building ${server}...${NC}"
        build_and_push "$server" "$TAG" || echo -e "${YELLOW}⚠️  Failed to build ${server}${NC}"
    done
    
    echo -e "${GREEN}✅ All images built${NC}"
}

# Main command handler
case "${1:-}" in
    login)
        docker_login
        ;;
    build)
        build_and_push "$2" "$3"
        ;;
    build-all)
        build_all "$2"
        ;;
    *)
        echo "MCP Servers Docker Helper"
        echo ""
        echo "Usage:"
        echo "  docker-helper.sh login                    - Login to Docker Hub"
        echo "  docker-helper.sh build <server> [tag]     - Build and push a specific server"
        echo "  docker-helper.sh build-all [tag]         - Build and push all servers"
        echo ""
        echo "Examples:"
        echo "  docker-helper.sh login"
        echo "  docker-helper.sh build openproject latest"
        echo "  docker-helper.sh build-all v1.0.0"
        echo ""
        echo "Environment variables:"
        echo "  DOCKER_USERNAME      - Docker Hub username"
        echo "  DOCKER_PASSWORD      - Docker Hub password/token"
        echo "  DOCKER_REGISTRY      - Docker registry (default: docker.io/docker4zerocool)"
        ;;
esac









