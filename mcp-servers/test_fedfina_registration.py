#!/usr/bin/env python3
"""
Test script to register Fedfina tenant directly via the MCP server.
This verifies the import fix works correctly.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_servers.postgres.tenant_manager import PostgresTenantManager, PostgresTenantConfig


async def test_registration():
    """Test registering the Fedfina tenant."""
    print("Testing Fedfina tenant registration...")
    
    manager = PostgresTenantManager()
    
    config = PostgresTenantConfig(
        tenant_id="fedfina",
        host="switchback.proxy.rlwy.net",
        port=26569,
        database="railway",
        user="postgres",
        password="rlfFWEHEvKGPGmndzdLIyowgyYUCsjVe",
        min_pool_size=2,
        max_pool_size=10,
        ssl=True,
    )
    
    try:
        await manager.register_tenant(config)
        print("✅ Tenant registered successfully!")
        
        # Test connection
        print("Testing connection...")
        async with manager.get_connection("fedfina") as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version();")
                version = await cur.fetchone()
                print(f"✅ Connection successful! PostgreSQL version: {version[0]}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await manager.close_all()


if __name__ == "__main__":
    success = asyncio.run(test_registration())
    sys.exit(0 if success else 1)


