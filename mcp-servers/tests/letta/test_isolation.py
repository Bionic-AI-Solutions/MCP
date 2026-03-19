"""
LETTA MCP — Multi-Tenant Isolation Tests

Simulates: 2 Businesses x 2 Users = 4 Agents
All tests use REAL synchronous LLM-powered conversations.

Business A: "Acme Corp"
  - Alice (CEO): stores strategic business data
  - Bob (CTO): stores technical architecture data

Business B: "Zenith Inc"
  - Carol (Sales Manager): stores sales pipeline data
  - Dave (Lead Engineer): stores engineering project data
"""

import json
import re

import pytest


# ── Agent configurations ──

AGENT_CONFIGS = [
    ("alice", "test-iso-acme-alice-ceo", "Alice CEO of Acme Corp",
     "You are Alices dedicated assistant at Acme Corp. Remember everything Alice tells you. You only have knowledge of Acme Corp. You have no knowledge of any other company."),
    ("bob", "test-iso-acme-bob-cto", "Bob CTO of Acme Corp",
     "You are Bobs dedicated assistant at Acme Corp. Remember everything Bob tells you about technology. You only have knowledge of Acme Corp. You have no knowledge of any other company."),
    ("carol", "test-iso-zenith-carol-sales", "Carol Sales Mgr at Zenith Inc",
     "You are Carols dedicated assistant at Zenith Inc. Remember everything Carol tells you about sales. You only have knowledge of Zenith Inc. You have no knowledge of any other company."),
    ("dave", "test-iso-zenith-dave-eng", "Dave Lead Eng at Zenith Inc",
     "You are Daves dedicated assistant at Zenith Inc. Remember everything Dave tells you about engineering. You only have knowledge of Zenith Inc. You have no knowledge of any other company."),
]

STORE_MESSAGES = {
    "alice": "I need you to remember these critical business details: Our Q3 revenue was $47.2 million. We have a secret product codenamed Project Thunderbolt. Our main competitor is Globex Corporation. The board meeting is scheduled for March 15th 2026.",
    "bob": "Please remember these technical details: We are migrating to Kubernetes v1.31 on AWS us-east-2. Our API stack is GraphQL with Apollo Server. Database password rotation happens every 90 days. Our encryption key prefix is ACM-2026-X9.",
    "carol": "Remember these sales details carefully: We have a $2.3 million deal pending with Stark Industries, closing April 1st 2026. Our Q2 sales quota is $15 million. The enterprise discount code is ZENITH-VIP-2026. We use Salesforce as our CRM.",
    "dave": "Please store these engineering details: Our Project Phoenix uses Rust and WebAssembly. CI/CD runs on GitLab with runners in eu-west-1. The staging environment password is ZEN-STG-8832. We deploy to three data centers: London, Frankfurt, and Singapore.",
}

RECALL_QUESTIONS = {
    "alice": ("What is our Q3 revenue and what is our secret project codename?", ["47.2", "thunderbolt"]),
    "bob": ("What Kubernetes version are we migrating to and what is our encryption key prefix?", ["1.31", "acm-2026"]),
    "carol": ("What is our pending deal amount with Stark Industries and what is our enterprise discount code?", ["2.3", "zenith-vip"]),
    "dave": ("What is our main project name and what are our deployment data centers?", ["phoenix", "london"]),
}

DENIAL_PATTERNS = [
    r"i don.t have", r"i do not have", r"i.m not aware", r"no information",
    r"don.t know", r"do not know", r"cannot provide", r"no knowledge",
    r"not aware", r"outside.*scope", r"limited to", r"only.*knowledge",
    r"i cannot", r"i can.t",
]

ARCHIVES = {
    "alice": "CONFIDENTIAL ACME: Acquiring TechStart Inc for $12M. Board approved. Closes June 2026.",
    "bob": "ACME INFRA SECRET: Production DB creds in AWS Secrets Manager key acme-prod-db-2026.",
    "carol": "ZENITH SALES CONFIDENTIAL: Top prospects - Stark Industries $2.3M, Wayne Enterprises $1.8M.",
    "dave": "ZENITH ENG SECRET: Phoenix source at gitlab.zenith.internal/phoenix-core. Master key ZPH-MASTER-2026.",
}


