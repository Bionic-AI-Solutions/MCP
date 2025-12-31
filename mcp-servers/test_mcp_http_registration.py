#!/usr/bin/env python3
"""
Test MCP HTTP registration using proper session management.
"""

import asyncio
import httpx
import json


async def test_mcp_registration():
    """Test registering Fedfina tenant via MCP HTTP endpoint."""
    base_url = "http://localhost:8001/mcp"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Initialize session
        print("Step 1: Initializing MCP session...")
        init_response = await client.post(
            base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                },
                "id": 1
            }
        )
        
        if init_response.status_code != 200:
            print(f"❌ Initialize failed: {init_response.status_code}")
            print(init_response.text)
            return False
        
        # Parse session ID from response
        session_id = None
        for line in init_response.text.split('\n'):
            if line.startswith('data:'):
                data = json.loads(line[5:].strip())
                if 'result' in data:
                    # Extract session ID from headers or response
                    session_id = init_response.headers.get('X-Session-Id') or data.get('result', {}).get('sessionId')
                    break
        
        print(f"✅ Session initialized")
        if session_id:
            print(f"   Session ID: {session_id}")
        
        # Step 2: Register tenant
        print("\nStep 2: Registering Fedfina tenant...")
        register_response = await client.post(
            base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Session-Id": session_id if session_id else ""
            },
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "register_tenant",
                    "arguments": {
                        "tenant_id": "fedfina",
                        "host": "switchback.proxy.rlwy.net",
                        "database": "railway",
                        "user": "postgres",
                        "password": "rlfFWEHEvKGPGmndzdLIyowgyYUCsjVe",
                        "port": 26569,
                        "ssl": True
                    }
                },
                "id": 2
            }
        )
        
        print(f"Response status: {register_response.status_code}")
        print(f"Response body: {register_response.text[:500]}")
        
        if register_response.status_code == 200:
            print("✅ Registration successful!")
            return True
        else:
            print("❌ Registration failed")
            return False


if __name__ == "__main__":
    success = asyncio.run(test_mcp_registration())
    exit(0 if success else 1)


