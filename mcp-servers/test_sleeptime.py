#!/usr/bin/env python3
"""Live test: Create a Letta agent with sleeptime enabled and compare response latency."""

import json
import time
import httpx
import sys

MCP_URL = "https://mcp.baisoln.com/letta/mcp"
TENANT = "wabuilder"
TIMEOUT = 180

def parse_sse(text):
    """Parse SSE response and extract JSON-RPC result."""
    result = None
    for line in text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if "result" in data or "error" in data:
                    result = data
            except json.JSONDecodeError:
                pass
    return result

def mcp_call(client, session_id, method, params=None):
    """Make a JSON-RPC 2.0 call to the MCP server via SSE."""
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params or {}
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    resp = client.post(MCP_URL, json=payload, headers=headers, timeout=TIMEOUT)
    new_session_id = resp.headers.get("Mcp-Session-Id") or session_id
    content_type = resp.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        parsed = parse_sse(resp.text)
        if parsed and "error" in parsed:
            return None, parsed["error"], new_session_id
        if parsed and "result" in parsed:
            return parsed["result"], None, new_session_id
        return None, {"code": -1, "message": "No result in SSE"}, new_session_id
    else:
        data = resp.json()
        if "error" in data:
            return None, data["error"], new_session_id
        return data.get("result"), None, new_session_id

def call_tool(client, session_id, tool_name, arguments):
    """Call an MCP tool and return the parsed result."""
    result, err, session_id = mcp_call(client, session_id, "tools/call", {
        "name": tool_name,
        "arguments": arguments
    })
    if err:
        return None, err, session_id
    if result and "content" in result:
        for item in result["content"]:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"]), None, session_id
                except json.JSONDecodeError:
                    return item["text"], None, session_id
    return result, None, session_id

def extract_reply(result):
    """Extract assistant reply from MCP send_message result."""
    if not result or not result.get("success"):
        return "(no response)"
    # New normalized format: {"success": true, "messages": [...], "usage": ...}
    messages = result.get("messages", [])
    # Fallback: old format {"success": true, "response": [...]}
    if not messages:
        resp = result.get("response", [])
        if isinstance(resp, list):
            messages = resp
        elif isinstance(resp, dict):
            messages = resp.get("messages", [])
    for m in messages:
        if m.get("message_type") == "assistant_message":
            return m.get("content") or m.get("assistant_message") or ""
    return "(no assistant_message found)"

