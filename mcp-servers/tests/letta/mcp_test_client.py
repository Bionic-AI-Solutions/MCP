"""
Reusable MCP-over-HTTP test client for Letta integration tests.

Extracts the SSE/JSON-RPC protocol logic from the standalone test scripts
into a clean, reusable class. Handles both structuredContent and content[]
response formats from FastMCP.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

import httpx


class LettaMCPTestClient:
    """MCP-over-HTTP client for Letta integration tests.

    Usage::

        client = LettaMCPTestClient()
        client.initialize()

        agent_id = client.create_agent("wabuilder", "my-test-agent")
        reply = client.send_message("wabuilder", agent_id, "Hello!")
        client.delete_agent("wabuilder", agent_id)

        client.close()
    """

    def __init__(
        self,
        mcp_url: Optional[str] = None,
        timeout: float = 180.0,
    ):
        self.mcp_url = mcp_url or os.environ.get(
            "LETTA_MCP_URL", "https://mcp.baisoln.com/letta/mcp"
        )
        self.http = httpx.Client(
            timeout=timeout, verify=False, follow_redirects=True
        )
        self.session_id: Optional[str] = None
        self._call_counter = 10

    def initialize(self) -> str:
        """Perform MCP session initialization handshake. Returns session_id."""
        result, err = self._mcp_call("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "letta-pytest", "version": "1.0"},
        })
        if err:
            raise RuntimeError(f"MCP initialization failed: {err}")

        # Send initialized notification
        self._mcp_call("notifications/initialized", {})
        return self.session_id

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool. Returns parsed result dict.

        Handles both response formats:
        - structuredContent (direct dict in result)
        - content[] (text items with embedded JSON)
        """
        self._call_counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._call_counter,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        resp = self.http.post(self.mcp_url, json=payload, headers=headers)

        # Update session ID from response headers
        new_sid = resp.headers.get("Mcp-Session-Id")
        if new_sid:
            self.session_id = new_sid

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            return self._parse_sse_tool_result(resp.text)
        else:
            data = resp.json()
            if "error" in data:
                return {"success": False, "error": data["error"].get("message", str(data["error"]))}
            result = data.get("result", {})
            return self._extract_tool_result(result)

    # ── Convenience wrappers ──

    def register_tenant(
        self,
        tenant_id: str,
        base_url: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 120,
        graphiti_url: Optional[str] = None,
    ) -> dict:
        """Register a tenant via lt_register_tenant."""
        args = {
            "tenant_id": tenant_id,
            "base_url": base_url or os.environ.get(
                "LETTA_BASE_URL",
                "http://letta-server.letta.svc.cluster.local:8283",
            ),
            "timeout": timeout,
        }
        if password or os.environ.get("LETTA_PASSWORD"):
            args["password"] = password or os.environ.get("LETTA_PASSWORD", "")
        if graphiti_url or os.environ.get("LETTA_GRAPHITI_URL"):
            args["graphiti_url"] = graphiti_url or os.environ.get("LETTA_GRAPHITI_URL")
        return self.call_tool("lt_register_tenant", args)

    def create_agent(
        self,
        tenant_id: str,
        name: str,
        model: str = "openai/gpt-4o-mini",
        description: str = "Automated test agent",
        system_prompt: str = "You are a test assistant. Remember everything you are told.",
        enable_sleeptime: bool = False,
        **kwargs,
    ) -> str:
        """Create an agent and return its agent_id. Raises on failure."""
        args = {
            "tenant_id": tenant_id,
            "operation": "create",
            "name": name,
            "model": model,
            "description": description,
            "system_prompt": system_prompt,
        }
        if enable_sleeptime:
            args["enable_sleeptime"] = True
        args.update(kwargs)

        result = self.call_tool("lt_agent", args)
        agent_id = self._extract_agent_id(result)
        if not agent_id:
            raise RuntimeError(f"Agent creation failed: {result}")
        return agent_id

    def delete_agent(self, tenant_id: str, agent_id: str) -> bool:
        """Delete an agent. Returns True on success, False on failure."""
        result = self.call_tool("lt_agent", {
            "tenant_id": tenant_id,
            "operation": "delete",
            "agent_id": agent_id,
        })
        return result.get("success", False)

    def send_message(self, tenant_id: str, agent_id: str, message: str) -> str:
        """Send a message to an agent and return the assistant's reply text."""
        result = self.call_tool("lt_agent", {
            "tenant_id": tenant_id,
            "operation": "send_message",
            "agent_id": agent_id,
            "message": message,
        })
        return self._extract_reply(result)

    def list_agents(self, tenant_id: str, limit: int = 100) -> List[dict]:
        """List agents for a tenant. Returns list of agent summaries."""
        result = self.call_tool("lt_agent", {
            "tenant_id": tenant_id,
            "operation": "list",
            "limit": limit,
        })
        agents = result.get("agents", result.get("data", []))
        return agents if isinstance(agents, list) else []

    def search_archival(
        self, tenant_id: str, agent_id: str, query: str
    ) -> dict:
        """Search an agent's archival memory."""
        return self.call_tool("lt_memory", {
            "tenant_id": tenant_id,
            "operation": "search_archival",
            "agent_id": agent_id,
            "query": query,
        })

    def create_archival_passage(
        self, tenant_id: str, agent_id: str, text: str
    ) -> dict:
        """Create an archival memory passage for an agent."""
        return self.call_tool("lt_memory", {
            "tenant_id": tenant_id,
            "operation": "create_passage",
            "agent_id": agent_id,
            "text": text,
        })

    def close(self):
        """Close the HTTP client."""
        self.http.close()

    # ── Internal helpers ──

    def _mcp_call(self, method: str, params: dict):
        """Low-level JSON-RPC 2.0 call to the MCP server."""
        self._call_counter += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._call_counter,
            "method": method,
            "params": params,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        resp = self.http.post(self.mcp_url, json=payload, headers=headers)

        new_sid = resp.headers.get("Mcp-Session-Id")
        if new_sid:
            self.session_id = new_sid

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "error" in data:
                            return None, data["error"]
                        if "result" in data:
                            return data["result"], None
                    except json.JSONDecodeError:
                        pass
            return None, {"message": "No result in SSE response"}
        else:
            data = resp.json()
            if "error" in data:
                return None, data["error"]
            return data.get("result"), None

    def _parse_sse_tool_result(self, text: str) -> dict:
        """Parse SSE response from a tools/call and extract the result."""
        for line in text.split("\n"):
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            if "error" in data:
                err = data["error"]
                return {"success": False, "error": err.get("message", str(err))}

            result = data.get("result")
            if result:
                return self._extract_tool_result(result)

        return {"success": False, "error": "No SSE data lines in response"}

    @staticmethod
    def _extract_tool_result(result: dict) -> dict:
        """Extract structured result from either response format."""
        # Format 1: structuredContent (direct dict)
        if "structuredContent" in result:
            return result["structuredContent"]

        # Format 2: content[] with text items containing embedded JSON
        if "content" in result:
            for item in result["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except (json.JSONDecodeError, TypeError):
                        return {"success": True, "data": item.get("text", "")}

        return result

    @staticmethod
    def _extract_agent_id(result: dict) -> str:
        """Extract agent_id from various response formats."""
        # Direct fields
        for key in ("data", "agent"):
            val = result.get(key)
            if isinstance(val, dict) and val.get("id"):
                return val["id"]
        return result.get("agent_id", "")

    @staticmethod
    def _extract_reply(result: dict) -> str:
        """Extract the assistant's text reply from send_message response."""
        # Normalized format: {"success": true, "messages": [...]}
        messages = result.get("messages", [])
        if not messages:
            # Old format: {"success": true, "response": ...}
            resp = result.get("response", result.get("data", {}))
            if isinstance(resp, list):
                messages = resp
            elif isinstance(resp, dict):
                messages = resp.get("messages", [])

        for m in messages:
            if m.get("message_type") == "assistant_message":
                return m.get("assistant_message") or m.get("content", "")
        return ""


def cleanup_orphaned_test_agents(
    client: LettaMCPTestClient,
    tenant_id: str,
    prefix: str = "test-",
) -> int:
    """Find and delete all agents whose names start with prefix.

    Returns the number of agents deleted.
    """
    agents = client.list_agents(tenant_id, limit=1000)
    orphans = [a for a in agents if (a.get("name") or "").startswith(prefix)]
    deleted = 0
    for agent in orphans:
        agent_id = agent.get("id", "")
        if agent_id:
            if client.delete_agent(tenant_id, agent_id):
                deleted += 1
            else:
                print(f"Warning: Failed to delete orphan agent {agent_id}")
    return deleted
