#!/bin/bash
# Setup script to install dependencies for Cursor MCP servers

set -e

echo "Setting up MCP servers for Cursor..."

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: Please run this script from /workspace/mcp-servers directory"
    exit 1
fi

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if ! python3 -m venv .venv; then
        echo "✗ Failed to create virtual environment"
        echo ""
        echo "The python3-venv package might not be installed."
        echo "Please install it with:"
        echo "  sudo apt install python3.12-venv"
        echo ""
        echo "Or use pipx to install fastmcp globally:"
        echo "  pipx install fastmcp"
        echo "  pipx inject fastmcp psycopg[binary,pool] minio pydantic python-dotenv"
        echo ""
        echo "Then use the system config: mcp_client_config_cursor_local_system.json"
        exit 1
    fi
    echo "✓ Virtual environment created"
fi

# Verify venv was created
if [ ! -f ".venv/bin/activate" ]; then
    echo "✗ Virtual environment activation script not found"
    echo "Trying to recreate..."
    rm -rf .venv
    if ! python3 -m venv .venv; then
        echo "✗ Failed to recreate virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install fastmcp psycopg[binary,pool] minio pydantic python-dotenv

# Verify installation
echo "Verifying installation..."
python -c "import fastmcp; print('✓ fastmcp installed')" || {
    echo "✗ fastmcp installation failed"
    exit 1
}

python -c "import psycopg; print('✓ psycopg installed')" || {
    echo "✗ psycopg installation failed"
    exit 1
}

python -c "import minio; print('✓ minio installed')" || {
    echo "✗ minio installation failed"
    exit 1
}

# Get the Python path from venv
VENV_PYTHON="$(pwd)/.venv/bin/python"

echo ""
echo "✓ All dependencies installed successfully!"
echo ""
echo "Virtual environment created at: $(pwd)/.venv"
echo "Python path: $VENV_PYTHON"
echo ""
echo "Next steps:"
echo "1. The config file has been updated to use the virtual environment Python"
echo "2. Copy mcp_client_config_cursor_local.json to ~/.cursor/mcp.json"
echo "3. Restart Cursor"
echo "4. The MCP servers should now be available"
echo ""
echo "To test manually:"
echo "  source .venv/bin/activate"
echo "  fastmcp run src/mcp_servers/calculator/server.py"
echo ""
echo "Or using the venv Python directly:"
echo "  $VENV_PYTHON -m fastmcp run src/mcp_servers/calculator/server.py"

