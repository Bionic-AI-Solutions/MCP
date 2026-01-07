"""
MeiliSearch MCP Server (Multi-tenant)

A FastMCP server providing MeiliSearch search engine operations with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.meilisearch.tenant_manager import MeiliSearchTenantManager
    from mcp_servers.meilisearch.client import MeiliSearchClientWrapper
except ImportError:
    from .tenant_manager import MeiliSearchTenantManager
    from .client import MeiliSearchClientWrapper

# Initialize tenant manager
tenant_manager = MeiliSearchTenantManager()


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
mcp = FastMCP("MeiliSearch Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "meilisearch-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Request/Response Models
# ============================================================================

class SearchRequest(BaseModel):
    """Request model for search operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    index_uid: str = Field(..., description="Index UID to search")
    query: str = Field(..., description="Search query string")
    limit: int = Field(default=20, description="Maximum number of results")
    offset: int = Field(default=0, description="Offset for pagination")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def ms_register_tenant(
    tenant_id: str,
    url: str,
    api_key: Optional[str] = None,
    timeout: int = 5,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new MeiliSearch tenant configuration.
    
    Args:
        tenant_id: Unique identifier for this tenant
        url: MeiliSearch server URL (e.g., 'http://meilisearch.meilisearch:7700')
        api_key: Optional API key (master key or search key)
        timeout: Request timeout in seconds (default: 5)
    """
    if ctx:
        await ctx.info(f"Registering MeiliSearch tenant: {tenant_id}")

    try:
        from mcp_servers.meilisearch.tenant_manager import MeiliSearchTenantConfig
    except ImportError:
        from .tenant_manager import MeiliSearchTenantConfig

    config = MeiliSearchTenantConfig(
        tenant_id=tenant_id,
        url=url,
        api_key=api_key,
        timeout=timeout,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


@mcp.tool
async def ms_list_indexes(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all indexes for a tenant."""
    if ctx:
        await ctx.info(f"Listing indexes for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    indexes = wrapper.list_indexes()

    return {
        "success": True,
        "tenant_id": tenant_id,
        "count": len(indexes),
        "indexes": indexes,
    }


@mcp.tool
async def ms_get_index(
    tenant_id: str,
    index_uid: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get information about a specific index."""
    if ctx:
        await ctx.info(f"Getting index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    index_info = wrapper.get_index(index_uid)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "index": index_info,
    }


@mcp.tool
async def ms_create_index(
    tenant_id: str,
    index_uid: str,
    primary_key: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new index."""
    if ctx:
        await ctx.info(f"Creating index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.create_index(index_uid, primary_key)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "index": result,
    }


@mcp.tool
async def ms_delete_index(
    tenant_id: str,
    index_uid: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete an index."""
    if ctx:
        await ctx.info(f"Deleting index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    wrapper.delete_index(index_uid)

    return {
        "success": True,
        "message": f"Index '{index_uid}' deleted successfully",
    }


@mcp.tool
async def ms_add_documents(
    tenant_id: str,
    index_uid: str,
    documents: str,  # JSON string of documents array
    primary_key: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add documents to an index.
    
    Args:
        tenant_id: Tenant identifier
        index_uid: Index UID
        documents: JSON string array of documents to add
        primary_key: Optional primary key field name
    """
    if ctx:
        await ctx.info(f"Adding documents to index '{index_uid}' for tenant: {tenant_id}")

    try:
        docs = json.loads(documents)
        if not isinstance(docs, list):
            return {"success": False, "error": "Documents must be a JSON array"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.add_documents(index_uid, docs, primary_key)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "task": result,
    }


@mcp.tool
async def ms_search(
    tenant_id: str,
    index_uid: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
    filter: Optional[str] = None,
    sort: Optional[str] = None,  # JSON string array
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search documents in an index.
    
    Args:
        tenant_id: Tenant identifier
        index_uid: Index UID to search
        query: Search query string
        limit: Maximum number of results (default: 20)
        offset: Offset for pagination (default: 0)
        filter: Optional filter expression
        sort: Optional JSON string array of sort fields
    """
    if ctx:
        await ctx.info(f"Searching index '{index_uid}' with query '{query}' for tenant: {tenant_id}")

    sort_list = None
    if sort:
        try:
            sort_list = json.loads(sort)
            if not isinstance(sort_list, list):
                sort_list = None
        except json.JSONDecodeError:
            sort_list = None

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.search(
        index_uid,
        query,
        limit=limit,
        offset=offset,
        filter=filter,
        sort=sort_list,
    )

    return {
        "success": True,
        "tenant_id": tenant_id,
        "query": query,
        "hits": result.get("hits", []),
        "estimated_total_hits": result.get("estimatedTotalHits", 0),
        "limit": limit,
        "offset": offset,
        "processing_time_ms": result.get("processingTimeMs", 0),
    }


@mcp.tool
async def ms_get_document(
    tenant_id: str,
    index_uid: str,
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get a single document by ID."""
    if ctx:
        await ctx.info(f"Getting document '{document_id}' from index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    document = wrapper.get_document(index_uid, document_id)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "document": document,
    }


@mcp.tool
async def ms_delete_documents(
    tenant_id: str,
    index_uid: str,
    document_ids: str,  # JSON string array
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete documents from an index."""
    if ctx:
        await ctx.info(f"Deleting documents from index '{index_uid}' for tenant: {tenant_id}")

    try:
        ids = json.loads(document_ids)
        if not isinstance(ids, list):
            return {"success": False, "error": "Document IDs must be a JSON array"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.delete_documents(index_uid, ids)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "task": result,
    }


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("meilisearch://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    try:
        client = await tenant_manager.get_client(tenant_id)
        wrapper = MeiliSearchClientWrapper(client)
        indexes = wrapper.list_indexes()
        
        result = {
            "tenant_id": tenant_id,
            "status": "active",
            "index_count": len(indexes),
            "indexes": indexes,
        }
    except Exception as e:
        result = {
            "tenant_id": tenant_id,
            "status": "error",
            "error": str(e),
        }
    return json.dumps(result, indent=2)


@mcp.resource("meilisearch://info")
def server_info() -> str:
    """Get information about the MeiliSearch MCP server."""
    return "MeiliSearch MCP Server - Multi-tenant search engine operations"


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the MeiliSearch server."""
    mcp.run()


if __name__ == "__main__":
    main()

