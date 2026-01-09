#!/usr/bin/env python3
"""
Test GenImage MCP Server for Remote Clients

This script tests the MCP server via HTTP endpoint to ensure it works
for remote clients like Cursor.
"""

import json
import requests
import sys
import time
from typing import Optional

BASE_URL = "https://mcp.baisoln.com/genimage/mcp"


def extract_session_id(response: requests.Response) -> Optional[str]:
    """Extract session ID from response headers or cookies."""
    # Check headers
    session_id = response.headers.get("X-Session-Id") or response.headers.get("Mcp-Session-Id")
    if session_id:
        return session_id
    
    # Check cookies
    for cookie in response.cookies:
        if 'session' in cookie.name.lower():
            return cookie.value
    
    # Try to extract from SSE response
    if 'text/event-stream' in response.headers.get('content-type', ''):
        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[5:].strip())
                    if 'result' in data:
                        # Session ID might be in result metadata
                        result = data['result']
                        if isinstance(result, dict):
                            session_id = result.get('sessionId') or result.get('session_id')
                            if session_id:
                                return session_id
                except:
                    pass
    
    return None


def test_remote_mcp():
    """Test MCP server via HTTP endpoint."""
    session = requests.Session()
    
    print("=" * 70)
    print("Testing GenImage MCP Server for Remote Clients")
    print("=" * 70)
    print(f"Endpoint: {BASE_URL}\n")
    
    # Step 1: Initialize
    print("Step 1: Initializing MCP session...")
    init_payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-remote-client",
                "version": "1.0.0"
            }
        },
        "id": 1
    }
    
    try:
        init_response = session.post(
            BASE_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json=init_payload,
            timeout=30
        )
        
        print(f"   Status: {init_response.status_code}")
        
        if init_response.status_code != 200:
            print(f"   ❌ Initialize failed: {init_response.text[:200]}")
            return False
        
        # Parse initialize response first to get session ID from result
        init_data = None
        session_id = None
        for line in init_response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    init_data = json.loads(line[5:].strip())
                    if 'result' in init_data:
                        # Session ID might be in result metadata
                        result = init_data['result']
                        if isinstance(result, dict):
                            session_id = result.get('sessionId') or result.get('session_id')
                    break
                except:
                    pass
        
        # Also try to extract from headers/cookies
        if not session_id:
            session_id = extract_session_id(init_response)
        
        if session_id:
            print(f"   ✅ Session ID: {session_id[:30]}...")
            # Store in session for subsequent requests
            session.headers['X-Session-Id'] = session_id
            session.headers['Mcp-Session-Id'] = session_id
        else:
            print("   ⚠️  No session ID found, continuing anyway...")
        
        if init_data and 'result' in init_data:
            print("   ✅ Session initialized successfully")
            capabilities = init_data['result'].get('capabilities', {})
            tools = capabilities.get('tools', {})
            if 'listChanged' in tools:
                print(f"   ✅ Server supports tools")
        else:
            print("   ⚠️  Could not parse initialize response")
        
    except Exception as e:
        print(f"   ❌ Initialize error: {e}")
        return False
    
    # Step 2: List tools
    print("\nStep 2: Listing available tools...")
    list_tools_payload = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": 2
    }
    
    try:
        tools_response = session.post(
            BASE_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json=list_tools_payload,
            timeout=30
        )
        
        if tools_response.status_code == 200:
            tools_data = None
            for line in tools_response.text.split('\n'):
                if line.startswith('data:'):
                    try:
                        tools_data = json.loads(line[5:].strip())
                        break
                    except:
                        pass
            
            if tools_data and 'result' in tools_data:
                tools = tools_data['result'].get('tools', [])
                tool_names = [t.get('name', '') for t in tools]
                print(f"   ✅ Found {len(tools)} tools:")
                for name in tool_names[:5]:
                    print(f"      - {name}")
                if len(tools) > 5:
                    print(f"      ... and {len(tools) - 5} more")
            else:
                print("   ⚠️  Could not parse tools list")
        else:
            print(f"   ⚠️  Tools list returned {tools_response.status_code}")
    except Exception as e:
        print(f"   ⚠️  Tools list error: {e}")
    
    # Step 3: Generate image
    print("\nStep 3: Generating image 'pigs flying using picasso style'...")
    print("   Tenant: fedfina")
    print("   Prompt: pigs flying using picasso style")
    print("   Size: 1024x1024")
    print("   This may take 30-60 seconds...")
    
    generate_payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "gi_generate_image",
            "arguments": {
                "tenant_id": "fedfina",
                "prompt": "pigs flying using picasso style",
                "width": 1024,
                "height": 1024,
                "steps": 40,
                "cfg_scale": 5.0
            }
        },
        "id": 3
    }
    
    try:
        start_time = time.time()
        generate_response = session.post(
            BASE_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            json=generate_payload,
            timeout=120  # 2 minutes for image generation
        )
        
        elapsed = time.time() - start_time
        print(f"   Response received in {elapsed:.1f} seconds")
        print(f"   Status: {generate_response.status_code}")
        
        if generate_response.status_code != 200:
            print(f"   ❌ Request failed: {generate_response.text[:500]}")
            return False
        
        # Parse streaming response - look for the actual result, not just notifications
        result_data = None
        all_messages = []
        
        for line in generate_response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    msg = json.loads(line[5:].strip())
                    all_messages.append(msg)
                    # Look for the actual result (has 'id' field matching our request)
                    if 'id' in msg and msg.get('id') == 3:
                        if 'result' in msg:
                            result_data = msg
                            break
                except:
                    pass
        
        if not result_data:
            # Try regular JSON (non-streaming response)
            try:
                result_data = generate_response.json()
                if 'id' in result_data and result_data.get('id') == 3:
                    pass  # This is our result
                else:
                    # Might be a notification, look through all messages
                    for msg in all_messages:
                        if 'id' in msg and msg.get('id') == 3 and 'result' in msg:
                            result_data = msg
                            break
            except:
                # If no JSON result found, check if we got notifications
                if all_messages:
                    print(f"   ⚠️  Received {len(all_messages)} messages, waiting for result...")
                    # The result might come in a separate response or we need to poll
                    # For now, check the last message
                    if all_messages:
                        last_msg = all_messages[-1]
                        if 'result' in last_msg:
                            result_data = last_msg
                        else:
                            print(f"   ⚠️  Last message was: {last_msg.get('method', 'unknown')}")
                            print(f"   Full response text: {generate_response.text[:1000]}")
                else:
                    print(f"   ❌ Could not parse response: {generate_response.text[:500]}")
                    return False
        
        print("\n" + "=" * 70)
        if 'result' in result_data:
            content = result_data['result'].get('content', [])
            if content:
                text = content[0].get('text', '')
                try:
                    result_json = json.loads(text)
                    if result_json.get('success'):
                        print("✅ IMAGE GENERATION SUCCESSFUL!")
                        print("=" * 70)
                        print(f"Format: {result_json.get('format', 'unknown')}")
                        print(f"Dimensions: {result_json.get('width')}x{result_json.get('height')}")
                        image_data = result_json.get('image_data', '')
                        if image_data:
                            print(f"Image data: {len(image_data)} characters (base64 encoded)")
                            print(f"Preview: {image_data[:80]}...")
                            print("\n✅ Image is ready! Base64 data available.")
                            return True
                        else:
                            print("⚠️  No image data in response")
                            print(f"Full response: {json.dumps(result_json, indent=2)[:500]}")
                    else:
                        print("❌ IMAGE GENERATION FAILED")
                        print("=" * 70)
                        print(f"Error: {result_json.get('error', 'Unknown error')}")
                        return False
                except json.JSONDecodeError:
                    print("Response text:")
                    print(text[:500])
                    if 'success' in text.lower():
                        print("\n✅ Success indicated in response text")
                        return True
                    else:
                        print("\n⚠️  Could not parse JSON response")
                        return False
            else:
                print("⚠️  No content in result")
                print(f"Full response: {json.dumps(result_data, indent=2)[:500]}")
        elif 'error' in result_data:
            print("❌ ERROR FROM SERVER")
            print("=" * 70)
            error = result_data['error']
            print(f"Code: {error.get('code', 'unknown')}")
            print(f"Message: {error.get('message', 'unknown')}")
            return False
        else:
            print("⚠️  Unexpected response format")
            print(f"Response: {json.dumps(result_data, indent=2)[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print("   ❌ Request timed out (>120 seconds)")
        return False
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_remote_mcp()
    print("\n" + "=" * 70)
    if success:
        print("✅ REMOTE CLIENT TEST PASSED")
        print("   The MCP server is working correctly for remote clients!")
    else:
        print("❌ REMOTE CLIENT TEST FAILED")
        print("   The MCP server may have issues with remote client access.")
    print("=" * 70)
    sys.exit(0 if success else 1)
