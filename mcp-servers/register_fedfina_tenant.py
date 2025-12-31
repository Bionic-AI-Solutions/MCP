#!/usr/bin/env python3
"""
Register Fedfina tenant directly via the MCP server running in Docker.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_servers.postgres.tenant_manager import PostgresTenantManager, PostgresTenantConfig


async def register_fedfina():
    """Register the Fedfina tenant."""
    print("Registering Fedfina tenant...")
    
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
        print("✅ Tenant 'fedfina' registered successfully!")
        
        # Test connection
        print("\nTesting connection...")
        async with manager.get_connection("fedfina") as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version();")
                version = await cur.fetchone()
                print(f"✅ Connection successful!")
                print(f"   PostgreSQL version: {version[0][:50]}...")
                
                # List a few tables to verify
                await cur.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                    LIMIT 5
                """)
                tables = await cur.fetchall()
                if tables:
                    print(f"\n✅ Found {len(tables)} table(s):")
                    for table in tables:
                        print(f"   - {table[0]}")
                else:
                    print("\nℹ️  No tables found in public schema")
        
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

