#!/usr/bin/env python3
"""Verify Fedfina tenant is registered and test a query."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_servers.postgres.tenant_manager import PostgresTenantManager


async def verify():
    """Verify Fedfina tenant and test query."""
    manager = PostgresTenantManager()
    
    try:
        # Initialize to load from Redis
        await manager._init_redis()
        redis_configs = await manager._load_all_from_redis()
        print(f"✅ Found {len(redis_configs)} tenant(s) in Redis:")
        for tenant_id in redis_configs.keys():
            print(f"   - {tenant_id}")
        
        # List tables
        print("\nListing tables for Fedfina tenant...")
        async with manager.get_connection("fedfina") as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                    LIMIT 10
                """)
                tables = await cur.fetchall()
                print(f"✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"   - {table[0]}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.close_all()


if __name__ == "__main__":
    asyncio.run(verify())

