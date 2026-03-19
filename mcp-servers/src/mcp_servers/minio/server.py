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
    """List all buckets available in a tenant's MinIO instance.

    Retrieves every bucket the tenant's credentials have access to, along with
    each bucket's creation timestamp. Use this to discover available storage
    locations before uploading or downloading objects, or to audit what buckets
    currently exist.

    This call maps to the S3-compatible ListBuckets API and returns all buckets
    regardless of region.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance to
            query. The tenant must already be registered via
            minio_register_tenant or pre-configured at server startup.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - buckets (list[dict]): List of bucket objects, each containing:
            - name (str): The bucket name.
            - creation_date (str | None): ISO-8601 formatted creation
              timestamp, or None if unavailable.
        - error (str): Error message if the operation failed.

    Notes:
        - Bucket listing is scoped to the credentials configured for the given
          tenant. If the credentials lack ListBuckets permission the call will
          fail with an access-denied error.
    """
    if ctx:
        await ctx.info(f"Listing buckets for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """Create a new storage bucket in a tenant's MinIO instance.

    Creates an empty bucket with the specified name. Buckets serve as the
    top-level containers for objects in S3-compatible storage. Use this before
    uploading objects when the target bucket does not yet exist.

    Common use cases:
    - Setting up storage for a new project or application component.
    - Creating isolated namespaces for different data categories (e.g.,
      "raw-data", "processed-data", "backups").
    - Provisioning per-user or per-team storage areas.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance will
            host the new bucket.
        bucket_name: Name for the new bucket. Must be globally unique within the
            MinIO instance, between 3 and 63 characters long, and consist only
            of lowercase letters, numbers, hyphens, and periods. Must start and
            end with a letter or number.
        region: Optional S3 region/location constraint for the bucket (e.g.,
            "us-east-1"). Defaults to the server's configured default region if
            not specified.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the bucket was created.
        - message (str): Confirmation message on success.
        - error (str): Error message if the operation failed (e.g., bucket
          already exists, invalid name, or insufficient permissions).

    Notes:
        - If a bucket with the same name already exists, the S3 API will return
          a BucketAlreadyOwnedByYou or BucketAlreadyExists error.
        - Bucket names follow S3 naming rules and are case-sensitive (lowercase
          only).
    """
    if ctx:
        await ctx.info(f"Creating bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """Delete an existing bucket from a tenant's MinIO instance.

    Permanently removes the specified bucket. The bucket must be completely empty
    (no objects, no incomplete multipart uploads) before it can be deleted. Use
    minio_list_objects to verify the bucket is empty, and minio_delete_object to
    remove any remaining objects first.

    Common use cases:
    - Cleaning up buckets that are no longer needed.
    - Tearing down storage during project decommissioning.
    - Removing accidentally created buckets.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance
            contains the bucket to delete.
        bucket_name: Name of the bucket to delete. The bucket must already exist
            and must be empty.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the bucket was deleted.
        - message (str): Confirmation message on success.
        - error (str): Error message if the operation failed (e.g., bucket not
          found, bucket not empty, or insufficient permissions).

    Notes:
        - This operation is irreversible. Once deleted, the bucket name becomes
          available for reuse.
        - Attempting to delete a non-empty bucket will result in a
          BucketNotEmpty error from the S3 API.
    """
    if ctx:
        await ctx.info(f"Deleting bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """Check whether a specific bucket exists in a tenant's MinIO instance.

    Performs a lightweight HEAD request against the bucket to determine if it
    exists and is accessible with the tenant's credentials. Use this to verify
    a bucket is present before attempting uploads or downloads, or to implement
    idempotent bucket creation logic.

    Common use cases:
    - Pre-flight validation before uploading objects.
    - Conditional bucket creation (check first, create only if missing).
    - Health checks to confirm storage is reachable.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance to
            query.
        bucket_name: Name of the bucket to check for existence.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the check operation itself succeeded.
        - exists (bool): True if the bucket exists and is accessible, False
          otherwise. Only present when success is True.
        - error (str): Error message if the operation failed (e.g., network
          error or authentication failure).

    Notes:
        - A return of exists=False may also mean the tenant's credentials lack
          permission to access the bucket, not necessarily that the bucket does
          not exist at all.
    """
    if ctx:
        await ctx.info(f"Checking if bucket '{bucket_name}' exists for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """List objects stored in a bucket, optionally filtered by prefix.

    Enumerates objects within the specified bucket. Supports prefix-based
    filtering to navigate folder-like hierarchies and recursive or
    non-recursive listing modes. Use this to discover what data is available,
    browse directory structures, or find specific files before downloading.

    Common use cases:
    - Browsing the contents of a bucket or a specific "folder" within it.
    - Finding objects matching a naming pattern or path prefix.
    - Building file listings for user interfaces or downstream processing.
    - Checking if a specific object exists before downloading.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance to
            query.
        bucket_name: Name of the bucket to list objects from. The bucket must
            exist.
        prefix: Optional prefix to filter objects by (e.g., "data/2024/" to
            list only objects under that path). Defaults to None, which lists
            all objects in the bucket.
        recursive: If True (default), lists all objects under the prefix
            recursively, traversing all nested "directories". If False, lists
            only objects and common prefixes at the current level, similar to a
            non-recursive directory listing.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - objects (list[dict]): List of object metadata dicts, each containing:
            - name (str): Full object key/path within the bucket.
            - size (int): Object size in bytes.
            - last_modified (str | None): ISO-8601 formatted last modification
              timestamp, or None if unavailable.
            - etag (str): Entity tag (MD5 hash of the object content for
              non-multipart uploads).
        - error (str): Error message if the operation failed.

    Notes:
        - MinIO/S3 uses a flat namespace. "Folders" are simulated by using
          forward slashes (/) in object names. The prefix parameter lets you
          filter by these virtual folder paths.
        - For buckets with a very large number of objects, this call returns
          all matching objects. Consider using a specific prefix to narrow
          results.
    """
    if ctx:
        await ctx.info(f"Listing objects in bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """Upload a string-based object to a bucket in a tenant's MinIO instance.

    Stores the provided data as an object in the specified bucket. The data is
    encoded as UTF-8 bytes before upload. Use this to persist text content such
    as JSON, CSV, logs, configuration files, or any other string-representable
    data to object storage.

    Common use cases:
    - Saving JSON documents or API responses for later retrieval.
    - Storing CSV data, log files, or text reports.
    - Writing configuration files or metadata to object storage.
    - Creating marker or sentinel objects in a workflow.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance will
            store the object.
        bucket_name: Name of the target bucket. The bucket must already exist;
            use minio_create_bucket to create it first if needed.
        object_name: Key/path for the object within the bucket. Can include
            forward slashes to simulate a directory structure (e.g.,
            "reports/2024/summary.json"). If an object with this name already
            exists, it will be overwritten.
        data: The string content to upload. This will be UTF-8 encoded before
            storage. For binary data, encode it as base64 first and use an
            appropriate content_type.
        content_type: Optional MIME type for the object (e.g., "application/json",
            "text/csv", "text/plain"). Defaults to "application/octet-stream" if
            not specified. Setting the correct content type helps clients handle
            the object appropriately when downloading.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the upload succeeded.
        - message (str): Confirmation message on success.
        - error (str): Error message if the upload failed (e.g., bucket not
          found, access denied, or storage quota exceeded).

    Notes:
        - Uploading to an existing object_name silently overwrites the previous
          content. MinIO/S3 does not prompt for confirmation.
        - Object names are case-sensitive.
        - The maximum object size for this tool is constrained by the string
          data passed in memory. For very large files, consider a streaming
          upload approach.
    """
    if ctx:
        await ctx.info(f"Uploading object '{object_name}' to bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        data_bytes = data.encode("utf-8")
        data_stream = BytesIO(data_bytes)
        length = len(data_bytes)

        async with semaphore:
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
    """Download an object's content from a bucket in a tenant's MinIO instance.

    Retrieves the full content of the specified object and returns it as a
    UTF-8 decoded string. Use this to read text-based files (JSON, CSV, logs,
    config files, etc.) stored in MinIO/S3-compatible object storage.

    Common use cases:
    - Reading JSON documents or configuration files from storage.
    - Fetching CSV data for processing or analysis.
    - Retrieving log files or text reports.
    - Loading previously saved state or checkpoint data.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance
            contains the object.
        bucket_name: Name of the bucket containing the object.
        object_name: Full key/path of the object to download (e.g.,
            "reports/2024/summary.json"). Must match the exact object name
            used during upload, including case.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the download succeeded.
        - data (str): The object's content decoded as a UTF-8 string. Only
          present when success is True.
        - size (int): Size of the downloaded content in bytes. Only present
          when success is True.
        - error (str): Error message if the download failed (e.g., object not
          found, access denied, or network error).

    Notes:
        - The object content is decoded as UTF-8. Downloading binary objects
          (images, compressed files, etc.) will fail with a decode error.
          For binary content, consider a base64-encoding wrapper.
        - The entire object is read into memory. For very large objects this
          may consume significant memory.
        - The underlying HTTP connection is properly closed and released after
          reading.
    """
    if ctx:
        await ctx.info(f"Downloading object '{object_name}' from bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    """Delete a single object from a bucket in a tenant's MinIO instance.

    Permanently removes the specified object from the bucket. Use this to clean
    up obsolete files, remove sensitive data, or free storage space. This must
    be called for each object individually; to empty a bucket before deleting
    it, list all objects and delete them one by one.

    Common use cases:
    - Removing outdated or superseded data files.
    - Cleaning up temporary or intermediate processing artifacts.
    - Deleting sensitive data that should no longer be retained.
    - Emptying a bucket in preparation for bucket deletion.

    Args:
        tenant_id: Unique identifier for the tenant whose MinIO instance
            contains the object.
        bucket_name: Name of the bucket containing the object to delete.
        object_name: Full key/path of the object to delete (e.g.,
            "reports/2024/summary.json"). Must match the exact object name,
            including case.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message on success.
        - error (str): Error message if the deletion failed (e.g., access
          denied or network error).

    Notes:
        - This operation is irreversible unless the bucket has versioning
          enabled, in which case a delete marker is placed instead.
        - Deleting a non-existent object is treated as a successful operation
          by the S3 API (idempotent delete). No error is returned.
        - Object names are case-sensitive.
    """
    if ctx:
        await ctx.info(f"Deleting object '{object_name}' from bucket '{bucket_name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]
        semaphore = client_info["semaphore"]

        async with semaphore:
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
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new MinIO tenant configuration at runtime with concurrency control.

    Adds a new tenant to the server's tenant registry, creating a configured
    MinIO client that subsequent tool calls can use. Each tenant represents an
    independent MinIO (or S3-compatible) instance with its own credentials and
    endpoint. Use this to onboard new storage backends dynamically without
    restarting the server.

    The tenant configuration is persisted via the tenant manager (typically
    backed by Redis), so registered tenants survive server restarts.

    Common use cases:
    - Dynamically onboarding a new customer or team's MinIO instance.
    - Connecting to an additional S3-compatible storage backend at runtime.
    - Updating connection parameters for an existing tenant by re-registering
      with the same tenant_id.

    Args:
        tenant_id: Unique identifier for this tenant. Used in all subsequent
            tool calls to route operations to the correct MinIO instance. If a
            tenant with this ID already exists, its configuration will be
            replaced.
        endpoint: MinIO or S3-compatible server endpoint, including port if
            non-standard (e.g., "minio.example.com:9000",
            "s3.amazonaws.com"). Do not include the protocol scheme (http/https);
            use the secure parameter instead.
        access_key: Access key (username) for authenticating with the MinIO
            instance. Equivalent to AWS_ACCESS_KEY_ID.
        secret_key: Secret key (password) for authenticating with the MinIO
            instance. Equivalent to AWS_SECRET_ACCESS_KEY.
        secure: Whether to use HTTPS/TLS for the connection. Defaults to True.
            Set to False for local development instances or MinIO servers without
            TLS configured.
        region: Optional S3 region for the MinIO instance (e.g., "us-east-1").
            Required by some S3-compatible services; can be omitted for standard
            MinIO deployments.
        max_concurrent_requests: Maximum number of concurrent requests allowed
            for this tenant. Defaults to 100. Controls the semaphore used to
            throttle parallel operations and prevent overloading the MinIO
            instance.
        ctx: Optional MCP context for logging (injected automatically).

    Returns:
        Dict with:
        - success (bool): Whether the tenant was registered successfully.
        - message (str): Confirmation message on success.
        - error (str): Error message if registration failed (e.g., invalid
          endpoint or connection failure).

    Notes:
        - Registration does not validate connectivity to the MinIO endpoint.
          The first actual operation (e.g., minio_list_buckets) will reveal
          connection issues.
        - Credentials are stored in the tenant manager's backing store. Ensure
          the backing store (e.g., Redis) is secured appropriately.
        - Re-registering an existing tenant_id will overwrite the previous
          configuration.
    """
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
        max_concurrent_requests=max_concurrent_requests,
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
