#!/bin/bash

# Context7 MCP Server Docker Helper Script
# This script provides easy commands to manage the Context7 MCP server in Docker

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

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker and try again."
        exit 1
    fi
}

# Function to build the Docker image
build() {
    print_status "Building Context7 MCP server Docker image..."
    cd "$PROJECT_ROOT"
    docker build -t context7-mcp:latest .
    print_success "Docker image built successfully!"
}

# Function to start the server using docker-compose
start() {
    print_status "Starting Context7 MCP server using docker-compose..."
    cd "$PROJECT_ROOT"
    check_docker
    
    # Create config directory if it doesn't exist
    mkdir -p config
    
    docker-compose up -d
    print_success "Context7 MCP server started successfully!"
    print_status "Server is running on http://localhost:8080"
    print_status "MCP endpoint: http://localhost:8080/mcp"
    print_status "SSE endpoint: http://localhost:8080/sse"
    print_status "Health check: http://localhost:8080/ping"
}

# Function to stop the server
stop() {
    print_status "Stopping Context7 MCP server..."
    cd "$PROJECT_ROOT"
    docker-compose down
    print_success "Context7 MCP server stopped successfully!"
}

# Function to restart the server
restart() {
    print_status "Restarting Context7 MCP server..."
    stop
    start
}

# Function to view logs
logs() {
    cd "$PROJECT_ROOT"
    docker-compose logs -f context7-mcp
}

# Function to check server status
status() {
    cd "$PROJECT_ROOT"
    if docker-compose ps | grep -q "Up"; then
        print_success "Context7 MCP server is running"
        print_status "Container details:"
        docker-compose ps
        print_status "Server endpoints:"
        print_status "  - MCP: http://localhost:8080/mcp"
        print_status "  - SSE: http://localhost:8080/sse"
        print_status "  - Health: http://localhost:8080/ping"
    else
        print_warning "Context7 MCP server is not running"
    fi
}

# Function to clean up Docker resources
cleanup() {
    print_status "Cleaning up Docker resources..."
    cd "$PROJECT_ROOT"
    docker-compose down --volumes --remove-orphans
    docker image rm context7-mcp:latest 2>/dev/null || true
    print_success "Cleanup completed!"
}

# Function to show help
show_help() {
    echo "Context7 MCP Server Docker Helper Script"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  build     Build the Docker image"
    echo "  start     Start the server using docker-compose"
    echo "  stop      Stop the server"
    echo "  restart   Restart the server"
    echo "  logs      View server logs"
    echo "  status    Check server status"
    echo "  cleanup   Clean up Docker resources"
    echo "  help      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 build      # Build the Docker image"
    echo "  $0 start      # Start the server"
    echo "  $0 logs       # View logs"
}

# Main script logic
case "${1:-help}" in
    build)
        build
        ;;
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
