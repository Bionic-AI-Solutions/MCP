"""
Example: Using the MinIO MCP Server

This example demonstrates how to use the MinIO MCP client with multi-tenant support.

Before running, set environment variables:
    export MINIO_TENANT_1_ENDPOINT=localhost:9000
    export MINIO_TENANT_1_ACCESS_KEY=minioadmin
    export MINIO_TENANT_1_SECRET_KEY=minioadmin123
    export MINIO_TENANT_1_SECURE=false
"""

import asyncio
from fastmcp import Client


async def main():
    """Run minio examples."""
    print("=== MinIO MCP Server Example ===\n")
    
    # Connect to the minio server
    async with Client("src/mcp_servers/minio/server.py") as client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {[tool.name for tool in tools]}\n")
        
        tenant_id = "1"
        bucket_name = "example-bucket"
        
        # Option 1: Register tenant programmatically (if not configured via env)
        print(f"=== Registering tenant: {tenant_id} ===")
        result = await client.call_tool(
            "register_tenant",
            {
                "tenant_id": tenant_id,
                "endpoint": "localhost:9000",
                "access_key": "minioadmin",
                "secret_key": "minioadmin123",
                "secure": False,
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # List buckets
        print(f"=== Listing buckets for tenant: {tenant_id} ===")
        result = await client.call_tool("list_buckets", {"tenant_id": tenant_id})
        print(f"Buckets: {result.content[0].text}\n")
        
        # Create a bucket
        print(f"=== Creating bucket: {bucket_name} ===")
        result = await client.call_tool(
            "create_bucket",
            {"tenant_id": tenant_id, "bucket_name": bucket_name},
        )
        print(f"Result: {result.content[0].text}\n")
        
        # Upload an object
        object_name = "example.txt"
        object_data = "Hello from MinIO MCP Server!"
        print(f"=== Uploading object: {object_name} ===")
        result = await client.call_tool(
            "upload_object",
            {
                "tenant_id": tenant_id,
                "bucket_name": bucket_name,
                "object_name": object_name,
                "data": object_data,
                "content_type": "text/plain",
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # List objects
        print(f"=== Listing objects in bucket: {bucket_name} ===")
        result = await client.call_tool(
            "list_objects",
            {"tenant_id": tenant_id, "bucket_name": bucket_name},
        )
        print(f"Objects: {result.content[0].text}\n")
        
        # Download the object
        print(f"=== Downloading object: {object_name} ===")
        result = await client.call_tool(
            "download_object",
            {
                "tenant_id": tenant_id,
                "bucket_name": bucket_name,
                "object_name": object_name,
            },
        )
        print(f"Result: {result.content[0].text}\n")
        
        # Delete the object
        print(f"=== Deleting object: {object_name} ===")
        result = await client.call_tool(
            "delete_object",
            {
                "tenant_id": tenant_id,
                "bucket_name": bucket_name,
                "object_name": object_name,
            },
        )
        print(f"Result: {result.content[0].text}\n")


if __name__ == "__main__":
    asyncio.run(main())

