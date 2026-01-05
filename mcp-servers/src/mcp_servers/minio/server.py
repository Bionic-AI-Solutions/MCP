"""
MinIO MCP Server (Multi-tenant)

A FastMCP server providing MinIO object storage operations with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from io import BytesIO
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from minio.error import S3Error

try:
    from mcp_servers.minio.tenant_manager import MinioTenantManager
except ImportError:
    from .tenant_manager import MinioTenantManager

# Initialize tenant manager
tenant_manager = MinioTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("MinIO Server", lifespan=lifespan)


# ============================================================================
# Request/Response Models
# ============================================================================

class BucketOperationRequest(BaseModel):
    """Request model for bucket operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    bucket_name: str = Field(..., description="Bucket name")


class ObjectOperationRequest(BaseModel):
    """Request model for object operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    bucket_name: str = Field(..., description="Bucket name")
    object_name: str = Field(..., description="Object name/path")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def minio_list_buckets(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all buckets for a tenant."""
    if ctx:
        await ctx.info(f"Listing buckets for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        buckets = client.list_buckets()
        return {
            "success": True,
            "buckets": [
                {
                    "name": bucket.name,
                    "creation_date": bucket.creation_date.isoformat() if bucket.creation_date else None,
                }
                for bucket in buckets
            ],
        }
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_create_bucket(
    tenant_id: str,
    bucket_name: str,
    region: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, str]:
    """Create a new bucket."""
    if ctx:
        await ctx.info(f"Creating bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        client.make_bucket(bucket_name, location=region)
        return {"success": True, "message": f"Bucket '{bucket_name}' created successfully"}
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_delete_bucket(
    tenant_id: str,
    bucket_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, str]:
    """Delete a bucket (must be empty)."""
    if ctx:
        await ctx.info(f"Deleting bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        client.remove_bucket(bucket_name)
        return {"success": True, "message": f"Bucket '{bucket_name}' deleted successfully"}
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_bucket_exists(
    tenant_id: str,
    bucket_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Check if a bucket exists."""
    if ctx:
        await ctx.info(f"Checking if bucket '{bucket_name}' exists for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        exists = client.bucket_exists(bucket_name)
        return {"success": True, "exists": exists}
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_list_objects(
    tenant_id: str,
    bucket_name: str,
    prefix: Optional[str] = None,
    recursive: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List objects in a bucket."""
    if ctx:
        await ctx.info(f"Listing objects in bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        objects = client.list_objects(bucket_name, prefix=prefix, recursive=recursive)
        return {
            "success": True,
            "objects": [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "etag": obj.etag,
                }
                for obj in objects
            ],
        }
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_upload_object(
    tenant_id: str,
    bucket_name: str,
    object_name: str,
    data: str,
    content_type: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, str]:
    """Upload an object to a bucket."""
    if ctx:
        await ctx.info(f"Uploading object '{object_name}' to bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        data_bytes = data.encode("utf-8")
        data_stream = BytesIO(data_bytes)
        length = len(data_bytes)
        
        client.put_object(
            bucket_name,
            object_name,
            data_stream,
            length,
            content_type=content_type or "application/octet-stream",
        )
        return {"success": True, "message": f"Object '{object_name}' uploaded successfully"}
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_download_object(
    tenant_id: str,
    bucket_name: str,
    object_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Download an object from a bucket."""
    if ctx:
        await ctx.info(f"Downloading object '{object_name}' from bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        response = client.get_object(bucket_name, object_name)
        data = response.read()
        response.close()
        response.release_conn()
        
        return {
            "success": True,
            "data": data.decode("utf-8"),
            "size": len(data),
        }
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_delete_object(
    tenant_id: str,
    bucket_name: str,
    object_name: str,
    ctx: Optional[Context] = None,
) -> Dict[str, str]:
    """Delete an object from a bucket."""
    if ctx:
        await ctx.info(f"Deleting object '{object_name}' from bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client = await tenant_manager.get_client(tenant_id)
        client.remove_object(bucket_name, object_name)
        return {"success": True, "message": f"Object '{object_name}' deleted successfully"}
    except S3Error as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def minio_register_tenant(
    tenant_id: str,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool = True,
    region: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new tenant configuration."""
    if ctx:
        await ctx.info(f"Registering tenant: {tenant_id}")

    try:
        from mcp_servers.minio.tenant_manager import MinioTenantConfig
    except ImportError:
        from .tenant_manager import MinioTenantConfig

    config = MinioTenantConfig(
        tenant_id=tenant_id,
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        region=region,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("minio://{tenant_id}/buckets")
async def get_buckets_resource(tenant_id: str) -> str:
    """Get list of buckets for a tenant as a resource."""
    result = await list_buckets(tenant_id)
    return json.dumps(result, indent=2)


@mcp.resource("minio://info")
def minio_info() -> str:
    """Get information about the MinIO MCP server."""
    return "MinIO MCP Server - Multi-tenant object storage operations"


def main():
    """Run the MinIO server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8002"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    # This allows each request to work independently without session management
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    # JSON format returns plain JSON instead of SSE format
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()

