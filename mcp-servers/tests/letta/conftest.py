"""
Pytest fixtures for Letta MCP integration tests.

Provides session-scoped MCP client, tenant registration, and
function-scoped agent creation with guaranteed cleanup.
"""

import os
import time

import pytest

from tests.letta.mcp_test_client import LettaMCPTestClient, cleanup_orphaned_test_agents


# ── Session-scoped fixtures (one per test run) ──


@pytest.fixture(scope="session")
def mcp_client():
    """Session-scoped MCP client — one HTTP session per test run."""
    client = LettaMCPTestClient(
        mcp_url=os.environ.get("LETTA_MCP_URL", "https://mcp.baisoln.com/letta/mcp"),
        timeout=float(os.environ.get("LETTA_TEST_TIMEOUT", "180")),
    )
    client.initialize()
    yield client
    client.close()


@pytest.fixture(scope="session")
def tenant_id():
    """The tenant ID to use for tests."""
    return os.environ.get("LETTA_TEST_TENANT", "wabuilder")


@pytest.fixture(scope="session")
def cross_tenant_id():
    """A different tenant for cross-tenant isolation checks."""
    return os.environ.get("LETTA_CROSS_TENANT", "base")


@pytest.fixture(scope="session")
def registered_tenant(mcp_client, tenant_id):
    """Ensure the test tenant is registered with a generous timeout."""
    result = mcp_client.register_tenant(
        tenant_id=tenant_id,
        password=os.environ.get("LETTA_PASSWORD", "L3ttaS3rv3rTh1515T0p53cr3t"),
        timeout=120,
        graphiti_url=os.environ.get("LETTA_GRAPHITI_URL",
                                     "http://graphiti-service.letta.svc.cluster.local:8200"),
    )
    yield tenant_id
    # Restore original timeout
    mcp_client.register_tenant(
        tenant_id=tenant_id,
        password=os.environ.get("LETTA_PASSWORD", "L3ttaS3rv3rTh1515T0p53cr3t"),
        timeout=30,
        graphiti_url=os.environ.get("LETTA_GRAPHITI_URL",
                                     "http://graphiti-service.letta.svc.cluster.local:8200"),
    )


# ── Function-scoped fixtures (one per test) ──


@pytest.fixture
def letta_agent(mcp_client, registered_tenant):
    """Create a single test agent, yield its ID, delete on teardown."""
    agent_id = mcp_client.create_agent(
        tenant_id=registered_tenant,
        name=f"test-agent-{int(time.time())}",
        model="openai/gpt-4o-mini",
        description="Automated test agent",
        system_prompt="You are a test assistant. Remember everything you are told.",
    )
    yield agent_id
    mcp_client.delete_agent(registered_tenant, agent_id)


@pytest.fixture
def letta_agent_factory(mcp_client, registered_tenant):
    """Factory fixture: create multiple agents with custom configs.

    All agents created through the factory are automatically cleaned up
    after the test, even if the test fails.

    Usage::

        def test_something(letta_agent_factory):
            alice = letta_agent_factory("test-alice", system_prompt="You are Alice.")
            bob = letta_agent_factory("test-bob", system_prompt="You are Bob.")
    """
    created_agents = []

    def _create(
        name: str,
        description: str = "Automated test agent",
        system_prompt: str = "You are a test assistant.",
        model: str = "openai/gpt-4o-mini",
        **kwargs,
    ) -> str:
        agent_id = mcp_client.create_agent(
            tenant_id=registered_tenant,
            name=name,
            description=description,
            system_prompt=system_prompt,
            model=model,
            **kwargs,
        )
        created_agents.append(agent_id)
        return agent_id

    yield _create

    # Cleanup all agents created by this factory
    for agent_id in created_agents:
        try:
            mcp_client.delete_agent(registered_tenant, agent_id)
        except Exception as e:
            print(f"Warning: cleanup failed for agent {agent_id}: {e}")


@pytest.fixture
def sleeptime_agent(mcp_client, registered_tenant):
    """Create a sleeptime-enabled agent for latency tests."""
    agent_id = mcp_client.create_agent(
        tenant_id=registered_tenant,
        name=f"test-sleeptime-{int(time.time())}",
        model="openai/gpt-4o-mini",
        enable_sleeptime=True,
        sleeptime_agent_frequency=5,
        memory_blocks=[
            {"label": "human", "value": ""},
            {"label": "persona", "value": "You are a fast, concise test assistant. Keep responses under 2 sentences."},
        ],
        description="Automated sleeptime test agent",
    )
    yield agent_id
    mcp_client.delete_agent(registered_tenant, agent_id)


# ── Orphan cleanup ──


@pytest.fixture(scope="session", autouse=True)
def cleanup_orphans(mcp_client, tenant_id):
    """Clean up orphaned test agents from previous failed runs."""
    deleted = cleanup_orphaned_test_agents(mcp_client, tenant_id, prefix="test-iso-")
    if deleted:
        print(f"\nCleaned up {deleted} orphaned test-iso- agents")
    yield