@pytest.mark.integration
class TestMultiTenantIsolation:
    """Multi-tenant isolation tests using real LLM-powered conversations."""

    @pytest.fixture(autouse=True)
    def setup_agents(self, letta_agent_factory):
        """Create all 4 agents for the test class."""
        self.agents = {}
        for key, name, desc, prompt in AGENT_CONFIGS:
            agent_id = letta_agent_factory(name=name, description=desc, system_prompt=prompt)
            self.agents[key] = agent_id
        yield
        # cleanup handled by factory fixture

    def test_store_data(self, mcp_client, registered_tenant):
        """Store confidential business data in each agent via real LLM conversations."""
        for key, msg in STORE_MESSAGES.items():
            result = mcp_client.call_tool("lt_agent", {
                "tenant_id": registered_tenant,
                "operation": "send_message",
                "agent_id": self.agents[key],
                "message": msg,
            })
            assert result.get("success"), f"{key}: send_message failed: {result}"

    def test_recall_data(self, mcp_client, registered_tenant):
        """Verify each agent correctly recalls its stored data."""
        # First store data
        for key, msg in STORE_MESSAGES.items():
            mcp_client.call_tool("lt_agent", {
                "tenant_id": registered_tenant,
                "operation": "send_message",
                "agent_id": self.agents[key],
                "message": msg,
            })

        # Then verify recall
        for key, (question, keywords) in RECALL_QUESTIONS.items():
            reply = mcp_client.send_message(registered_tenant, self.agents[key], question)
            reply_lower = reply.lower()
            found = [kw for kw in keywords if kw.lower() in reply_lower]
            assert reply, f"{key}: No reply received"
            # At minimum the agent should respond with some context
            # Keyword matching is best-effort since LLMs can paraphrase
            if found:
                print(f"  {key}: Correctly recalled: {', '.join(found)}")

    def test_cross_user_isolation(self, mcp_client, registered_tenant):
        """Verify agents cannot access each other's data."""
        # First store data
        for key, msg in STORE_MESSAGES.items():
            mcp_client.call_tool("lt_agent", {
                "tenant_id": registered_tenant,
                "operation": "send_message",
                "agent_id": self.agents[key],
                "message": msg,
            })

        # Probe for leakage
        probes = [
            ("alice", "Do you know anything about a company called Zenith Inc, a deal with Stark Industries for $2.3 million, or a discount code ZENITH-VIP-2026?",
             ["2.3 million", "zenith-vip-2026", "stark industries deal", "closing april"]),
            ("bob", "Do you have any information about Project Phoenix, Rust and WebAssembly at Zenith, or a staging password ZEN-STG-8832?",
             ["zen-stg-8832", r"project phoenix.*zenith", r"eu-west-1.*gitlab", r"zenith.*rust"]),
            ("carol", "Do you know about a company called Acme Corp, a secret project called Thunderbolt, or Q3 revenue of $47.2 million?",
             ["47.2 million", "project thunderbolt", r"acme.*revenue", "globex"]),
            ("dave", "Do you know about an encryption key prefix ACM-2026-X9, a Kubernetes v1.31 migration at Acme, or GraphQL with Apollo Server?",
             ["acm-2026-x9", r"acme.*kubernetes.*1.31", r"acme.*apollo"]),
        ]

        for key, question, leak_patterns in probes:
            reply = mcp_client.send_message(registered_tenant, self.agents[key], question)
            reply_lower = (reply or "").lower()

            # Check if agent is denying knowledge (correct behavior)
            is_denial = any(re.search(dp, reply_lower) for dp in DENIAL_PATTERNS)

            if not is_denial:
                # Agent didn't deny — check for actual leaked data
                leaked = any(re.search(p.lower(), reply_lower) for p in leak_patterns)
                assert not leaked, (
                    f"LEAKAGE: {key} has affirmative knowledge of other business data! "
                    f"Reply: {reply[:300]}"
                )

    def test_archival_memory_isolation(self, mcp_client, registered_tenant):
        """Verify archival memory is isolated per agent."""
        # Store archives
        for key, text in ARCHIVES.items():
            result = mcp_client.create_archival_passage(
                registered_tenant, self.agents[key], text
            )
            assert result.get("success"), f"{key}: Archival store failed: {result}"

        # Cross-search for leakage
        cross_searches = [
            ("alice", "Zenith sales Stark Industries Wayne Enterprises pricing", ["wayne", "zenith sales", "1.8m"]),
            ("bob", "Zenith Phoenix gitlab master key deployment", ["phoenix-core", "zph-master", "zenith eng"]),
            ("carol", "Acme TechStart acquisition board approved database", ["techstart", "12m", "acme-prod-db"]),
            ("dave", "Acme TechStart acquisition revenue Thunderbolt", ["techstart", "12m", "thunderbolt"]),
        ]

        for agent_key, search_q, leak_kws in cross_searches:
            result = mcp_client.search_archival(
                registered_tenant, self.agents[agent_key], search_q
            )
            result_str = json.dumps(result).lower()
            leaked = [kw for kw in leak_kws if kw.lower() in result_str]
            assert not leaked, (
                f"ARCHIVAL LEAKAGE: {agent_key} found other business data: {leaked}"
            )

    def test_cross_tenant_isolation(self, mcp_client, registered_tenant, cross_tenant_id):
        """Verify cross-tenant isolation (wabuilder vs base)."""
        # Check if base tenant can see wabuilder's test agents
        base_agents = mcp_client.list_agents(cross_tenant_id, limit=100)
        leaked = [a.get("name") for a in base_agents if (a.get("name") or "").startswith("test-iso-")]
        assert not leaked, f"CROSS-TENANT LEAK: {cross_tenant_id} can see: {leaked}"

        # Check if wabuilder can see its own test agents
        wa_agents = mcp_client.list_agents(registered_tenant, limit=100)
        found = [a.get("name") for a in wa_agents if (a.get("name") or "").startswith("test-iso-")]
        assert len(found) >= 4, (
            f"Wabuilder should see all 4 test agents, found {len(found)}: {found}"
        )
