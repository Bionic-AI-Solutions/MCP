#!/bin/bash
# Script to commit and push mcp-servers and mcp-nginx to GitHub

set -e

cd /workspace/MCP

# Check if git is initialized
if [ ! -d .git ]; then
    echo "Initializing git repository..."
    git init
fi

# Set remote
git remote remove origin 2>/dev/null || true
git remote add origin https://github.com/Bionic-AI-Solutions/MCP.git

# Configure git user
git config user.name "Bionic AI Solutions"
git config user.email "info@bionicaisolutions.com"

# Add the new folders (force add to override .gitignore if needed)
echo "Adding mcp-servers and mcp-nginx..."
git add mcp-servers/ mcp-nginx/

# Explicitly add src folders and fastmcp if they exist
echo "Adding source folders..."
git add -f mcp-servers/src/ 2>/dev/null || true
git add -f fastmcp/ 2>/dev/null || true
git add -f fastmcp/src/ 2>/dev/null || true

# Check status
echo "Git status:"
git status --short

# Commit
echo "Committing changes..."
git commit -m "Add MCP servers (Calculator, Postgres, MinIO) with Docker support and nginx configuration

- Added FastMCP-based MCP servers for Calculator, Postgres, and MinIO
- Multi-tenant support for Postgres and MinIO
- Docker Compose setup with Redis for tenant configuration storage
- Nginx reverse proxy configuration for external access
- Cursor IDE configuration files for local and remote access
- Comprehensive documentation and setup guides"

# Set default branch to main
git branch -M main 2>/dev/null || true

# Push to remote
echo "Pushing to GitHub..."
git push -u origin main

echo "✅ Successfully pushed to https://github.com/Bionic-AI-Solutions/MCP.git"