def main():
    print("=" * 70)
    print("SLEEPTIME AGENT LIVE TEST")
    print("=" * 70)

    client = httpx.Client(verify=False, follow_redirects=True)

    # Step 1: Initialize
    print("\n[1] Initializing MCP session...")
    result, err, session_id = mcp_call(client, None, "initialize", {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "sleeptime-test", "version": "1.0"}
    })
    if err:
        print(f"  FAIL: {err}")
        sys.exit(1)
    print(f"  OK: Session {session_id[:30]}...")
    mcp_call(client, session_id, "notifications/initialized", {})

    # Step 2: Create agent WITH sleeptime
    print("\n[2] Creating sleeptime-enabled agent...")
    t0 = time.time()
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT,
        "operation": "create",
        "name": "sleeptime-voice-test",
        "model": "openai/gpt-4o-mini",
        "enable_sleeptime": True,
        "sleeptime_agent_frequency": 5,
        "memory_blocks": [
            {"label": "human", "value": ""},
            {"label": "persona", "value": "You are a fast, concise voice assistant for TechFlow Solutions. Keep all responses under 2 sentences. Be direct."}
        ],
        "description": "Sleeptime voice latency test"
    })
    create_time = time.time() - t0
    if err:
        print(f"  FAIL ({create_time:.1f}s): {err}")
        sys.exit(1)
    if not result or not result.get("success"):
        print(f"  FAIL: {json.dumps(result, indent=2)[:500] if result else 'No result'}")
        sys.exit(1)

    agent_data = result.get("agent", {})
    agent_id = agent_data.get("id", "")
    print(f"  OK: Created in {create_time:.1f}s")
    print(f"  Agent ID: {agent_id}")
    print(f"  enable_sleeptime: {agent_data.get('enable_sleeptime')}")
    has_group = agent_data.get("multi_agent_group") is not None
    print(f"  multi_agent_group: {has_group}")

    if not agent_id:
        sys.exit(1)

    # Step 3: Verify config
    print("\n[3] Verifying sleeptime config...")
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "get", "agent_id": agent_id
    })
    if not err and result and result.get("success"):
        agent = result.get("agent", {})
        print(f"  enable_sleeptime: {agent.get('enable_sleeptime')}")
        group = agent.get("multi_agent_group")
        if group:
            bg_agents = group.get("agent_ids", [])
            print(f"  Sleep-time background agents: {len(bg_agents)}")
            print(f"  Manager type: {group.get('manager_type')}")

    # Step 4: Message 1 - Introduction
    print("\n[4] Message 1: Introduction...")
    t0 = time.time()
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "send_message", "agent_id": agent_id,
        "message": "Hi, I'm John from the engineering team. What can you help me with?"
    })
    msg1_time = time.time() - t0
    msg1_text = extract_reply(result) if not err else f"ERROR: {err}"
    print(f"  Time: {msg1_time:.1f}s")
    print(f"  Reply: {msg1_text[:200]}")

    # Step 5: Message 2 - Store information
    print("\n[5] Message 2: Store information...")
    t0 = time.time()
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "send_message", "agent_id": agent_id,
        "message": "Our deployment date for Project Aurora is March 5th 2026. Please remember this important date."
    })
    msg2_time = time.time() - t0
    msg2_text = extract_reply(result) if not err else f"ERROR: {err}"
    print(f"  Time: {msg2_time:.1f}s")
    print(f"  Reply: {msg2_text[:200]}")

    # Step 6: Message 3 - Recall test
    print("\n[6] Message 3: Recall test...")
    t0 = time.time()
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "send_message", "agent_id": agent_id,
        "message": "When is the deployment date for Project Aurora?"
    })
    msg3_time = time.time() - t0
    msg3_text = extract_reply(result) if not err else f"ERROR: {err}"
    print(f"  Time: {msg3_time:.1f}s")
    print(f"  Reply: {msg3_text[:200]}")
    recall_ok = "march" in msg3_text.lower() and "5" in msg3_text
    print(f"  Recall: {'PASS' if recall_ok else 'CHECK MANUALLY'}")

    # Step 7: Message 4 - Quick response test
    print("\n[7] Message 4: Quick response test...")
    t0 = time.time()
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "send_message", "agent_id": agent_id,
        "message": "What's 15 times 23?"
    })
    msg4_time = time.time() - t0
    msg4_text = extract_reply(result) if not err else f"ERROR: {err}"
    print(f"  Time: {msg4_time:.1f}s")
    print(f"  Reply: {msg4_text[:200]}")

    # Step 8: Clean up
    print("\n[8] Cleaning up...")
    result, err, session_id = call_tool(client, session_id, "lt_agent", {
        "tenant_id": TENANT, "operation": "delete", "agent_id": agent_id
    })
    print(f"  {'OK: Agent deleted' if not err else f'FAIL: {err}'}")

    # Summary
    times = [t for t in [msg1_time, msg2_time, msg3_time, msg4_time] if t < 900]
    print("\n" + "=" * 70)
    print("LATENCY RESULTS")
    print("=" * 70)
    print(f"  Agent creation:         {create_time:.1f}s")
    print(f"  Msg 1 (intro):          {msg1_time:.1f}s")
    print(f"  Msg 2 (store info):     {msg2_time:.1f}s")
    print(f"  Msg 3 (recall):         {msg3_time:.1f}s")
    print(f"  Msg 4 (quick calc):     {msg4_time:.1f}s")
    if times:
        avg = sum(times) / len(times)
        baseline = 57.9
        print(f"  ─────────────────────────────────")
        print(f"  Average response:       {avg:.1f}s")
        print(f"  Baseline (no sleep):    {baseline:.1f}s")
        if avg < baseline:
            pct = ((baseline - avg) / baseline) * 100
            print(f"  Latency reduction:      {pct:.0f}%")
            print(f"  Speedup:                {baseline/avg:.1f}x faster")
    print("=" * 70)
    client.close()

if __name__ == "__main__":
    main()
