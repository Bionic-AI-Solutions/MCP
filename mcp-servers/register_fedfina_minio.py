#!/usr/bin/env python3
"""
Register Fedfina tenant directly via the MinIO MCP server running in Docker.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_servers.minio.tenant_manager import MinioTenantManager, MinioTenantConfig


async def register_fedfina():
    """Register the Fedfina tenant."""
    print("Registering Fedfina tenant in MinIO...")
    
    manager = MinioTenantManager()
    
    config = MinioTenantConfig(
        tenant_id="fedfina",
        endpoint="bucket-staging-b563.up.railway.app:443",
        access_key="IcyKs7K13OBpvdQKAVHNIuLn7xUwSxMt",
        secret_key="Axw7sAFHwB47zzhtu5oemKfzhefg1a2iR7LXDEw3kpfgJQZC",
        secure=True,
    )
    
    try:
        await manager.register_tenant(config)
        print("✅ Tenant 'fedfina' registered successfully!")
        
        # Test connection by listing buckets
        print("\nTesting connection...")
        client = await manager.get_client("fedfina")
        buckets = client.list_buckets()
        print(f"✅ Connection successful!")
        print(f"   Found {len(buckets)} bucket(s):")
        for bucket in buckets:
            print(f"   - {bucket.name} (created: {bucket.creation_date})")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await manager.close_all()


if __name__ == "__main__":
    success = asyncio.run(register_fedfina())
    sys.exit(0 if success else 1)

