"""
SERVER_NAME MCP Server (Multi-tenant)

A FastMCP server providing [DESCRIPTION] with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

try:
    from mcp_servers.SERVER_NAME.tenant_manager import SERVER_NAMETenantManager
except ImportError:
    from .tenant_manager import SERVER_NAMETenantManager

# Initialize tenant manager
# Note: SERVER_NAMETenantManager will be replaced with proper camelCase during server creation
tenant_manager = SERVER_NAMETenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all connections and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("SERVER_NAME Server", lifespan=lifespan)


# ============================================================================
# Request/Response Models
# ============================================================================

class ExampleRequest(BaseModel):
    """Example request model - customize for your needs."""

    tenant_id: str = Field(..., description="Tenant identifier")
    # Add your custom fields here
    # field_name: str = Field(..., description="Field description")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def example_tool(
    tenant_id: str,
    # Add your parameters here
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Example tool - customize for your needs.
    
    Args:
        tenant_id: Tenant identifier
        # Add parameter descriptions here
        
    Returns:
        Dictionary with operation results
    """
    if ctx:
        await ctx.info(f"Executing example_tool for tenant: {tenant_id}")

    # Get tenant-specific client/connection
    client = await tenant_manager.get_client(tenant_id)
    
    # Implement your tool logic here
    # Example:
    # result = await client.some_operation()
    
    return {
        "success": True,
        "message": "Operation completed successfully",
        # Add your result data here
    }


@mcp.tool
async def register_tenant(
    tenant_id: str,
    # Add your tenant configuration parameters here
    # Example for API-based service:
    # api_key: str,
    # api_url: str,
    # Example for database service:
    # host: str,
    # database: str,
    # user: str,
    # password: str,
    # port: int = 5432,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration."""
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        from mcp_servers.SERVER_NAME.tenant_manager import SERVER_NAMETenantConfig
    except ImportError:
        from .tenant_manager import SERVER_NAMETenantConfig
    # Note: SERVER_NAMETenantConfig will be replaced with proper camelCase during server creation

    config = SERVER_NAMETenantConfig(
        tenant_id=tenant_id,
        # Add your configuration fields here
        # api_key=api_key,
        # api_url=api_url,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("SERVER_NAME://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    # Implement resource logic here
    result = {
        "tenant_id": tenant_id,
        "status": "active",
        # Add your resource data here
    }
    return json.dumps(result, indent=2)


@mcp.resource("SERVER_NAME://info")
def server_info() -> str:
    """Get information about the SERVER_NAME MCP server."""
    return "SERVER_NAME MCP Server - Multi-tenant [DESCRIPTION] operations"


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the SERVER_NAME server."""
    mcp.run()


if __name__ == "__main__":
    main()

