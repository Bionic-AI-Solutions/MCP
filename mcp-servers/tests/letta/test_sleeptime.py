"""
LETTA MCP — Sleeptime Agent Latency Tests

Tests that sleeptime-enabled agents can:
1. Be created with proper multi-agent group configuration
2. Store and recall information
3. Respond to queries

Latency comparisons are logged but not hard-asserted (performance varies).
"""

import time

import pytest


@pytest.mark.integration
class TestSleeptimeAgent:
    """Sleeptime agent functionality and latency tests."""

    def test_agent_creation(self, mcp_client, registered_tenant, sleeptime_agent):
        """Verify sleeptime agent was created with proper config."""
        result = mcp_client.call_tool("lt_agent", {
            "tenant_id": registered_tenant,
            "operation": "get",
            "agent_id": sleeptime_agent,
        })
        assert result.get("success"), f"Failed to get agent: {result}"

        agent = result.get("agent", {})
        assert agent.get("enable_sleeptime") is True, "Sleeptime should be enabled"

        group = agent.get("multi_agent_group")
        if group:
            bg_agents = group.get("agent_ids", [])
            print(f"  Sleep-time background agents: {len(bg_agents)}")
            print(f"  Manager type: {group.get('manager_type')}")

    def test_store_and_recall(self, mcp_client, registered_tenant, sleeptime_agent):
        """Store information and verify the agent can recall it."""
        # Store
        reply = mcp_client.send_message(
            registered_tenant, sleeptime_agent,
            "Our deployment date for Project Aurora is March 5th 2026. Please remember this important date.",
        )
        assert reply, "Agent should acknowledge the stored information"

        # Recall
        reply = mcp_client.send_message(
            registered_tenant, sleeptime_agent,
            "When is the deployment date for Project Aurora?",
        )
        assert "march" in reply.lower() or "5" in reply, (
            f"Agent should recall 'March 5th' but replied: {reply[:200]}"
        )

    def test_response_latency(self, mcp_client, registered_tenant, sleeptime_agent):
        """Measure response latencies for a sequence of messages.

        Latency thresholds are NOT hard-asserted since they depend on
        infrastructure and LLM provider performance. Results are logged.
        """
        messages = [
            ("intro", "Hi, I'm John from the engineering team. What can you help me with?"),
            ("store", "Please remember: our CI pipeline uses GitHub Actions with 3 runners."),
            ("recall", "What CI pipeline setup did I just mention?"),
            ("quick", "What's 15 times 23?"),
        ]

        timings = {}
        for label, msg in messages:
            t0 = time.time()
            reply = mcp_client.send_message(registered_tenant, sleeptime_agent, msg)
            elapsed = time.time() - t0
            timings[label] = elapsed
            print(f"  [{label}] {elapsed:.1f}s — {(reply or '(no reply)')[:150]}")

        # Log summary (informational, not asserted)
        avg = sum(timings.values()) / len(timings) if timings else 0
        print(f"\n  Average response time: {avg:.1f}s")
        print(f"  Individual: {', '.join(f'{k}={v:.1f}s' for k, v in timings.items())}")
