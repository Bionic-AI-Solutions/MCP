"""
MinIO MCP Client

Example client for interacting with the MinIO MCP server.
"""

import asyncio
from fastmcp import Client


async def main():
    """Example usage of the MinIO MCP client."""
    # Connect to the minio server
    async with Client("src/mcp_servers/minio/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}")
        
        # Register a tenant (if not already configured via env vars)
        tenant_id = "1"
        print(f"\n=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "minio_register_tenant",
            {
                "tenant_id": tenant_id,
                "endpoint": "localhost:9000",
                "access_key": "minioadmin",
                "secret_key": "minioadmin123",
                "secure": False,
            },
        )
        print(f"Result: {result.content[0].text}")
        
        # List buckets
        print(f"\n=== Listing buckets for tenant: {tenant_id} ===")
        result = await client.call_tool("minio_list_buckets", {"tenant_id": tenant_id})
        print(f"Buckets: {result.content[0].text}")
        
        # Create a bucket
        bucket_name = "test-bucket"
        print(f"\n=== Creating bucket: {bucket_name} ===")
        result = await client.call_tool(
            "minio_create_bucket",
            {"tenant_id": tenant_id, "bucket_name": bucket_name},
        )
        print(f"Result: {result.content[0].text}")
        
        # Upload an object
        print(f"\n=== Uploading object ===")
        result = await client.call_tool(
            "minio_upload_object",
            {
                "tenant_id": tenant_id,
                "bucket_name": bucket_name,
                "object_name": "test.txt",
                "data": "Hello, MinIO!",
            },
        )
        print(f"Result: {result.content[0].text}")
        
        # List objects
        print(f"\n=== Listing objects ===")
        result = await client.call_tool(
            "minio_list_objects",
            {"tenant_id": tenant_id, "bucket_name": bucket_name},
        )
        print(f"Objects: {result.content[0].text}")
        
        # Download the object
        print(f"\n=== Downloading object ===")
        result = await client.call_tool(
            "minio_download_object",
            {
                "tenant_id": tenant_id,
                "bucket_name": bucket_name,
                "object_name": "test.txt",
            },
        )
        print(f"Result: {result.content[0].text}")


if __name__ == "__main__":
    asyncio.run(main())

