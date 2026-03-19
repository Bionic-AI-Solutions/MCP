"""
End-to-end tests for Letta MCP server conversation operations.

Tests Phase 1: create_conversation, send_conversation_message, list_conversations
Tests Phase 2: get_letta_url

Usage:
    python tests/letta/test_conversations.py
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from tests.letta.mcp_test_client import LettaMCPTestClient

TENANT_ID = "wabuilder"


def test_conversations():
    """Full end-to-end test of conversation operations."""
    client = LettaMCPTestClient()
    client.initialize()

    # Register tenant (with password and generous timeout for agent creation)
    reg = client.register_tenant(
        TENANT_ID,
        password=os.environ.get("LETTA_PASSWORD", "L3ttaS3rv3rTh1515T0p53cr3t"),
        timeout=120,
    )
    print(f"[1/8] Register tenant: {'OK' if reg.get('success') else 'FAIL'} - {reg}")

    # Create a test agent with a memory block we can isolate
    agent_name = f"test-conv-{int(time.time())}"
    agent_id = client.create_agent(
        TENANT_ID,
        agent_name,
        model="openai/gpt-4o-mini",
        description="Conversation test agent",
        system_prompt="You are a helpful assistant for testing conversations. Keep responses short.",
        memory_blocks=[
            {"label": "human", "value": ""},
            {"label": "persona", "value": "You are a test assistant."},
            {"label": "customer_context", "value": "No customer yet."},
        ],
    )
    print(f"[2/8] Create agent: OK - agent_id={agent_id}")

    created_conversations = []

    try:
        # ── Test 1: create_conversation ──
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "create_conversation",
            "agent_id": agent_id,
            "isolated_block_labels": ["customer_context"],
            "summary": "Test call isolation - caller 1",
        })
        print(f"[3/8] create_conversation: {'OK' if result.get('success') else 'FAIL'}")
        print(f"       Response: {result}")
        assert result.get("success"), f"create_conversation failed: {result}"

        conv = result.get("conversation", {})
        conv_id_1 = conv.get("id")
        assert conv_id_1, f"No conversation ID returned: {result}"
        created_conversations.append(conv_id_1)
        print(f"       conversation_id={conv_id_1}")

        # ── Test 2: send_conversation_message ──
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "send_conversation_message",
            "conversation_id": conv_id_1,
            "message": "Hello! My name is Alice and I want to book an appointment.",
        })
        print(f"[4/8] send_conversation_message: {'OK' if result.get('success') else 'FAIL'}")
        print(f"       Response keys: {list(result.keys())}")
        assert result.get("success"), f"send_conversation_message failed: {result}"

        messages = result.get("messages", [])
        print(f"       Messages count: {len(messages)}")
        # Extract assistant reply
        assistant_reply = ""
        for m in messages:
            if m.get("message_type") == "assistant_message":
                assistant_reply = m.get("assistant_message") or m.get("content", "")
                break
        print(f"       Assistant reply: {assistant_reply[:200]}")

        # ── Test 3: Create a SECOND conversation to verify isolation ──
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "create_conversation",
            "agent_id": agent_id,
            "isolated_block_labels": ["customer_context"],
            "summary": "Test call isolation - caller 2",
        })
        print(f"[5/8] create_conversation (2nd): {'OK' if result.get('success') else 'FAIL'}")
        assert result.get("success"), f"create_conversation (2nd) failed: {result}"

        conv2 = result.get("conversation", {})
        conv_id_2 = conv2.get("id")
        assert conv_id_2, f"No conversation ID returned for 2nd: {result}"
        created_conversations.append(conv_id_2)
        print(f"       conversation_id={conv_id_2}")

        # Send message in 2nd conversation - should NOT know about Alice
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "send_conversation_message",
            "conversation_id": conv_id_2,
            "message": "Hi, who am I?",
        })
        print(f"[6/8] send_conversation_message (2nd conv): {'OK' if result.get('success') else 'FAIL'}")
        assert result.get("success"), f"send_conversation_message (2nd) failed: {result}"
        messages2 = result.get("messages", [])
        reply2 = ""
        for m in messages2:
            if m.get("message_type") == "assistant_message":
                reply2 = m.get("assistant_message") or m.get("content", "")
                break
        print(f"       Reply (should NOT mention Alice): {reply2[:200]}")

        # ── Test 4: list_conversations ──
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "list_conversations",
            "agent_id": agent_id,
        })
        print(f"[7/8] list_conversations: {'OK' if result.get('success') else 'FAIL'}")
        assert result.get("success"), f"list_conversations failed: {result}"
        conversations = result.get("conversations", [])
        print(f"       Conversations count: {len(conversations)}")
        for c in conversations:
            print(f"       - id={c.get('id')}, summary={c.get('summary', 'N/A')}")
        # We should see at least our 2 conversations
        conv_ids = [c.get("id") for c in conversations]
        assert conv_id_1 in conv_ids, f"conversation_id_1 not in list: {conv_ids}"
        assert conv_id_2 in conv_ids, f"conversation_id_2 not in list: {conv_ids}"

        # ── Test 5: get_letta_url (Phase 2) ──
        result = client.call_tool("lt_agent", {
            "tenant_id": TENANT_ID,
            "operation": "get_letta_url",
        })
        print(f"[8/8] get_letta_url: {'OK' if result.get('success') else 'FAIL'}")
        assert result.get("success"), f"get_letta_url failed: {result}"
        assert result.get("letta_url"), f"No letta_url returned: {result}"
        print(f"       letta_url={result.get('letta_url')}")
        print(f"       auth_token={'set' if result.get('auth_token') else 'none'}")

        print("\n=== ALL TESTS PASSED ===")

    except Exception as e:
        print(f"\n!!! TEST FAILED: {e}")
        raise

    finally:
        # Cleanup: delete the test agent (conversations are deleted with it)
        ok = client.delete_agent(TENANT_ID, agent_id)
        print(f"\nCleanup: delete agent {agent_id}: {'OK' if ok else 'FAIL'}")
        client.close()


if __name__ == "__main__":
    test_conversations()
