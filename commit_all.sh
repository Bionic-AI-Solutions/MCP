#!/bin/bash
# Script to commit and push ALL files including fastmcp and src folders

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

# Force add everything (overrides .gitignore)
echo "Adding all folders (force mode to include everything)..."
git add -f mcp-servers/
git add -f mcp-nginx/
git add -f fastmcp/
git add -f context7-mcp/
git add -f mcp-ai/

# Add root level files
git add -f commit_and_push.sh commit_all.sh COMMIT_INSTRUCTIONS.md PUSH_STATUS.md FIX_GIT_ADD.md README.md .gitignore 2>/dev/null || true

# Check what's staged
echo ""
echo "=== Files staged for commit ==="
git status --short | head -50

echo ""
echo "=== Checking for ignored files ==="
git status --ignored | grep -E "fastmcp|src" | head -20 || echo "No ignored files found for fastmcp/src"

# Commit
echo ""
echo "Committing changes..."
git commit -m "Add MCP servers (Calculator, Postgres, MinIO) with Docker support and nginx configuration

- Added FastMCP-based MCP servers for Calculator, Postgres, and MinIO
- Multi-tenant support for Postgres and MinIO
- Docker Compose setup with Redis for tenant configuration storage
- Nginx reverse proxy configuration for external access
- Cursor IDE configuration files for local and remote access
- Comprehensive documentation and setup guides
- Included fastmcp framework source code
- Included all src/ source folders"

# Set default branch to main
git branch -M main 2>/dev/null || true

# Push to remote
echo ""
echo "Pushing to GitHub..."
git push -u origin main

echo ""
echo "✅ Successfully pushed to https://github.com/Bionic-AI-Solutions/MCP.git"
echo ""
echo "Verify at: https://github.com/Bionic-AI-Solutions/MCP"

