"""
Letta MCP Server (Multi-tenant)

A FastMCP server providing full Letta AI agent platform operations with multi-tenant support.
Exposes 18 consolidated tools covering 202 operations: agents (33), memory (20),
tools (13), sources (15), jobs (4), files/folders (8), MCP integrations (14),
temporal memory (5), conversations (6), groups (12), identities (10), runs/steps (17),
archives (9), models/providers (10), sandboxes (12), and miscellaneous (8).

Compatible with Letta v0.16.4+. Graphiti temporal memory requires a Graphiti service.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.letta.tenant_manager import LettaTenantManager
except ImportError:
    from .tenant_manager import LettaTenantManager

# Initialize tenant manager
tenant_manager = LettaTenantManager()


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan — initialize tenants from Redis and cleanup on shutdown."""
    await tenant_manager.initialize()
    yield
    await tenant_manager.close_all()


mcp = FastMCP("Letta Server", lifespan=lifespan)


# ============================================================================
# Helpers
# ============================================================================

def _truncate(text: Optional[str], max_len: int = 200) -> Optional[str]:
    """Truncate text for response size optimization."""
    if text and len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _paginate_params(limit: int = 15, offset: int = 0) -> Dict[str, Any]:
    """Build pagination query params."""
    return {"limit": limit, "offset": offset}


async def _api_call(
    tenant_id: str,
    method: str,
    path: str,
    params: Optional[Dict] = None,
    json_body: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Make an authenticated API call to the Letta instance for the given tenant."""
    try:
        info = await tenant_manager.get_client(tenant_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    client = info["client"]
    semaphore = info["semaphore"]

    async with semaphore:
        try:
            resp = await client.request(method, path, params=params, json=json_body)
            if resp.status_code >= 400:
                return {
                    "success": False,
                    "error": f"Letta API error {resp.status_code}: {resp.text[:500]}",
                }
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": f"Request failed: {str(e)}"}


async def _api_call_stream(
    tenant_id: str,
    path: str,
    json_body: Optional[Dict] = None,
    params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Make a streaming POST to the Letta API, collecting SSE chunks into a final response."""
    try:
        info = await tenant_manager.get_client(tenant_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    client = info["client"]
    semaphore = info["semaphore"]
    stream_params = dict(params or {})
    stream_params["stream_steps"] = "true"
    stream_params["stream_tokens"] = "true"

    async with semaphore:
        try:
            collected_messages = []
            usage = None
            async with client.stream("POST", path, json=json_body, params=stream_params) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    return {"success": False, "error": f"Letta API error {resp.status_code}: {body.decode()[:500]}"}
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            # Collect step-level messages (not individual tokens)
                            if isinstance(event, dict):
                                if "messages" in event:
                                    collected_messages.extend(event["messages"])
                                elif "usage" in event:
                                    usage = event["usage"]
                                elif event.get("message_type") or event.get("role"):
                                    collected_messages.append(event)
                        except json.JSONDecodeError:
                            pass
            return {"success": True, "data": {"messages": collected_messages, "usage": usage}}
        except Exception as e:
            return {"success": False, "error": f"Stream request failed: {str(e)}"}


async def _auto_attach_org_identity(tenant_id: str, agent_id: str) -> Optional[str]:
    """Attach the tenant's org identity to a newly created agent. Returns warning string or None."""
    config = tenant_manager.configs.get(tenant_id)
    if not config or not config.org_identity_id or not agent_id:
        return None
    result = await _api_call(
        tenant_id, "PATCH",
        f"/v1/agents/{agent_id}/identities/attach/{config.org_identity_id}"
    )
    if not result.get("success"):
        return f"Org identity attach failed: {result.get('error', 'unknown')}"
    return None


async def _graphiti_call(
    tenant_id: str,
    method: str,
    path: str,
    params: Optional[Dict] = None,
    json_body: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Make an HTTP call to the Graphiti temporal memory service for a tenant."""
    try:
        client = await tenant_manager.get_graphiti_client(tenant_id)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        resp = await client.request(method, path, params=params, json=json_body)
        if resp.status_code >= 400:
            return {
                "success": False,
                "error": f"Graphiti API error {resp.status_code}: {resp.text[:500]}",
            }
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return {"success": True, "data": data}
    except Exception as e:
        return {"success": False, "error": f"Graphiti request failed: {str(e)}"}


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "letta-mcp-server",
        "version": "2.0.0",
        "tenant_manager_initialized": tenant_manager is not None,
    })


# ============================================================================
# Tool 0: Tenant Registration & Management
# ============================================================================

@mcp.tool
async def lt_register_tenant(
    tenant_id: str,
    base_url: str,
    password: Optional[str] = None,
    timeout: int = 30,
    max_concurrency: int = 5,
    graphiti_url: Optional[str] = None,
    org_identity_id: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new Letta AI platform tenant connection with automatic org isolation.

    Creates and validates an HTTP client connection to a Letta instance. On successful
    registration, an org-level Letta identity is automatically created (or upserted) for
    this tenant. This identity provides tenant isolation: agents created through this
    tenant are automatically associated with its org identity, and agent listings are
    scoped to only show agents belonging to this tenant.

    Multiple tenants can share the same Letta backend while maintaining isolated agent
    and memory namespaces through this identity-based separation.

    Args:
        tenant_id: A unique identifier for this tenant (e.g., "production", "staging").
                   Must be alphanumeric with hyphens/underscores. Used in all subsequent
                   tool calls to route to the correct Letta instance.
        base_url: Full base URL of the Letta API, including protocol and port
                  (e.g., "http://letta:8283" for in-cluster, "https://letta.example.com").
                  Do NOT include trailing /v1 — the server adds API paths automatically.
        password: Optional Letta API password/token for Bearer authentication.
                  Required if the Letta instance has auth enabled. Defaults to None.
        timeout: HTTP request timeout in seconds. Defaults to 30.
                 Increase for slow networks or large operations (e.g., file uploads).
        max_concurrency: Maximum number of concurrent API requests for this tenant.
                         Defaults to 5. Increase for high-throughput workloads.
        graphiti_url: Optional URL of the Graphiti temporal memory service for this tenant
                      (e.g., "http://graphiti-service:8200"). Required to use lt_temporal_memory.
                      Do NOT include trailing slash.
        org_identity_id: Optional pre-provisioned Letta org identity UUID. If not provided,
                         one is automatically created via upsert using identifier_key
                         "mcp-tenant-<tenant_id>". Use this to map a tenant to an existing
                         Letta identity. Env var: LETTA_TENANT_<ID>_ORG_IDENTITY_ID.

    Returns:
        dict: On success: {"success": True, "message": str, "tenant_id": str, "org_identity_id": str}
              On failure: {"success": False, "error": str}

    Notes:
        - The connection is validated via Letta health check before registration.
        - Config persists in Redis DB 10 under key "mcp:letta:tenant:<tenant_id>".
        - Org identity uses identifier_key "mcp-tenant-<tenant_id>" — idempotent across restarts.
        - To update a tenant, call this again with the same tenant_id (overwrites).
        - Tenants can be pre-configured via env vars: LETTA_TENANT_<ID>_BASE_URL, etc.

    Tenant Isolation:
        - Each tenant gets an org identity in Letta (auto-created or pre-provisioned).
        - Agents created via lt_agent "create" are automatically attached to the tenant's org identity.
        - Agent listings (lt_agent "list", "count", "search") are scoped to the tenant's identity.
        - Direct access by agent_id (lt_agent "get") is NOT scoped — use for cross-tenant admin only.
        - To migrate pre-existing agents into a tenant, use lt_agent "attach_identity" with
          the tenant's org_identity_id.
    """
    try:
        from mcp_servers.letta.tenant_manager import LettaTenantConfig
    except ImportError:
        from .tenant_manager import LettaTenantConfig

    try:
        config = LettaTenantConfig(
            tenant_id=tenant_id,
            base_url=base_url.rstrip("/"),
            password=password,
            timeout=timeout,
            max_concurrency=max_concurrency,
            graphiti_url=graphiti_url.rstrip("/") if graphiti_url else None,
            org_identity_id=org_identity_id,
        )
        result = await tenant_manager.register_tenant(config)
        if result.get("success"):
            registered_config = tenant_manager.configs.get(tenant_id)
            return {
                "success": True,
                "message": "Tenant registered successfully",
                "tenant_id": tenant_id,
                "org_identity_id": registered_config.org_identity_id if registered_config else None,
            }
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool
async def lt_list_tenants(
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all registered Letta tenants.

    Returns a summary of all currently registered tenant connections, including
    their base URLs, connection status, and org identity for tenant isolation.

    Args:
        (no parameters besides ctx)

    Returns:
        dict: On success: {"success": True, "tenants": [{"tenant_id": str, "base_url": str,
              "org_identity_id": str|null, ...}], "count": int}
              On failure: {"success": False, "error": str}

    Notes:
        - org_identity_id indicates the Letta identity used for agent isolation.
          Null means no isolation is configured (all agents visible to the tenant).
        - Only shows tenants loaded in memory (from Redis + env vars at startup, plus runtime registrations).
        - Passwords are never included in the response.
    """
    try:
        tenants = []
        for tid, config in tenant_manager.configs.items():
            info = {
                "tenant_id": tid,
                "base_url": config.base_url,
                "timeout": config.timeout,
                "org_identity_id": config.org_identity_id,
            }
            if config.graphiti_url:
                info["graphiti_url"] = config.graphiti_url
            tenants.append(info)
        return {"success": True, "tenants": tenants, "count": len(tenants)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 1: Agent Management (33 operations)
# ============================================================================

@mcp.tool
async def lt_agent(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    model: Optional[str] = None,
    embedding_model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    message: Optional[str] = None,
    query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    enable_sleeptime: Optional[bool] = None,
    sleeptime_agent_frequency: Optional[int] = None,
    memory_blocks: Optional[List[Dict[str, str]]] = None,
    enable_reasoner: Optional[bool] = None,
    max_tokens: Optional[int] = None,
    thinking_budget: Optional[int] = None,
    llm: Optional[str] = None,
    embedding: Optional[str] = None,
    memoryBlocks: Optional[List[Dict[str, str]]] = None,
    thinking: Optional[int] = None,
    stream: Optional[bool] = None,
    verbose: bool = False,
    limit: int = 15,
    offset: int = 0,
    role: Optional[str] = None,
    include_system: bool = False,
    message_id: Optional[str] = None,
    identity_id: Optional[str] = None,
    archive_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    import_data: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None,
    isolated_block_labels: Optional[List[str]] = None,
    summary: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage Letta AI agents — full lifecycle including messaging, context, identity, archival, and conversations.

    Primary tool for Letta agents. Consolidates 33 operations via the 'operation' parameter.

    Args:
        tenant_id: Tenant identifier (registered via lt_register_tenant).
        operation: One of:
            CRUD: "list", "create", "get", "update", "delete", "count", "search"
            Messaging: "send_message", "send_message_async", "search_messages",
                       "edit_message", "reset_messages"
            Config: "get_config", "list_tools", "get_context", "list_groups"
            Lifecycle: "export", "import_agent", "clone", "summarize"
            Identity/Archive: "attach_identity", "detach_identity",
                              "attach_archive", "detach_archive"
            Tools: "run_agent_tool"
            Conversations: "create_conversation", "send_conversation_message",
                           "list_conversations", "get_letta_url"
        agent_id: UUID of target agent (most ops).
        name: Agent name (create, update).
        description: Agent description (create, update).
        model: LLM model (create, update). Example: "openai/gpt-4o", "anthropic/claude-sonnet-4-20250514".
        embedding_model: Embedding model (create, update).
        system_prompt: System prompt (create, update).
        message: Message text (send_message, send_message_async, edit_message).
        query: Search query (search, search_messages).
        tags: Tags list (create, update).
        enable_sleeptime: Enable sleeptime architecture (create, update). When True, memory
            management is deferred to a background "sleep-time agent", dramatically reducing
            response latency. Recommended for voice/real-time conversational systems.
        sleeptime_agent_frequency: How often the sleep-time agent runs, in number of primary
            agent steps (create). Default: 5. Lower = more frequent memory updates, higher cost.
        memory_blocks: Initial memory blocks for the agent (create). List of dicts with "label"
            and "value" keys. Example: [{"label": "human", "value": ""}, {"label": "persona",
            "value": "You are a helpful assistant."}]. Required when enable_sleeptime=True.
        enable_reasoner: Enable extended thinking/reasoning (create, update). When True, sets
            thinking budget_tokens (default 1024). When False, sets budget_tokens=1 to effectively
            disable reasoning (Letta API ignores thinking.type="disabled" on both POST and PATCH).
        max_tokens: Maximum output tokens for LLM generation (create, update).
        thinking_budget: Maximum tokens for reasoning/thinking (create, update). Controls how many
            tokens the LLM can use for internal reasoning when enable_reasoner=True. Maps to
            ``max_reasoning_tokens`` in Letta's API.
        llm: Alias for ``model`` (Letta SDK compatibility). Use either ``model`` or ``llm``.
            Accepts "letta-free" for the built-in free model.
        embedding: Alias for ``embedding_model`` (Letta SDK compatibility). Use either
            ``embedding_model`` or ``embedding``. Accepts "letta-free" for the built-in free model.
        memoryBlocks: Alias for ``memory_blocks`` (Letta SDK compatibility, camelCase).
            Same format: list of dicts with "label" and "value" keys.
        thinking: Alias for ``thinking_budget``. Use either ``thinking_budget`` or ``thinking``.
        stream: When True, send_message uses SSE streaming. Collects all streamed chunks
            and returns the complete response. Useful for long-running agent responses.
        verbose: When True, returns full untruncated data in list/search operations.
            When False (default), descriptions and content are truncated for compact responses.
        limit: Max results. Defaults to 15.
        offset: Pagination offset. Defaults to 0.
        role: Message role filter (search_messages).
        include_system: Include system messages. Defaults to False.
        message_id: Message UUID (edit_message).
        identity_id: Identity UUID (attach/detach_identity).
        archive_id: Archive UUID (attach/detach_archive).
        tool_id: Tool UUID (run_agent_tool).
        tool_args: Tool arguments dict (run_agent_tool).
        import_data: Agent export JSON data (import_agent).
        conversation_id: Conversation UUID (send_conversation_message). Created via
            create_conversation. Conversations provide per-call isolation on a shared
            agent — each conversation has independent recall memory and optionally
            isolated memory blocks, while sharing the agent's core configuration, tools,
            and non-isolated memory blocks.
        isolated_block_labels: Block labels to isolate per-conversation (create_conversation).
            When creating a conversation, blocks with these labels are COPIED for the
            conversation, creating per-conversation state. Other blocks remain shared across
            all conversations. Example: ["customer_context"] isolates customer-specific state
            while sharing "business" and "team" blocks.
        summary: Short description for a conversation (create_conversation). Example:
            "Inbound customer call from +919999000123".

    Sleeptime Architecture (for voice/real-time systems):
        When enable_sleeptime=True, Letta creates a dual-agent system:
        - Primary agent: Handles conversations with fast response times. Can read memory
          blocks but defers heavy memory writes to the background agent.
        - Sleep-time agent: Runs asynchronously every N steps (sleeptime_agent_frequency)
          to consolidate, reorganize, and persist memory. Uses memory_insert, memory_replace,
          and memory_rethink tools to maintain long-term memory without blocking responses.
        This reduces response latency from 15-45s to 3-8s for typical conversations.

    Tenant Isolation Behavior:
        When a tenant has an org identity configured (see lt_register_tenant):
        - "create": New agents are automatically attached to the tenant's org identity.
                    No manual attach_identity call needed.
        - "import_agent": Imported agents are automatically attached to the tenant's org identity.
        - "list": Only returns agents associated with this tenant's org identity.
                  Agents without an identity attachment are not visible.
        - "count": Only counts agents associated with this tenant's org identity.
        - "search": Only searches agents associated with this tenant's org identity.
        - "get", "update", "delete", "send_message", etc.: These operate by agent_id
                  and are NOT scoped. If you know an agent's UUID, you can access it
                  from any tenant. This is by design for cross-tenant admin operations.
        - "attach_identity"/"detach_identity": Use these to manually manage identity
                  associations. To migrate a pre-existing agent into a tenant's scope,
                  call attach_identity with the tenant's org_identity_id (available
                  from lt_list_tenants).
    """
    # Normalize SDK-compatible aliases to canonical parameter names
    if not model and llm:
        model = llm
    if not embedding_model and embedding:
        embedding_model = embedding
    if not memory_blocks and memoryBlocks:
        memory_blocks = memoryBlocks
    if thinking_budget is None and thinking is not None:
        thinking_budget = thinking

    try:
        if operation == "list":
            config = tenant_manager.configs.get(tenant_id)
            if config and config.org_identity_id:
                # Identity-scoped listing for tenant isolation
                result = await _api_call(
                    tenant_id, "GET",
                    f"/v1/identities/{config.org_identity_id}/agents",
                    params=_paginate_params(limit, offset)
                )
            else:
                result = await _api_call(tenant_id, "GET", "/v1/agents", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for a in agents:
                entry: Dict[str, Any] = {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "description": a.get("description") if verbose else _truncate(a.get("description"), 100),
                    "created_at": a.get("created_at"),
                    "tags": a.get("tags", []),
                }
                if verbose:
                    entry["model"] = a.get("llm_config", {}).get("model") if isinstance(a.get("llm_config"), dict) else None
                    entry["embedding_model"] = a.get("embedding_config", {}).get("model") if isinstance(a.get("embedding_config"), dict) else None
                    entry["system"] = a.get("system")
                summary.append(entry)
            return {"success": True, "agents": summary, "count": len(summary),
                    "pagination": {"limit": limit, "offset": offset}}

        elif operation == "create":
            if not name:
                return {"success": False, "error": "Parameter 'name' is required for create"}
            body: Dict[str, Any] = {"name": name}
            if description:
                body["description"] = description
            if model:
                body["model"] = model
            if embedding_model:
                body["embedding"] = embedding_model
                body["embedding_model"] = embedding_model
            elif enable_sleeptime:
                # Sleeptime requires an embedding model for memory search
                body["embedding"] = "openai/text-embedding-3-small"
            if system_prompt:
                body["system"] = system_prompt
            if tags:
                body["tags"] = tags
            if enable_sleeptime is not None:
                body["enable_sleeptime"] = enable_sleeptime
            if sleeptime_agent_frequency is not None:
                body["sleeptime_agent_frequency"] = sleeptime_agent_frequency
            if memory_blocks:
                body["memory_blocks"] = memory_blocks
            # Build model_settings for LLM configuration
            if enable_reasoner is not None or max_tokens is not None or thinking_budget is not None:
                ms: Dict[str, Any] = {}
                if model and ("anthropic" in model or "claude" in model):
                    ms["provider_type"] = "anthropic"
                else:
                    ms["provider_type"] = "openai"
                if enable_reasoner is not None:
                    if enable_reasoner:
                        ms["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget or 1024}
                    else:
                        ms["thinking"] = {"type": "enabled", "budget_tokens": 1}
                elif thinking_budget is not None:
                    ms["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                if max_tokens is not None:
                    ms["max_output_tokens"] = max_tokens
                body["model_settings"] = ms
            result = await _api_call(tenant_id, "POST", "/v1/agents", json_body=body)
            if not result["success"]:
                return result
            agent = result["data"]
            new_agent_id = agent.get("id")
            # Auto-attach tenant org identity for isolation
            warning = await _auto_attach_org_identity(tenant_id, new_agent_id)
            if warning:
                agent["_org_identity_attach_warning"] = warning
            return {"success": True, "agent": agent, "agent_id": new_agent_id}

        elif operation == "get":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}")
            if not result["success"]:
                return result
            return {"success": True, "agent": result["data"]}

        elif operation == "update":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for update"}
            body = {}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            if model:
                body["model"] = model
            if embedding_model:
                body["embedding"] = embedding_model
                body["embedding_model"] = embedding_model
            if system_prompt:
                body["system"] = system_prompt
            if tags:
                body["tags"] = tags
            if enable_sleeptime is not None:
                body["enable_sleeptime"] = enable_sleeptime
            # Build model_settings for LLM configuration changes
            if enable_reasoner is not None or max_tokens is not None or thinking_budget is not None:
                # Fetch current agent to get existing model_settings and provider
                agent_result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}")
                current_ms: Dict[str, Any] = {}
                current_lc: Dict[str, Any] = {}
                if agent_result["success"]:
                    ad = agent_result["data"]
                    current_ms = ad.get("model_settings", {}) if isinstance(ad.get("model_settings"), dict) else {}
                    current_lc = ad.get("llm_config", {}) if isinstance(ad.get("llm_config"), dict) else {}

                ms: Dict[str, Any] = {}
                # provider_type is a required discriminator — read from current settings,
                # or infer from model name (llm_config.model omits the provider/ prefix,
                # so check for "claude" not just "anthropic")
                if model and "anthropic" in model:
                    ms["provider_type"] = "anthropic"
                elif current_ms.get("provider_type"):
                    ms["provider_type"] = current_ms["provider_type"]
                elif "claude" in (current_lc.get("model") or ""):
                    ms["provider_type"] = "anthropic"
                else:
                    ms["provider_type"] = "openai"

                # Handle thinking settings
                # Letta API ignores thinking.type="disabled" on both POST and PATCH.
                # Workaround: budget_tokens=1 to effectively disable reasoning.
                if enable_reasoner is not None:
                    if enable_reasoner:
                        ms["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget or 1024}
                    else:
                        ms["thinking"] = {"type": "enabled", "budget_tokens": 1}
                elif thinking_budget is not None:
                    ms["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
                else:
                    # Preserve current thinking settings when only max_tokens changes
                    current_thinking = current_ms.get("thinking")
                    if isinstance(current_thinking, dict):
                        ms["thinking"] = current_thinking

                if max_tokens is not None:
                    ms["max_output_tokens"] = max_tokens
                else:
                    # Preserve current max_output_tokens when not explicitly changed
                    current_max = current_ms.get("max_output_tokens")
                    if current_max is not None:
                        ms["max_output_tokens"] = current_max
                body["model_settings"] = ms
            if not body:
                return {"success": False, "error": "At least one field (name, description, model, embedding_model, system_prompt, tags, enable_sleeptime, enable_reasoner, max_tokens, thinking_budget) must be provided"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "agent": result["data"]}

        elif operation == "delete":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/agents/{agent_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Agent {agent_id} deleted"}

        elif operation == "count":
            config = tenant_manager.configs.get(tenant_id)
            if config and config.org_identity_id:
                agents_all = await _api_call(
                    tenant_id, "GET",
                    f"/v1/identities/{config.org_identity_id}/agents",
                    params={"limit": 10000}
                )
            else:
                agents_all = await _api_call(tenant_id, "GET", "/v1/agents", params={"limit": 10000})
            count = len(agents_all.get("data", [])) if agents_all["success"] else 0
            return {"success": True, "count": count}

        elif operation == "search":
            config = tenant_manager.configs.get(tenant_id)
            if config and config.org_identity_id:
                # Fetch identity-scoped agents, then filter client-side
                result = await _api_call(
                    tenant_id, "GET",
                    f"/v1/identities/{config.org_identity_id}/agents",
                    params={"limit": 10000}
                )
                if not result["success"]:
                    return result
                agents = result["data"] if isinstance(result["data"], list) else []
                if query:
                    query_lower = query.lower()
                    agents = [a for a in agents if
                              query_lower in (a.get("name") or "").lower() or
                              query_lower in (a.get("description") or "").lower()]
                agents = agents[offset:offset + limit]
            else:
                params = _paginate_params(limit, offset)
                if query:
                    params["query_text"] = query
                result = await _api_call(tenant_id, "GET", "/v1/agents", params=params)
                if not result["success"]:
                    return result
                agents = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for a in agents:
                summary.append({
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "description": _truncate(a.get("description"), 100),
                    "tags": a.get("tags", []),
                })
            return {"success": True, "agents": summary, "count": len(summary),
                    "pagination": {"limit": limit, "offset": offset}}

        elif operation == "send_message":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for send_message"}
            if not message:
                return {"success": False, "error": "Parameter 'message' is required for send_message"}
            body = {"messages": [{"role": "user", "content": message}]}
            if stream:
                # Use streaming endpoint — collects SSE chunks into final response
                result = await _api_call_stream(tenant_id, f"/v1/agents/{agent_id}/messages", json_body=body)
                if not result["success"]:
                    return result
                raw = result["data"]
                return {"success": True, "messages": raw.get("messages", []),
                        "usage": raw.get("usage"), "streamed": True}
            else:
                result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/messages", json_body=body)
                if not result["success"]:
                    return result
                raw = result["data"]
                # Normalize response: Letta returns a list (non-sleeptime) or dict with "messages" key (sleeptime)
                if isinstance(raw, dict) and "messages" in raw:
                    messages = raw["messages"]
                    usage = raw.get("usage")
                elif isinstance(raw, list):
                    messages = raw
                    usage = None
                else:
                    messages = []
                    usage = None
                return {"success": True, "messages": messages, "usage": usage}

        elif operation == "search_messages":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for search_messages"}
            params = _paginate_params(limit, offset)
            if query:
                params["query"] = query
            if role:
                params["role"] = role
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/messages", params=params)
            if not result["success"]:
                return result
            messages = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for m in messages:
                entry = {
                    "id": m.get("id"),
                    "role": m.get("role"),
                    "content": (m.get("content") or m.get("text", "")) if verbose else _truncate(m.get("content") or m.get("text", ""), 1000),
                    "created_at": m.get("created_at"),
                }
                if verbose:
                    entry["tool_calls"] = m.get("tool_calls")
                    entry["tool_call_id"] = m.get("tool_call_id")
                if include_system or m.get("role") != "system":
                    summary.append(entry)
            return {"success": True, "messages": summary, "count": len(summary)}

        elif operation == "get_config":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for get_config"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}")
            if not result["success"]:
                return result
            agent = result["data"]
            llm_config = agent.get("llm_config", {}) if isinstance(agent.get("llm_config"), dict) else {}
            ms = agent.get("model_settings", {}) if isinstance(agent.get("model_settings"), dict) else {}
            thinking = ms.get("thinking", {}) if isinstance(ms.get("thinking"), dict) else {}
            config_summary = {
                "id": agent.get("id"),
                "name": agent.get("name"),
                "model": llm_config.get("model"),
                "embedding_model": agent.get("embedding_config", {}).get("model") if isinstance(agent.get("embedding_config"), dict) else None,
                "model_settings": {
                    "max_output_tokens": ms.get("max_output_tokens"),
                    "enable_reasoner": thinking.get("budget_tokens", 0) > 1,
                    "thinking": thinking if thinking else None,
                },
                "system_prompt": _truncate(agent.get("system"), 500),
                "tools": [t.get("name") if isinstance(t, dict) else t for t in agent.get("tools", [])],
                "tags": agent.get("tags", []),
            }
            return {"success": True, "config": config_summary}

        elif operation == "reset_messages":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for reset_messages"}
            body = {"add_default_initial_messages": True}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/reset-messages", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "message": f"Messages reset for agent {agent_id}"}

        elif operation == "list_tools":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for list_tools"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/tools")
            if not result["success"]:
                return result
            tools = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for t in tools:
                summary.append({
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "description": _truncate(t.get("description"), 80),
                })
            return {"success": True, "tools": summary, "count": len(summary)}

        # --- Export / Import / Clone ---
        elif operation == "export":
            if not agent_id:
                return {"success": False, "error": "agent_id required for export"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/export")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "import_agent":
            if not import_data:
                return {"success": False, "error": "import_data (agent export JSON) required for import_agent"}
            result = await _api_call(tenant_id, "POST", "/v1/agents/import", json_body=import_data)
            if not result["success"]:
                return result
            agent = result["data"]
            new_agent_id = agent.get("id")
            # Auto-attach tenant org identity for isolation
            warning = await _auto_attach_org_identity(tenant_id, new_agent_id)
            if warning:
                agent["_org_identity_attach_warning"] = warning
            return {"success": True, "agent": agent, "agent_id": new_agent_id}

        # --- Context & Summarize ---
        elif operation == "get_context":
            if not agent_id:
                return {"success": False, "error": "agent_id required for get_context"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/context")
            if not result["success"]:
                return result
            return {"success": True, "context": result["data"]}

        elif operation == "summarize":
            if not agent_id:
                return {"success": False, "error": "agent_id required for summarize"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/summarize", json_body={})
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        # --- Async Messaging ---
        elif operation == "send_message_async":
            if not agent_id or not message:
                return {"success": False, "error": "agent_id and message required for send_message_async"}
            body = {"messages": [{"role": "user", "content": message}]}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/messages/async", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "run": result["data"]}

        elif operation == "edit_message":
            if not agent_id or not message_id:
                return {"success": False, "error": "agent_id and message_id required for edit_message"}
            body = {}
            if message:
                body["content"] = message
            if role:
                body["role"] = role
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/messages/{message_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "message": result["data"]}

        # --- Identity ---
        elif operation == "attach_identity":
            if not agent_id or not identity_id:
                return {"success": False, "error": "agent_id and identity_id required for attach_identity"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/identities/attach/{identity_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Identity {identity_id} attached to agent {agent_id}"}

        elif operation == "detach_identity":
            if not agent_id or not identity_id:
                return {"success": False, "error": "agent_id and identity_id required for detach_identity"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/identities/detach/{identity_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Identity {identity_id} detached from agent {agent_id}"}

        # --- Archive ---
        elif operation == "attach_archive":
            if not agent_id or not archive_id:
                return {"success": False, "error": "agent_id and archive_id required for attach_archive"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/archives/attach/{archive_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Archive {archive_id} attached to agent {agent_id}"}

        elif operation == "detach_archive":
            if not agent_id or not archive_id:
                return {"success": False, "error": "agent_id and archive_id required for detach_archive"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/archives/detach/{archive_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Archive {archive_id} detached from agent {agent_id}"}

        # --- Agent Groups ---
        elif operation == "list_groups":
            if not agent_id:
                return {"success": False, "error": "agent_id required for list_groups"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/groups",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            groups = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": g.get("id"), "name": g.get("name")} for g in groups]
            return {"success": True, "groups": summary, "count": len(summary)}

        # --- Run Agent Tool ---
        elif operation == "run_agent_tool":
            tool_ref = tool_id or name  # Can use tool_id or tool name
            if not agent_id or not tool_ref:
                return {"success": False, "error": "agent_id and tool_id (or name) required for run_agent_tool"}
            body = {}
            if tool_args:
                body["arguments"] = tool_args
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/tools/{tool_ref}/run",
                                     json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "result": result["data"]}

        # --- Conversations (per-call isolation) ---
        elif operation == "create_conversation":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for create_conversation"}
            body: Dict[str, Any] = {}
            if isolated_block_labels:
                body["isolated_block_labels"] = isolated_block_labels
            if summary:
                body["summary"] = summary
            result = await _api_call(
                tenant_id, "POST",
                f"/v1/conversations",
                params={"agent_id": agent_id},
                json_body=body
            )
            if not result["success"]:
                return result
            conv = result["data"]
            return {"success": True, "conversation": conv}

        elif operation == "send_conversation_message":
            if not conversation_id:
                return {"success": False, "error": "Parameter 'conversation_id' is required for send_conversation_message"}
            if not message:
                return {"success": False, "error": "Parameter 'message' is required for send_conversation_message"}
            body = {
                "messages": [{"role": "user", "content": message}],
                "streaming": False,
            }
            result = await _api_call(
                tenant_id, "POST",
                f"/v1/conversations/{conversation_id}/messages",
                json_body=body
            )
            if not result["success"]:
                return result
            raw = result["data"]
            # Normalize response: match send_message format for consistent parsing
            if isinstance(raw, dict) and "messages" in raw:
                messages = raw["messages"]
                usage = raw.get("usage")
            elif isinstance(raw, list):
                messages = raw
                usage = None
            else:
                messages = []
                usage = None
            return {"success": True, "messages": messages, "usage": usage}

        elif operation == "list_conversations":
            if not agent_id:
                return {"success": False, "error": "Parameter 'agent_id' is required for list_conversations"}
            params: Dict[str, Any] = {"agent_id": agent_id, **_paginate_params(limit, offset)}
            result = await _api_call(tenant_id, "GET", "/v1/conversations", params=params)
            if not result["success"]:
                return result
            conversations = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "conversations": conversations}

        # --- Phase 2: Direct Letta URL for streaming ---
        elif operation == "get_letta_url":
            config = tenant_manager.configs.get(tenant_id)
            if not config:
                return {"success": False, "error": f"Tenant '{tenant_id}' not registered"}
            auth_header = None
            if config.password:
                auth_header = f"Bearer {config.password}"
            return {
                "success": True,
                "letta_url": config.base_url,
                "auth_token": auth_header,
            }

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, create, get, update, delete, count, search, send_message, send_message_async, search_messages, edit_message, get_config, reset_messages, list_tools, export, import_agent, get_context, summarize, attach_identity, detach_identity, attach_archive, detach_archive, list_groups, run_agent_tool, create_conversation, send_conversation_message, list_conversations, get_letta_url"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 2: Memory Management (18 operations)
# ============================================================================

@mcp.tool
async def lt_memory(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    block_id: Optional[str] = None,
    label: Optional[str] = None,
    value: Optional[str] = None,
    name: Optional[str] = None,
    text: Optional[str] = None,
    query: Optional[str] = None,
    passage_id: Optional[str] = None,
    source: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    is_template: Optional[bool] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage agent memory — core memory, memory blocks, and archival passages.

    Provides unified access to Letta's memory system. Core memory is the agent's
    working memory (persona + human blocks). Memory blocks are reusable data chunks
    that can be shared across agents. Archival passages are long-term storage entries
    searchable by semantic similarity.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The memory operation to perform. One of:
            Core Memory:
            - "get_core_memory": Get agent's core memory. Requires agent_id.
            - "update_core_memory": Update a core memory block. Requires agent_id + label + value.
            Memory Blocks:
            - "list_blocks": List memory blocks. Uses limit/offset.
            - "get_block": Get a specific block. Requires block_id.
            - "get_block_by_label": Get block by label for an agent. Requires agent_id + label.
            - "create_block": Create a new block. Requires label + value.
            - "update_block": Update a block. Requires block_id + value.
            - "attach_block": Attach a block to an agent. Requires agent_id + block_id.
            - "detach_block": Detach a block from an agent. Requires agent_id + block_id.
            Archival/Passages:
            - "search_archival": Search archival memory. Requires agent_id + query.
                Optional: start_date, end_date (ISO 8601) for date range filtering.
            - "list_passages": List archival passages. Requires agent_id. Uses limit/offset.
            - "create_passage": Create an archival passage. Requires agent_id + text.
            - "update_passage": Update a passage. Requires passage_id + text.
            - "delete_passage": Delete a passage. Requires passage_id.
            Unified Search:
            - "search_memory": Unified search across archival + messages. Requires query.
                Optional: agent_id, source ("archival"/"messages"/"both"), start_date, end_date.
            - "list_agents_using_block": List agents using a block. Requires block_id.
        agent_id: UUID of the target agent. Required for core memory and archival ops.
        block_id: UUID of a memory block. Required for get_block, update_block, attach/detach.
        label: Block label (e.g., "persona", "human", "custom_data"). Required for
               get_block_by_label, create_block, update_core_memory.
        value: The text content for the block/memory. Required for create/update ops.
        name: Optional name for a new block (create_block).
        text: Text content for archival passages (create_passage, update_passage).
        query: Search query for search_archival, search_memory.
        passage_id: UUID of an archival passage (update_passage, delete_passage).
        source: Search source for search_memory: "archival", "messages", or "both" (default).
        start_date: ISO 8601 datetime for date range filtering (search_archival, search_memory).
        end_date: ISO 8601 datetime for date range filtering (search_archival, search_memory).
        is_template: Filter blocks by template status (list_blocks).
        limit: Max results. Defaults to 15.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation. Common patterns:
            - get_core_memory: {"success": True, "memory": {...}}
            - list_blocks: {"success": True, "blocks": [...], "count": int}
            - search_archival: {"success": True, "passages": [...], "count": int}
            On failure: {"success": False, "error": str}

    Notes:
        - Core memory labels are typically "persona" and "human" by default.
        - Memory blocks can be shared across agents — changes propagate to all attached agents.
        - Archival search uses semantic similarity (embeddings), not keyword matching.
        - For temporal/episodic memory with bi-temporal validity tracking (valid_at/invalid_at),
          use lt_temporal_memory instead. Archival memory is for static long-term storage.
        - See also: lt_agent for agent operations, lt_source_manager for data ingestion,
          lt_temporal_memory for evolving facts with temporal awareness.
    """
    try:
        # --- Core Memory ---
        if operation == "get_core_memory":
            if not agent_id:
                return {"success": False, "error": "agent_id required for get_core_memory"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/core-memory")
            if not result["success"]:
                return result
            return {"success": True, "memory": result["data"]}

        elif operation == "update_core_memory":
            if not agent_id or not label or value is None:
                return {"success": False, "error": "agent_id, label, and value required for update_core_memory"}
            body = {"value": value}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/core-memory/blocks/{label}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "memory": result["data"]}

        # --- Memory Blocks ---
        elif operation == "list_blocks":
            params = _paginate_params(limit, offset)
            if is_template is not None:
                params["is_template"] = str(is_template).lower()
            result = await _api_call(tenant_id, "GET", "/v1/blocks", params=params)
            if not result["success"]:
                return result
            blocks = result["data"] if isinstance(result["data"], list) else []
            # Client-side fallback if API ignores is_template param
            if is_template is not None:
                blocks = [b for b in blocks if b.get("is_template") == is_template]
            summary = []
            for b in blocks:
                summary.append({
                    "id": b.get("id"),
                    "label": b.get("label"),
                    "name": b.get("name"),
                    "is_template": b.get("is_template"),
                    "value": _truncate(b.get("value"), 200),
                })
            return {"success": True, "blocks": summary, "count": len(summary)}

        elif operation == "get_block":
            if not block_id:
                return {"success": False, "error": "block_id required for get_block"}
            result = await _api_call(tenant_id, "GET", f"/v1/blocks/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "block": result["data"]}

        elif operation == "get_block_by_label":
            if not agent_id or not label:
                return {"success": False, "error": "agent_id and label required for get_block_by_label"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/core-memory/blocks/{label}")
            if not result["success"]:
                return result
            return {"success": True, "block": result["data"]}

        elif operation == "create_block":
            if not label or value is None:
                return {"success": False, "error": "label and value required for create_block"}
            body: Dict[str, Any] = {"label": label, "value": value}
            if name:
                body["name"] = name
            result = await _api_call(tenant_id, "POST", "/v1/blocks", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "block": result["data"]}

        elif operation == "update_block":
            if not block_id or value is None:
                return {"success": False, "error": "block_id and value required for update_block"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/blocks/{block_id}", json_body={"value": value})
            if not result["success"]:
                return result
            return {"success": True, "block": result["data"]}

        elif operation == "attach_block":
            if not agent_id or not block_id:
                return {"success": False, "error": "agent_id and block_id required for attach_block"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/core-memory/blocks/attach/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Block {block_id} attached to agent {agent_id}"}

        elif operation == "detach_block":
            if not agent_id or not block_id:
                return {"success": False, "error": "agent_id and block_id required for detach_block"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/core-memory/blocks/detach/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Block {block_id} detached from agent {agent_id}"}

        # --- Archival / Passages ---
        elif operation == "search_archival":
            if not agent_id or not query:
                return {"success": False, "error": "agent_id and query required for search_archival"}
            params = _paginate_params(limit, offset)
            params["query"] = query
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/archival-memory", params=params)
            if not result["success"]:
                return result
            passages = result["data"] if isinstance(result["data"], list) else []
            # Client-side date filtering fallback if API ignores date params
            if start_date or end_date:
                filtered = []
                for p in passages:
                    created = p.get("created_at", "")
                    if start_date and created and created < start_date:
                        continue
                    if end_date and created and created > end_date:
                        continue
                    filtered.append(p)
                passages = filtered
            summary = []
            for p in passages:
                summary.append({
                    "id": p.get("id"),
                    "text": _truncate(p.get("text"), 200),
                    "created_at": p.get("created_at"),
                })
            return {"success": True, "passages": summary, "count": len(summary)}

        elif operation == "list_passages":
            if not agent_id:
                return {"success": False, "error": "agent_id required for list_passages"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/archival-memory",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            passages = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for p in passages:
                summary.append({
                    "id": p.get("id"),
                    "text": _truncate(p.get("text"), 200),
                    "created_at": p.get("created_at"),
                })
            return {"success": True, "passages": summary, "count": len(summary)}

        elif operation == "create_passage":
            if not agent_id or not text:
                return {"success": False, "error": "agent_id and text required for create_passage"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/archival-memory", json_body={"text": text})
            if not result["success"]:
                return result
            return {"success": True, "passage": result["data"]}

        elif operation == "update_passage":
            if not passage_id or not text:
                return {"success": False, "error": "passage_id and text required for update_passage"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/passages/{passage_id}", json_body={"text": text})
            if not result["success"]:
                return result
            return {"success": True, "passage": result["data"]}

        elif operation == "delete_passage":
            if not passage_id:
                return {"success": False, "error": "passage_id required for delete_passage"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/passages/{passage_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Passage {passage_id} deleted"}

        elif operation == "delete_block":
            if not block_id:
                return {"success": False, "error": "block_id required for delete_block"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/blocks/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Block {block_id} deleted"}

        elif operation == "list_agent_blocks":
            if not agent_id:
                return {"success": False, "error": "agent_id required for list_agent_blocks"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/core-memory")
            if not result["success"]:
                return result
            memory = result["data"]
            blocks = memory.get("blocks", []) if isinstance(memory, dict) else []
            summary = []
            for b in blocks:
                summary.append({
                    "id": b.get("id"),
                    "label": b.get("label"),
                    "value": _truncate(b.get("value"), 200),
                })
            return {"success": True, "blocks": summary, "count": len(summary)}

        # --- Unified Search ---
        elif operation == "search_memory":
            if not query:
                return {"success": False, "error": "query required for search_memory"}
            search_source = source or "both"
            results: Dict[str, Any] = {"archival": [], "messages": []}

            # Search archival passages
            if search_source in ("archival", "both"):
                if agent_id:
                    params = _paginate_params(limit, offset)
                    params["query"] = query
                    if start_date:
                        params["start_date"] = start_date
                    if end_date:
                        params["end_date"] = end_date
                    r = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/archival-memory", params=params)
                else:
                    body: Dict[str, Any] = {"query_text": query, "limit": limit}
                    if start_date:
                        body["start_date"] = start_date
                    if end_date:
                        body["end_date"] = end_date
                    r = await _api_call(tenant_id, "POST", "/v1/passages/search", json_body=body)
                if r.get("success"):
                    raw = r["data"] if isinstance(r.get("data"), list) else []
                    # Client-side date filtering fallback
                    if start_date or end_date:
                        filtered = []
                        for p in raw:
                            created = p.get("created_at", "")
                            if start_date and created and created < start_date:
                                continue
                            if end_date and created and created > end_date:
                                continue
                            filtered.append(p)
                        raw = filtered
                    for p in raw:
                        results["archival"].append({
                            "id": p.get("id"),
                            "text": _truncate(p.get("text"), 200),
                            "created_at": p.get("created_at"),
                            "score": p.get("score"),
                        })

            # Search messages
            if search_source in ("messages", "both"):
                params = _paginate_params(limit, offset)
                params["query"] = query
                if agent_id:
                    params["agent_id"] = agent_id
                if start_date:
                    params["start_date"] = start_date
                if end_date:
                    params["end_date"] = end_date
                r = await _api_call(tenant_id, "GET", "/v1/messages", params=params)
                if r.get("success"):
                    msgs = r["data"] if isinstance(r.get("data"), list) else []
                    if start_date or end_date:
                        filtered = []
                        for m in msgs:
                            created = m.get("created_at", "")
                            if start_date and created and created < start_date:
                                continue
                            if end_date and created and created > end_date:
                                continue
                            filtered.append(m)
                        msgs = filtered
                    for m in msgs:
                        results["messages"].append({
                            "id": m.get("id"),
                            "role": m.get("role"),
                            "content": _truncate(m.get("content") or m.get("text", ""), 300),
                            "created_at": m.get("created_at"),
                            "agent_id": m.get("agent_id"),
                        })

            total = len(results["archival"]) + len(results["messages"])
            return {"success": True, "results": results, "total_count": total, "source": search_source}

        elif operation == "list_agents_using_block":
            if not block_id:
                return {"success": False, "error": "block_id required for list_agents_using_block"}
            result = await _api_call(tenant_id, "GET", f"/v1/blocks/{block_id}/agents",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name")} for a in agents]
            return {"success": True, "agents": summary, "count": len(summary)}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: get_core_memory, update_core_memory, list_blocks, get_block, get_block_by_label, create_block, update_block, attach_block, detach_block, delete_block, list_agent_blocks, search_archival, list_passages, create_passage, update_passage, delete_passage, search_memory, list_agents_using_block"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 3: Tool Management (13 operations)
# ============================================================================

@mcp.tool
async def lt_tool_manager(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    tool_ids: Optional[List[str]] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    source_code: Optional[str] = None,
    source_type: Optional[str] = None,
    prompt: Optional[str] = None,
    json_schema: Optional[Dict[str, Any]] = None,
    query: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage Letta tools — create, list, attach/detach tools to agents, and generate from prompts.

    Tools extend agent capabilities by allowing them to call custom functions during
    conversation. This tool manages the full tool lifecycle: CRUD, agent attachment,
    bulk operations, and AI-powered tool generation from natural language prompts.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The tool operation to perform. One of:
            - "list": List all available tools. Uses limit/offset.
            - "get": Get tool details. Requires tool_id.
            - "create": Create a new tool. Requires name + source_code.
            - "update": Update a tool. Requires tool_id; optional name, description, source_code.
            - "delete": Delete a tool. Requires tool_id.
            - "upsert": Create or update a tool by name. Requires name + source_code.
            - "attach": Attach a tool to an agent. Requires agent_id + tool_id.
            - "detach": Detach a tool from an agent. Requires agent_id + tool_id.
            - "bulk_attach": Attach multiple tools at once. Requires agent_id + tool_ids.
            - "generate_from_prompt": AI-generate a tool from a natural language prompt.
                                      Requires prompt.
            - "add_base_tools": Add all default base tools to an agent. Requires agent_id.
            - "run_from_source": Execute tool source code directly. Requires source_code.
        agent_id: UUID of target agent (attach, detach, bulk_attach, add_base_tools).
        tool_id: UUID of the tool (get, update, delete, attach, detach).
        tool_ids: List of tool UUIDs for bulk_attach.
        name: Tool name (create, upsert). Must be a valid Python function name.
        description: Tool description (create, update).
        source_code: Python source code for the tool function (create, upsert, run_from_source).
                     Must be a valid Python function definition.
        source_type: Tool source type, e.g., "python" (create). Defaults to "python".
        prompt: Natural language description for generate_from_prompt.
                Example: "A tool that fetches the current weather for a given city".
        json_schema: Optional JSON schema for the tool's input parameters.
        limit: Max results for list. Defaults to 25.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation:
            - list: {"success": True, "tools": [...], "count": int}
            - create/get/update: {"success": True, "tool": {...}}
            - attach/detach: {"success": True, "message": str}
            - generate_from_prompt: {"success": True, "tool": {...}}
            On failure: {"success": False, "error": str}

    Notes:
        - Tools must be valid Python functions with type hints and docstrings.
        - generate_from_prompt uses the Letta instance's configured LLM to generate code.
        - Attached tools become available to the agent during conversations.
        - See also: lt_agent(operation="list_tools") to see tools on a specific agent.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/tools", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            tools = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for t in tools:
                summary.append({
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "description": _truncate(t.get("description"), 80),
                    "source_type": t.get("source_type"),
                })
            return {"success": True, "tools": summary, "count": len(summary)}

        elif operation == "get":
            if not tool_id:
                return {"success": False, "error": "tool_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/tools/{tool_id}")
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "create":
            if not name or not source_code:
                return {"success": False, "error": "name and source_code required for create"}
            body: Dict[str, Any] = {"name": name, "source_code": source_code}
            if description:
                body["description"] = description
            if source_type:
                body["source_type"] = source_type
            if json_schema:
                body["json_schema"] = json_schema
            result = await _api_call(tenant_id, "POST", "/v1/tools", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "update":
            if not tool_id:
                return {"success": False, "error": "tool_id required for update"}
            body = {}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            if source_code:
                body["source_code"] = source_code
            result = await _api_call(tenant_id, "PATCH", f"/v1/tools/{tool_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "delete":
            if not tool_id:
                return {"success": False, "error": "tool_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/tools/{tool_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Tool {tool_id} deleted"}

        elif operation == "upsert":
            if not name or not source_code:
                return {"success": False, "error": "name and source_code required for upsert"}
            body: Dict[str, Any] = {"name": name, "source_code": source_code}
            if description:
                body["description"] = description
            result = await _api_call(tenant_id, "PUT", "/v1/tools", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "attach":
            if not agent_id or not tool_id:
                return {"success": False, "error": "agent_id and tool_id required for attach"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/tools/attach/{tool_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Tool {tool_id} attached to agent {agent_id}"}

        elif operation == "detach":
            if not agent_id or not tool_id:
                return {"success": False, "error": "agent_id and tool_id required for detach"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/tools/detach/{tool_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Tool {tool_id} detached from agent {agent_id}"}

        elif operation == "bulk_attach":
            if not agent_id or not tool_ids:
                return {"success": False, "error": "agent_id and tool_ids required for bulk_attach"}
            results = []
            for tid in tool_ids:
                r = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/tools/attach/{tid}")
                results.append({"tool_id": tid, "success": r["success"], "error": r.get("error")})
            return {"success": True, "results": results}

        elif operation == "generate_from_prompt":
            if not prompt:
                return {"success": False, "error": "prompt required for generate_from_prompt"}
            result = await _api_call(tenant_id, "POST", "/v1/tools/generate", json_body={"prompt": prompt})
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "add_base_tools":
            if not agent_id:
                return {"success": False, "error": "agent_id required for add_base_tools"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/tools/add-base-tools")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Base tools added to agent {agent_id}", "data": result["data"]}

        elif operation == "run_from_source":
            if not source_code:
                return {"success": False, "error": "source_code required for run_from_source"}
            result = await _api_call(tenant_id, "POST", "/v1/tools/run", json_body={"source_code": source_code})
            if not result["success"]:
                return result
            return {"success": True, "result": result["data"]}

        elif operation == "search":
            params = _paginate_params(limit, offset)
            if query:
                params["query"] = query
            if name:
                params["name"] = name
            result = await _api_call(tenant_id, "GET", "/v1/tools", params=params)
            if not result["success"]:
                return result
            tools = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": t.get("id"), "name": t.get("name"),
                        "description": _truncate(t.get("description"), 80)} for t in tools]
            return {"success": True, "tools": summary, "count": len(summary)}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, get, create, update, delete, upsert, attach, detach, bulk_attach, generate_from_prompt, add_base_tools, run_from_source, search"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 4: Source/Data Management (13 operations)
# ============================================================================

@mcp.tool
async def lt_source_manager(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    source_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    embedding_model: Optional[str] = None,
    file_path: Optional[str] = None,
    file_content: Optional[str] = None,
    file_name: Optional[str] = None,
    file_id: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage Letta data sources — create sources, upload files, and attach to agents.

    Data sources allow agents to access external knowledge. Files uploaded to a source
    are automatically chunked, embedded, and indexed for semantic search via the agent's
    archival memory. Use this to build knowledge bases for your agents.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The source operation to perform. One of:
            - "list": List all data sources. Uses limit/offset.
            - "get": Get source details. Requires source_id.
            - "create": Create a new data source. Requires name.
            - "update": Update source metadata. Requires source_id; optional name, description.
            - "delete": Delete a source and its data. Requires source_id.
            - "count": Count total data sources.
            - "attach": Attach a source to an agent. Requires agent_id + source_id.
            - "detach": Detach a source from an agent. Requires agent_id + source_id.
            - "list_attached": List sources attached to an agent. Requires agent_id.
            - "upload": Upload file content to a source. Requires source_id + file_content + file_name.
                Optional: content_type (MIME type, e.g., "application/pdf").
            - "list_files": List files in a source. Requires source_id.
            - "delete_files": Delete a file from a source. Requires source_id + file_id.
            - "list_agents_using": List agents using a source. Requires source_id.
        agent_id: UUID of target agent (attach, detach, list_attached).
        source_id: UUID of the data source.
        name: Source name (create, update). E.g., "product-docs", "faq-knowledge-base".
        description: Source description (create, update).
        embedding_model: Embedding model handle for source creation (create only).
                         Format: "provider/model-name" (e.g., "openai/text-embedding-3-small").
                         Required by Letta when creating sources. If omitted, tries server default.
        file_path: Local file path (not used in remote API — use file_content instead).
        file_content: Base64-encoded file content for upload.
        file_name: Original filename for upload (e.g., "manual.pdf", "faq.txt").
        file_id: UUID of a file (delete_files).
        content_type: MIME type for upload (e.g., "application/pdf", "text/plain").
        limit: Max results. Defaults to 15.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation:
            - list: {"success": True, "sources": [...], "count": int}
            - create/get: {"success": True, "source": {...}}
            - attach: {"success": True, "message": str}
            - upload: {"success": True, "message": str, "job": {...}}
            On failure: {"success": False, "error": str}

    Notes:
        - Uploaded files are processed asynchronously. Use lt_job_monitor to track progress.
        - Supported file types: .txt, .pdf, .md, .csv, .json (varies by Letta config).
        - Attaching a source makes its data searchable via the agent's archival memory.
        - Deleting a source removes all associated files and embeddings.
        - See also: lt_memory(operation="search_archival") to search ingested data.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/sources", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            sources = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for s in sources:
                summary.append({
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "description": _truncate(s.get("description"), 100),
                    "created_at": s.get("created_at"),
                })
            return {"success": True, "sources": summary, "count": len(summary)}

        elif operation == "get":
            if not source_id:
                return {"success": False, "error": "source_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/sources/{source_id}")
            if not result["success"]:
                return result
            return {"success": True, "source": result["data"]}

        elif operation == "create":
            if not name:
                return {"success": False, "error": "name required for create"}
            body: Dict[str, Any] = {"name": name}
            if description:
                body["description"] = description
            if embedding_model:
                body["embedding"] = embedding_model
            result = await _api_call(tenant_id, "POST", "/v1/sources", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "source": result["data"]}

        elif operation == "update":
            if not source_id:
                return {"success": False, "error": "source_id required for update"}
            body = {}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            result = await _api_call(tenant_id, "PATCH", f"/v1/sources/{source_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "source": result["data"]}

        elif operation == "delete":
            if not source_id:
                return {"success": False, "error": "source_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/sources/{source_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Source {source_id} deleted"}

        elif operation == "count":
            result = await _api_call(tenant_id, "GET", "/v1/sources", params={"limit": 10000})
            if not result["success"]:
                return result
            count = len(result["data"]) if isinstance(result["data"], list) else 0
            return {"success": True, "count": count}

        elif operation == "attach":
            if not agent_id or not source_id:
                return {"success": False, "error": "agent_id and source_id required for attach"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/sources/attach/{source_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Source {source_id} attached to agent {agent_id}"}

        elif operation == "detach":
            if not agent_id or not source_id:
                return {"success": False, "error": "agent_id and source_id required for detach"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/sources/detach/{source_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Source {source_id} detached from agent {agent_id}"}

        elif operation == "list_attached":
            if not agent_id:
                return {"success": False, "error": "agent_id required for list_attached"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/sources")
            if not result["success"]:
                return result
            sources = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for s in sources:
                summary.append({
                    "id": s.get("id"),
                    "name": s.get("name"),
                    "description": _truncate(s.get("description"), 100),
                })
            return {"success": True, "sources": summary, "count": len(summary)}

        elif operation == "upload":
            if not source_id or not file_content or not file_name:
                return {"success": False, "error": "source_id, file_content, and file_name required for upload"}
            # Upload via multipart form
            info = await tenant_manager.get_client(tenant_id)
            client = info["client"]
            semaphore = info["semaphore"]
            import base64
            try:
                raw_bytes = base64.b64decode(file_content)
            except Exception:
                raw_bytes = file_content.encode("utf-8")

            async with semaphore:
                try:
                    file_tuple = (file_name, raw_bytes, content_type) if content_type else (file_name, raw_bytes)
                    resp = await client.post(
                        f"/v1/sources/{source_id}/upload",
                        files={"file": file_tuple},
                    )
                    if resp.status_code >= 400:
                        return {"success": False, "error": f"Upload failed: {resp.status_code} {resp.text[:300]}"}
                    return {"success": True, "message": f"File '{file_name}' uploaded to source {source_id}", "data": resp.json()}
                except Exception as e:
                    return {"success": False, "error": f"Upload error: {str(e)}"}

        elif operation == "list_files":
            if not source_id:
                return {"success": False, "error": "source_id required for list_files"}
            result = await _api_call(tenant_id, "GET", f"/v1/sources/{source_id}/files",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            files = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "files": files, "count": len(files)}

        elif operation == "delete_files":
            if not source_id or not file_id:
                return {"success": False, "error": "source_id and file_id required for delete_files"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/sources/{source_id}/files/{file_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"File {file_id} deleted from source {source_id}"}

        elif operation == "list_agents_using":
            if not source_id:
                return {"success": False, "error": "source_id required for list_agents_using"}
            result = await _api_call(tenant_id, "GET", f"/v1/sources/{source_id}/agents",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name")} for a in agents]
            return {"success": True, "agents": summary, "count": len(summary)}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, get, create, update, delete, count, attach, detach, list_attached, upload, list_files, delete_files, list_agents_using"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 5: Job Monitor (4 operations)
# ============================================================================

@mcp.tool
async def lt_job_monitor(
    tenant_id: str,
    operation: str,
    job_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Monitor and manage Letta background jobs.

    Letta runs certain operations asynchronously (file uploads, data source processing,
    agent cloning, etc.). Use this tool to check on job status, list active jobs, or
    cancel running jobs.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The job operation to perform. One of:
            - "list": List all jobs with pagination. Uses limit/offset.
            - "get": Get details of a specific job. Requires job_id.
            - "cancel": Cancel a running job. Requires job_id.
            - "list_active": List only currently active/running jobs.
        job_id: UUID of the job (get, cancel).
        limit: Max results. Defaults to 20.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation:
            - list/list_active: {"success": True, "jobs": [...], "count": int}
            - get: {"success": True, "job": {...}}
            - cancel: {"success": True, "message": str}
            On failure: {"success": False, "error": str}

    Notes:
        - Job statuses: "pending", "running", "completed", "failed", "cancelled".
        - File upload jobs may take minutes for large documents.
        - Cancelled jobs cannot be resumed.
        - See also: lt_source_manager(operation="upload") which creates upload jobs.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/jobs", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            jobs = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for j in jobs:
                summary.append({
                    "id": j.get("id"),
                    "status": j.get("status"),
                    "type": j.get("type") or j.get("job_type"),
                    "created_at": j.get("created_at"),
                    "completed_at": j.get("completed_at"),
                })
            return {"success": True, "jobs": summary, "count": len(summary)}

        elif operation == "get":
            if not job_id:
                return {"success": False, "error": "job_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/jobs/{job_id}")
            if not result["success"]:
                return result
            return {"success": True, "job": result["data"]}

        elif operation == "cancel":
            if not job_id:
                return {"success": False, "error": "job_id required for cancel"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/jobs/{job_id}/cancel")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Job {job_id} cancelled"}

        elif operation == "list_active":
            result = await _api_call(tenant_id, "GET", "/v1/jobs/active", params=_paginate_params(limit, offset))
            if not result["success"]:
                # Fallback: filter from full list
                all_result = await _api_call(tenant_id, "GET", "/v1/jobs", params={"limit": 100})
                if not all_result["success"]:
                    return all_result
                jobs = all_result["data"] if isinstance(all_result["data"], list) else []
                active = [j for j in jobs if j.get("status") in ("pending", "running")]
                summary = [{"id": j.get("id"), "status": j.get("status"),
                            "type": j.get("type") or j.get("job_type")} for j in active]
                return {"success": True, "jobs": summary, "count": len(summary)}
            jobs = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": j.get("id"), "status": j.get("status"),
                        "type": j.get("type") or j.get("job_type")} for j in jobs]
            return {"success": True, "jobs": summary, "count": len(summary)}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, get, cancel, list_active"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 6: File & Folder Operations (8 operations)
# ============================================================================

@mcp.tool
async def lt_file_folder_ops(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    file_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    folder_path: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage Letta file sessions and folder organization.

    Provides file session management (open/close files for agent context) and folder
    operations (organize agents into folders). File sessions control which files an
    agent can actively reference during conversations.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The file/folder operation to perform. One of:
            File Sessions:
            - "list_files": List open file sessions for an agent. Requires agent_id.
            - "open_file": Open a file for an agent's context. Requires agent_id + file_id.
            - "close_file": Close a file session. Requires agent_id + file_id.
            - "close_all_files": Close all open file sessions. Requires agent_id.
            Folders:
            - "list_folders": List all folders.
            - "attach_folder": Assign an agent to a folder. Requires agent_id + folder_id.
            - "detach_folder": Remove an agent from a folder. Requires agent_id + folder_id.
            - "list_agents_in_folder": List agents in a folder. Requires folder_id.
        agent_id: UUID of target agent (file ops, folder attach/detach).
        file_id: UUID of the file (open_file, close_file).
        folder_id: UUID of the folder (attach/detach/list_agents).
        folder_path: Optional folder path identifier.
        limit: Max results. Defaults to 20.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation:
            - list_files: {"success": True, "files": [...], "count": int}
            - list_folders: {"success": True, "folders": [...], "count": int}
            - open_file/close_file: {"success": True, "message": str}
            On failure: {"success": False, "error": str}

    Notes:
        - File sessions are transient — they reset when the agent restarts.
        - Folders are purely organizational; they don't affect agent capabilities.
        - See also: lt_source_manager for permanent data source management.
    """
    try:
        # --- File Sessions ---
        if operation == "list_files":
            if not agent_id:
                return {"success": False, "error": "agent_id required for list_files"}
            result = await _api_call(tenant_id, "GET", f"/v1/agents/{agent_id}/files",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            files = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "files": files, "count": len(files)}

        elif operation == "open_file":
            if not agent_id or not file_id:
                return {"success": False, "error": "agent_id and file_id required for open_file"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/files/{file_id}/open")
            if not result["success"]:
                return result
            return {"success": True, "message": f"File {file_id} opened for agent {agent_id}"}

        elif operation == "close_file":
            if not agent_id or not file_id:
                return {"success": False, "error": "agent_id and file_id required for close_file"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/files/{file_id}/close")
            if not result["success"]:
                return result
            return {"success": True, "message": f"File {file_id} closed for agent {agent_id}"}

        elif operation == "close_all_files":
            if not agent_id:
                return {"success": False, "error": "agent_id required for close_all_files"}
            result = await _api_call(tenant_id, "POST", f"/v1/agents/{agent_id}/files/close-all")
            if not result["success"]:
                return result
            return {"success": True, "message": f"All files closed for agent {agent_id}"}

        # --- Folders ---
        elif operation == "list_folders":
            result = await _api_call(tenant_id, "GET", "/v1/folders", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            folders = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "folders": folders, "count": len(folders)}

        elif operation == "attach_folder":
            if not agent_id or not folder_id:
                return {"success": False, "error": "agent_id and folder_id required for attach_folder"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/folders/{folder_id}/attach")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Agent {agent_id} added to folder {folder_id}"}

        elif operation == "detach_folder":
            if not agent_id or not folder_id:
                return {"success": False, "error": "agent_id and folder_id required for detach_folder"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/agents/{agent_id}/folders/{folder_id}/detach")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Agent {agent_id} removed from folder {folder_id}"}

        elif operation == "list_agents_in_folder":
            if not folder_id:
                return {"success": False, "error": "folder_id required for list_agents_in_folder"}
            result = await _api_call(tenant_id, "GET", f"/v1/folders/{folder_id}/agents",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name")} for a in agents]
            return {"success": True, "agents": summary, "count": len(summary)}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list_files, open_file, close_file, close_all_files, list_folders, attach_folder, detach_folder, list_agents_in_folder"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 7: MCP Operations (11 operations)
# ============================================================================

@mcp.tool
async def lt_mcp_ops(
    tenant_id: str,
    operation: str,
    agent_id: Optional[str] = None,
    server_url: Optional[str] = None,
    server_name: Optional[str] = None,
    server_id: Optional[str] = None,
    server_config: Optional[Dict[str, Any]] = None,
    oauth_config: Optional[Dict[str, Any]] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[Dict[str, Any]] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage MCP server integrations within Letta — connect external MCP servers to agents.

    Letta supports connecting to external MCP servers to extend agent capabilities.
    This tool manages the full MCP integration lifecycle: adding servers, discovering
    their tools, registering tools with Letta, and attaching them to agents.

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant first.
        operation: The MCP operation to perform. One of:
            Server Management:
            - "list_servers": List all configured MCP servers.
            - "add": Add a new MCP server. Requires server_name + (server_url or server_config).
                Optional: oauth_config for authenticated servers.
            - "update": Update MCP server config. Requires server_id; optional server_url, server_name,
                server_config, oauth_config.
            - "delete": Remove an MCP server. Requires server_id.
            - "test": Test connectivity to an MCP server. Requires server_id.
            - "connect": Connect/reconnect to an MCP server. Requires server_id.
            - "resync": Re-discover tools from an MCP server. Requires server_id.
            Tool Operations:
            - "list_tools": List tools available from MCP servers.
            - "register_tool": Register a discovered MCP tool with Letta. Requires tool_name + server_id.
            - "execute": Execute an MCP tool directly. Requires tool_name + server_id; optional tool_args.
            One-Step Integration:
            - "attach_mcp_server": Discover, register, and attach all tools from an MCP server
                                    to an agent in one step. Requires agent_id + server_id.
        agent_id: UUID of agent for attach_mcp_server.
        server_url: MCP server URL (add, update). E.g., "https://mcp.example.com/mcp".
                    For simple URL-based servers. Use server_config for advanced transport config.
        server_name: Display name for the MCP server (add, update).
        server_id: UUID of a configured MCP server (update, delete, test, connect, resync,
                   register_tool, execute, attach_mcp_server).
        server_config: Advanced transport configuration dict (add, update). Supports SSE, Stdio,
                       StreamableHttp. E.g., {"type": "sse", "url": "https://..."} or
                       {"type": "stdio", "command": "npx", "args": ["-y", "server-name"]}.
                       Takes precedence over server_url if both provided.
        oauth_config: OAuth configuration for authenticated MCP servers (add, update).
                      E.g., {"client_id": "...", "client_secret": "...", "auth_url": "...",
                      "token_url": "...", "scope": "..."}.
        tool_name: Name of an MCP tool (register_tool, execute).
        tool_args: Arguments to pass when executing a tool (execute).
                   JSON object matching the tool's input schema.
        limit: Max results. Defaults to 20.
        offset: Pagination offset. Defaults to 0.

    Returns:
        dict: Varies by operation:
            - list_servers: {"success": True, "servers": [...], "count": int}
            - add: {"success": True, "server": {...}}
            - test: {"success": True, "status": "connected"|"failed"}
            - list_tools: {"success": True, "tools": [...]}
            - execute: {"success": True, "result": {...}}
            - attach_mcp_server: {"success": True, "message": str, "tools_attached": int}
            On failure: {"success": False, "error": str}

    Notes:
        - MCP servers must be accessible from the Letta instance's network.
        - attach_mcp_server is the easiest way to integrate — it does discovery + registration + attachment.
        - Resyncing updates the tool list if the remote MCP server has been updated.
        - See also: lt_tool_manager for managing tools once registered.
    """
    try:
        if operation == "list_servers":
            result = await _api_call(tenant_id, "GET", "/v1/mcp-servers", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            servers = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "servers": servers, "count": len(servers)}

        elif operation == "add":
            if not server_name:
                return {"success": False, "error": "server_name required for add"}
            if not server_config and not server_url:
                return {"success": False, "error": "server_url or server_config required for add"}
            body: Dict[str, Any] = {"name": server_name}
            if server_config:
                body["server_config"] = server_config
            elif server_url:
                body["url"] = server_url
            if oauth_config:
                body["oauth_config"] = oauth_config
            result = await _api_call(tenant_id, "POST", "/v1/mcp-servers", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "server": result["data"]}

        elif operation == "update":
            if not server_id:
                return {"success": False, "error": "server_id required for update"}
            body: Dict[str, Any] = {}
            if server_url:
                body["url"] = server_url
            if server_name:
                body["name"] = server_name
            if server_config:
                body["server_config"] = server_config
            if oauth_config:
                body["oauth_config"] = oauth_config
            result = await _api_call(tenant_id, "PATCH", f"/v1/mcp-servers/{server_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "server": result["data"]}

        elif operation == "delete":
            if not server_id:
                return {"success": False, "error": "server_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/mcp-servers/{server_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"MCP server {server_id} deleted"}

        elif operation == "test":
            if not server_id:
                return {"success": False, "error": "server_id required for test"}
            result = await _api_call(tenant_id, "POST", f"/v1/mcp-servers/{server_id}/test")
            if not result["success"]:
                return result
            return {"success": True, "status": "connected", "data": result["data"]}

        elif operation == "connect":
            if not server_id:
                return {"success": False, "error": "server_id required for connect"}
            result = await _api_call(tenant_id, "GET", f"/v1/mcp-servers/connect/{server_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Connected to MCP server {server_id}", "data": result["data"]}

        elif operation == "resync":
            if not server_id:
                return {"success": False, "error": "server_id required for resync"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/mcp-servers/{server_id}/refresh")
            if not result["success"]:
                return result
            return {"success": True, "message": f"MCP server {server_id} resynced", "data": result["data"]}

        elif operation == "list_tools":
            if server_id:
                result = await _api_call(tenant_id, "GET", f"/v1/mcp-servers/{server_id}/tools",
                                         params=_paginate_params(limit, offset))
                if not result["success"]:
                    return result
                tools = result["data"] if isinstance(result["data"], list) else []
            else:
                # List tools from all MCP servers
                servers_result = await _api_call(tenant_id, "GET", "/v1/mcp-servers",
                                                  params=_paginate_params(limit, offset))
                tools = []
                if servers_result["success"]:
                    servers = servers_result["data"] if isinstance(servers_result["data"], list) else []
                    for srv in servers:
                        sid = srv.get("id")
                        if sid:
                            tr = await _api_call(tenant_id, "GET", f"/v1/mcp-servers/{sid}/tools")
                            if tr["success"]:
                                srv_tools = tr["data"] if isinstance(tr["data"], list) else []
                                for t in srv_tools:
                                    t["server_id"] = sid
                                    t["server_name"] = srv.get("name")
                                tools.extend(srv_tools)
                else:
                    return servers_result
            summary = [{"name": t.get("name"), "description": _truncate(t.get("description"), 80),
                        "server_id": t.get("server_id")} for t in tools]
            return {"success": True, "tools": summary, "count": len(summary)}

        elif operation == "register_tool":
            if not tool_name or not server_id:
                return {"success": False, "error": "tool_name and server_id required for register_tool"}
            result = await _api_call(tenant_id, "POST", f"/v1/mcp-servers/{server_id}/tools/register",
                                     json_body={"tool_name": tool_name})
            if not result["success"]:
                return result
            return {"success": True, "tool": result["data"]}

        elif operation == "execute":
            if not tool_name or not server_id:
                return {"success": False, "error": "tool_name and server_id required for execute"}
            body: Dict[str, Any] = {"tool_name": tool_name}
            if tool_args:
                body["arguments"] = tool_args
            result = await _api_call(tenant_id, "POST", f"/v1/mcp-servers/{server_id}/tools/execute",
                                     json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "result": result["data"]}

        elif operation == "attach_mcp_server":
            if not agent_id or not server_id:
                return {"success": False, "error": "agent_id and server_id required for attach_mcp_server"}
            result = await _api_call(tenant_id, "POST",
                                     f"/v1/agents/{agent_id}/mcp/servers/{server_id}/attach")
            if not result["success"]:
                return result
            data = result["data"]
            tools_count = len(data) if isinstance(data, list) else 0
            return {"success": True, "message": f"MCP server attached to agent {agent_id}",
                    "tools_attached": tools_count, "data": data}

        elif operation == "get":
            if not server_id:
                return {"success": False, "error": "server_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/mcp-servers/{server_id}")
            if not result["success"]:
                return result
            return {"success": True, "server": result["data"]}

        elif operation == "refresh":
            if not server_id:
                return {"success": False, "error": "server_id required for refresh"}
            result = await _api_call(tenant_id, "POST", f"/v1/mcp-servers/{server_id}/refresh")
            if not result["success"]:
                return result
            return {"success": True, "message": f"MCP server {server_id} refreshed", "data": result["data"]}

        elif operation == "get_tool":
            if not server_id or not tool_name:
                return {"success": False, "error": "server_id and tool_name required for get_tool"}
            result = await _api_call(tenant_id, "GET", f"/v1/mcp-servers/{server_id}/tools")
            if not result["success"]:
                return result
            tools = result["data"] if isinstance(result["data"], list) else []
            matched = [t for t in tools if t.get("name") == tool_name]
            if not matched:
                return {"success": False, "error": f"Tool '{tool_name}' not found on server {server_id}"}
            return {"success": True, "tool": matched[0]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list_servers, add, update, delete, test, connect, resync, list_tools, register_tool, execute, attach_mcp_server, get, refresh, get_tool"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 8: Temporal Memory (Graphiti) — 5 operations
# ============================================================================

@mcp.tool
async def lt_temporal_memory(
    tenant_id: str,
    operation: str,
    group_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    text: Optional[str] = None,
    query: Optional[str] = None,
    source: str = "conversation",
    source_description: Optional[str] = None,
    timestamp: Optional[str] = None,
    point_in_time: Optional[str] = None,
    max_results: int = 10,
    limit: int = 50,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage bi-temporal knowledge graph memory via Graphiti + FalkorDB.

    Provides temporal memory capabilities for Letta agents, powered by the Graphiti
    service. Unlike archival memory (lt_memory), temporal memory tracks *when* facts
    were valid and automatically detects/resolves contradictions over time. It uses
    entity extraction, deduplication, and bi-temporal timestamps (valid_at / invalid_at)
    so you can query what was true at any point in history.

    Architecture: MCP → Graphiti Service (HTTP) → graphiti-core → FalkorDB

    Args:
        tenant_id: Identifier for the tenant whose Letta instance to use.
                   Must be registered via lt_register_tenant with a graphiti_url.
        operation: The temporal memory operation to perform. One of:
            - "ingest": Ingest a conversation episode into the knowledge graph.
                        Graphiti extracts entities/relationships, resolves duplicates,
                        and detects temporal conflicts automatically.
                        Requires group_id + text. Optional: source, source_description, timestamp.
            - "search": Search the knowledge graph using hybrid retrieval (semantic +
                        keyword + graph traversal). Returns facts with temporal validity.
                        Requires group_id + query. Optional: max_results.
            - "query_at": Query facts that were valid at a specific point in time.
                          Returns only facts where valid_at <= point_in_time and
                          (invalid_at is null OR invalid_at > point_in_time).
                          Requires group_id + query + point_in_time. Optional: max_results.
            - "list_entities": List all entity nodes for a group. Useful for exploring
                               what the graph knows about a tenant/agent.
                               Requires group_id. Optional: limit.
            - "health": Check Graphiti service health and FalkorDB connectivity.
                        No required parameters.
        group_id: Isolation key for multi-tenancy within the graph. Typically the agent_id
                  or a tenant-specific prefix. IMPORTANT: Must be alphanumeric with
                  underscores only — NO HYPHENS (FalkorDB RediSearch limitation).
                  Example: "agent_abc123", "tenant_prod_agent1".
                  If omitted but agent_id is provided, defaults to agent_id with hyphens
                  replaced by underscores.
        agent_id: Optional Letta agent UUID. If group_id is not provided, this is used
                  to derive group_id (hyphens stripped and replaced with underscores).
        text: The conversation text or data to ingest (ingest operation).
              Can be a full conversation transcript, a single message, or structured data.
              Example: "User said their favorite color is blue. Previously it was red."
        query: Natural language search query (search, query_at operations).
               Example: "What is the user's favorite color?"
        source: Episode source type for ingest. Defaults to "conversation".
        source_description: Human-readable description of the data source for ingest.
                            Example: "WhatsApp chat with user Raj on 2026-01-15".
        timestamp: ISO 8601 timestamp of when the episode occurred (ingest operation).
                   Defaults to current time if not provided.
                   Example: "2026-01-15T10:30:00Z".
        point_in_time: ISO 8601 timestamp for point-in-time queries (query_at operation).
                       Example: "2026-01-01T00:00:00Z" to see facts as of Jan 1, 2026.
        max_results: Maximum number of results to return (search, query_at). Defaults to 10.
        limit: Maximum entities to return (list_entities). Defaults to 50.

    Returns:
        dict: Varies by operation:
            - ingest: {"success": True, "data": {"status": "ok", "episode_id": str,
                       "entities_extracted": int, "relations_extracted": int}}
            - search: {"success": True, "data": {"results": [{"fact": str,
                       "valid_from": str|null, "invalid_at": str|null, "score": float}], "total": int}}
            - query_at: Same as search, but filtered to facts valid at the given point_in_time.
            - list_entities: {"success": True, "data": {"entities": [{"name": str,
                             "summary": str, "uuid": str}], "total": int}}
            - health: {"success": True, "data": {"status": "ok", "falkordb": str}}
            On failure: {"success": False, "error": str}

    Notes:
        - Requires graphiti_url to be set when registering the tenant via lt_register_tenant.
        - group_id must NOT contain hyphens — FalkorDB RediSearch treats them as operators.
          Use underscores or alphanumeric characters only.
        - Temporal memory complements Letta's built-in archival memory (lt_memory):
          use archival for static long-term storage, temporal for evolving facts.
        - Ingest is asynchronous in nature — entity extraction uses LLM calls and may
          take a few seconds per episode.
        - See also: lt_memory for core/archival memory, lt_agent for agent operations.
    """
    # Resolve group_id from agent_id if not provided
    if not group_id and agent_id:
        group_id = agent_id.replace("-", "_")

    try:
        if operation == "health":
            result = await _graphiti_call(tenant_id, "GET", "/health")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "ingest":
            if not group_id or not text:
                return {"success": False, "error": "group_id (or agent_id) and text are required for ingest"}
            body: Dict[str, Any] = {
                "group_id": group_id,
                "text": text,
                "source": source,
            }
            if source_description:
                body["source_description"] = source_description
            if timestamp:
                body["timestamp"] = timestamp
            result = await _graphiti_call(tenant_id, "POST", "/ingest", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "search":
            if not group_id or not query:
                return {"success": False, "error": "group_id (or agent_id) and query are required for search"}
            body = {
                "group_id": group_id,
                "query": query,
                "max_results": max_results,
            }
            result = await _graphiti_call(tenant_id, "POST", "/search", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "query_at":
            if not group_id or not query or not point_in_time:
                return {"success": False, "error": "group_id (or agent_id), query, and point_in_time are required for query_at"}
            body = {
                "group_id": group_id,
                "query": query,
                "point_in_time": point_in_time,
                "max_results": max_results,
            }
            result = await _graphiti_call(tenant_id, "POST", "/query-at", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "list_entities":
            if not group_id:
                return {"success": False, "error": "group_id (or agent_id) is required for list_entities"}
            result = await _graphiti_call(tenant_id, "GET", f"/entities/{group_id}", params={"limit": limit})
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: ingest, search, query_at, list_entities, health"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 9: Conversation Management (10 operations)
# ============================================================================

@mcp.tool
async def lt_conversation(
    tenant_id: str,
    operation: str,
    group_id: Optional[str] = None,
    message: Optional[str] = None,
    message_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    agent_ids: Optional[List[str]] = None,
    role: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage multi-agent group conversations — send messages, list history, compact.

    Group conversations allow multiple agents to collaborate on messages. Messages
    are routed through the group and processed by member agents in sequence.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            - "list_messages": List messages in a group conversation. Requires group_id.
            - "send_message": Send a message to the group. Requires group_id + message.
            - "edit_message": Edit a message. Requires group_id + message_id + message.
            - "reset_messages": Clear group message history. Requires group_id.
            - "compact": Compact/summarize group conversation history. Requires group_id.
        group_id: UUID of the group.
        message: Message text (send_message, edit_message).
        message_id: UUID of message to edit (edit_message).
        name: Group name (unused here — see lt_group for group CRUD).
        description: Group description.
        agent_ids: List of agent UUIDs.
        role: Message role filter.
        limit: Max results. Defaults to 15.
        offset: Pagination offset.

    Notes:
        - KNOWN ISSUE (Letta v0.16.4): send_message and list_messages return 500 errors
          due to a server-side bug in groups.py (ascending kwarg mismatch). This will be
          fixed in Letta v0.17+. For single-agent messaging, use lt_agent(operation="send_message")
          as a workaround.
        - For single-agent messaging (not multi-agent groups), use lt_agent(operation="send_message").
    """
    try:
        if operation == "list_messages":
            if not group_id:
                return {"success": False, "error": "group_id required for list_messages"}
            params = _paginate_params(limit, offset)
            if role:
                params["role"] = role
            result = await _api_call(tenant_id, "GET", f"/v1/groups/{group_id}/messages", params=params)
            if not result["success"]:
                return result
            messages = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for m in messages:
                summary.append({
                    "id": m.get("id"),
                    "role": m.get("role"),
                    "content": _truncate(m.get("content") or m.get("text", ""), 500),
                    "agent_id": m.get("agent_id"),
                    "created_at": m.get("created_at"),
                })
            return {"success": True, "messages": summary, "count": len(summary)}

        elif operation == "send_message":
            if not group_id or not message:
                return {"success": False, "error": "group_id and message required for send_message"}
            body = {"messages": [{"role": "user", "content": message}]}
            result = await _api_call(tenant_id, "POST", f"/v1/groups/{group_id}/messages", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "response": result["data"]}

        elif operation == "send_message_async":
            if not group_id or not message:
                return {"success": False, "error": "group_id and message required for send_message_async"}
            body = {"messages": [{"role": "user", "content": message}]}
            result = await _api_call(tenant_id, "POST", f"/v1/groups/{group_id}/messages/async", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "run": result["data"]}

        elif operation == "edit_message":
            if not group_id or not message_id:
                return {"success": False, "error": "group_id and message_id required for edit_message"}
            body: Dict[str, Any] = {}
            if message:
                body["content"] = message
            if role:
                body["role"] = role
            result = await _api_call(tenant_id, "PATCH", f"/v1/groups/{group_id}/messages/{message_id}",
                                     json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "message": result["data"]}

        elif operation == "reset_messages":
            if not group_id:
                return {"success": False, "error": "group_id required for reset_messages"}
            body = {"add_default_initial_messages": True}
            result = await _api_call(tenant_id, "PATCH", f"/v1/groups/{group_id}/reset-messages", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "message": f"Messages reset for group {group_id}"}

        elif operation == "compact":
            if not group_id:
                return {"success": False, "error": "group_id required for compact"}
            result = await _api_call(tenant_id, "POST", f"/v1/groups/{group_id}/compact")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list_messages, send_message, send_message_async, edit_message, reset_messages, compact"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 10: Group Management (12 operations)
# ============================================================================

@mcp.tool
async def lt_group(
    tenant_id: str,
    operation: str,
    group_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    agent_ids: Optional[List[str]] = None,
    block_id: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage agent groups — CRUD, member management, shared memory blocks.

    Groups organize agents for multi-agent conversations. Agents in a group
    share context and can collaborate on tasks.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            CRUD: "list", "create", "get", "update", "delete", "count"
            Membership: "add_agents", "remove_agents"
            Memory: "attach_block", "detach_block"
            Search: "search"
        group_id: UUID of the group.
        name: Group name (create, update, search).
        description: Group description (create, update).
        agent_ids: List of agent UUIDs (create, add_agents, remove_agents).
        block_id: Memory block UUID (attach_block, detach_block).
        query: Search query (search).
        limit: Max results. Defaults to 15.
        offset: Pagination offset.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/groups", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            groups = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": g.get("id"), "name": g.get("name"),
                        "description": _truncate(g.get("description"), 100),
                        "agent_ids": g.get("agent_ids", [])} for g in groups]
            return {"success": True, "groups": summary, "count": len(summary)}

        elif operation == "create":
            if not name:
                return {"success": False, "error": "name required for create"}
            body: Dict[str, Any] = {"name": name, "description": description or ""}
            if agent_ids:
                body["agent_ids"] = agent_ids
            result = await _api_call(tenant_id, "POST", "/v1/groups", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "group": result["data"], "group_id": result["data"].get("id")}

        elif operation == "get":
            if not group_id:
                return {"success": False, "error": "group_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/groups/{group_id}")
            if not result["success"]:
                return result
            return {"success": True, "group": result["data"]}

        elif operation == "update":
            if not group_id:
                return {"success": False, "error": "group_id required for update"}
            body = {}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            if agent_ids:
                body["agent_ids"] = agent_ids
            result = await _api_call(tenant_id, "PATCH", f"/v1/groups/{group_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "group": result["data"]}

        elif operation == "delete":
            if not group_id:
                return {"success": False, "error": "group_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/groups/{group_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Group {group_id} deleted"}

        elif operation == "count":
            result = await _api_call(tenant_id, "GET", "/v1/groups/count")
            if not result["success"]:
                return result
            return {"success": True, "count": result["data"]}

        elif operation == "search":
            params = _paginate_params(limit, offset)
            if query:
                params["query_text"] = query
            if name:
                params["name"] = name
            result = await _api_call(tenant_id, "GET", "/v1/groups", params=params)
            if not result["success"]:
                return result
            groups = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": g.get("id"), "name": g.get("name"),
                        "description": _truncate(g.get("description"), 100)} for g in groups]
            return {"success": True, "groups": summary, "count": len(summary)}

        elif operation == "add_agents":
            if not group_id or not agent_ids:
                return {"success": False, "error": "group_id and agent_ids required for add_agents"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/groups/{group_id}",
                                     json_body={"agent_ids": agent_ids})
            if not result["success"]:
                return result
            return {"success": True, "group": result["data"]}

        elif operation == "remove_agents":
            if not group_id:
                return {"success": False, "error": "group_id required for remove_agents"}
            # Get current group, remove specified agents
            get_result = await _api_call(tenant_id, "GET", f"/v1/groups/{group_id}")
            if not get_result["success"]:
                return get_result
            current = get_result["data"]
            current_ids = current.get("agent_ids", [])
            remove_set = set(agent_ids or [])
            new_ids = [a for a in current_ids if a not in remove_set]
            result = await _api_call(tenant_id, "PATCH", f"/v1/groups/{group_id}",
                                     json_body={"agent_ids": new_ids})
            if not result["success"]:
                return result
            return {"success": True, "group": result["data"]}

        elif operation == "attach_block":
            if not group_id or not block_id:
                return {"success": False, "error": "group_id and block_id required for attach_block"}
            result = await _api_call(tenant_id, "PATCH",
                                     f"/v1/groups/{group_id}/blocks/attach/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Block {block_id} attached to group {group_id}"}

        elif operation == "detach_block":
            if not group_id or not block_id:
                return {"success": False, "error": "group_id and block_id required for detach_block"}
            result = await _api_call(tenant_id, "PATCH",
                                     f"/v1/groups/{group_id}/blocks/detach/{block_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Block {block_id} detached from group {group_id}"}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, create, get, update, delete, count, search, add_agents, remove_agents, attach_block, detach_block"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 11: Identity Management (10 operations)
# ============================================================================

@mcp.tool
async def lt_identity(
    tenant_id: str,
    operation: str,
    identity_id: Optional[str] = None,
    name: Optional[str] = None,
    identifier: Optional[str] = None,
    identity_type: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
    query: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage identities — user/entity profiles that agents can be associated with.

    Identities represent users, organizations, or entities that interact with agents.
    They provide the foundation for tenant isolation: each MCP tenant automatically
    gets an org-level identity (created during lt_register_tenant). Agents are scoped
    to tenants through these identity associations.

    Use this tool to:
    - Create additional user-level identities within a tenant for per-user personalization
    - List agents belonging to a specific identity (e.g., for auditing tenant boundaries)
    - Manage identity properties (user preferences, metadata)

    Note: The tenant's org identity is managed automatically — you only need this tool
    for creating additional user/customer identities within a tenant, or for advanced
    identity management (auditing, migration, property updates).

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            CRUD: "list", "create", "upsert", "get", "update", "delete", "count"
            Relations: "list_agents", "list_blocks"
            Properties: "set_properties"
        identity_id: UUID of the identity.
        name: Identity display name (create, upsert, update).
        identifier: Unique external identifier string (create, upsert).
        identity_type: Type classification (create, upsert). E.g., "user", "org", "customer".
        properties: Key-value properties dict (create, upsert, set_properties).
        query: Search query (list).
        limit: Max results. Defaults to 15.
        offset: Pagination offset.
    """
    try:
        if operation == "list":
            params = _paginate_params(limit, offset)
            if query:
                params["query_text"] = query
            result = await _api_call(tenant_id, "GET", "/v1/identities", params=params)
            if not result["success"]:
                return result
            identities = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": i.get("id"), "name": i.get("name"),
                        "identifier": i.get("identifier"),
                        "identity_type": i.get("identity_type")} for i in identities]
            return {"success": True, "identities": summary, "count": len(summary)}

        elif operation == "create":
            if not name or not identifier or not identity_type:
                return {"success": False, "error": "name, identifier (identifier_key), and identity_type (user/org/other) required for create"}
            body: Dict[str, Any] = {"name": name, "identifier_key": identifier, "identity_type": identity_type}
            if properties:
                if isinstance(properties, dict):
                    body["properties"] = [{"key": k, "value": v, "type": "string"} for k, v in properties.items()]
                else:
                    body["properties"] = properties
            result = await _api_call(tenant_id, "POST", "/v1/identities", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "identity": result["data"], "identity_id": result["data"].get("id")}

        elif operation == "upsert":
            if not identifier:
                return {"success": False, "error": "identifier (identifier_key) required for upsert"}
            body: Dict[str, Any] = {"identifier_key": identifier}
            if name:
                body["name"] = name
            if identity_type:
                body["identity_type"] = identity_type
            if properties:
                if isinstance(properties, dict):
                    body["properties"] = [{"key": k, "value": v, "type": "string"} for k, v in properties.items()]
                else:
                    body["properties"] = properties
            result = await _api_call(tenant_id, "PUT", "/v1/identities", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "identity": result["data"]}

        elif operation == "get":
            if not identity_id:
                return {"success": False, "error": "identity_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/identities/{identity_id}")
            if not result["success"]:
                return result
            return {"success": True, "identity": result["data"]}

        elif operation == "update":
            if not identity_id:
                return {"success": False, "error": "identity_id required for update"}
            body = {}
            if name:
                body["name"] = name
            if identifier:
                body["identifier"] = identifier
            if identity_type:
                body["identity_type"] = identity_type
            if properties:
                body["properties"] = properties
            result = await _api_call(tenant_id, "PATCH", f"/v1/identities/{identity_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "identity": result["data"]}

        elif operation == "delete":
            if not identity_id:
                return {"success": False, "error": "identity_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/identities/{identity_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Identity {identity_id} deleted"}

        elif operation == "count":
            result = await _api_call(tenant_id, "GET", "/v1/identities", params={"limit": 10000})
            if not result["success"]:
                return result
            count = len(result["data"]) if isinstance(result["data"], list) else 0
            return {"success": True, "count": count}

        elif operation == "list_agents":
            if not identity_id:
                return {"success": False, "error": "identity_id required for list_agents"}
            result = await _api_call(tenant_id, "GET", f"/v1/identities/{identity_id}/agents",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name")} for a in agents]
            return {"success": True, "agents": summary, "count": len(summary)}

        elif operation == "list_blocks":
            if not identity_id:
                return {"success": False, "error": "identity_id required for list_blocks"}
            result = await _api_call(tenant_id, "GET", f"/v1/identities/{identity_id}/blocks",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            blocks = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": b.get("id"), "label": b.get("label"),
                        "value": _truncate(b.get("value"), 200)} for b in blocks]
            return {"success": True, "blocks": summary, "count": len(summary)}

        elif operation == "set_properties":
            if not identity_id or not properties:
                return {"success": False, "error": "identity_id and properties required for set_properties"}
            props = properties
            if isinstance(props, dict):
                props = [{"key": k, "value": v, "type": "string"} for k, v in props.items()]
            result = await _api_call(tenant_id, "PATCH", f"/v1/identities/{identity_id}",
                                     json_body={"properties": props})
            if not result["success"]:
                return result
            return {"success": True, "identity": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, create, upsert, get, update, delete, count, list_agents, list_blocks, set_properties"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 12: Run & Step Observability (17 operations)
# ============================================================================

@mcp.tool
async def lt_run(
    tenant_id: str,
    operation: str,
    run_id: Optional[str] = None,
    step_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    feedback: Optional[str] = None,
    feedback_score: Optional[float] = None,
    transaction_id: Optional[str] = None,
    transaction_status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Observe and manage agent runs and steps — traces, metrics, feedback.

    Runs represent individual agent invocations (message processing). Each run
    contains multiple steps (LLM calls, tool executions). Use this for debugging,
    monitoring, and providing feedback on agent behavior.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            Runs: "list", "list_active", "get", "delete", "get_messages",
                  "get_metrics", "list_steps", "get_trace", "get_usage"
            Steps: "list_all_steps", "get_step", "add_feedback",
                   "get_step_messages", "get_step_metrics", "get_step_trace"
            Transactions: "update_transaction"
        run_id: UUID of the run.
        step_id: UUID of the step.
        agent_id: Filter runs by agent UUID.
        feedback: Feedback text (add_feedback).
        feedback_score: Numeric feedback score 0-1 (add_feedback).
        transaction_id: Transaction UUID (update_transaction).
        transaction_status: New status for transaction (update_transaction).
        limit: Max results. Defaults to 20.
        offset: Pagination offset.

    Notes:
        - list_all_steps has an automatic fallback: if /v1/steps fails (Letta v0.16.4
          server bug with order param), it iterates over recent runs and collects
          per-run steps via /v1/runs/{id}/steps instead.
        - For per-run steps, use list_steps (requires run_id) which always works.
    """
    try:
        # --- Runs ---
        if operation == "list":
            params = _paginate_params(limit, offset)
            if agent_id:
                params["agent_id"] = agent_id
            result = await _api_call(tenant_id, "GET", "/v1/runs", params=params)
            if not result["success"]:
                return result
            runs = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": r.get("id"), "status": r.get("status"),
                        "agent_id": r.get("agent_id"), "created_at": r.get("created_at"),
                        "completed_at": r.get("completed_at")} for r in runs]
            return {"success": True, "runs": summary, "count": len(summary)}

        elif operation == "list_active":
            result = await _api_call(tenant_id, "GET", "/v1/runs/active",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            runs = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": r.get("id"), "status": r.get("status"),
                        "agent_id": r.get("agent_id")} for r in runs]
            return {"success": True, "runs": summary, "count": len(summary)}

        elif operation == "get":
            if not run_id:
                return {"success": False, "error": "run_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}")
            if not result["success"]:
                return result
            return {"success": True, "run": result["data"]}

        elif operation == "delete":
            if not run_id:
                return {"success": False, "error": "run_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/runs/{run_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Run {run_id} deleted"}

        elif operation == "get_messages":
            if not run_id:
                return {"success": False, "error": "run_id required for get_messages"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}/messages",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            messages = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": m.get("id"), "role": m.get("role"),
                        "content": _truncate(m.get("content") or m.get("text", ""), 500),
                        "created_at": m.get("created_at")} for m in messages]
            return {"success": True, "messages": summary, "count": len(summary)}

        elif operation == "get_metrics":
            if not run_id:
                return {"success": False, "error": "run_id required for get_metrics"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}/metrics")
            if not result["success"]:
                return result
            return {"success": True, "metrics": result["data"]}

        elif operation == "list_steps":
            if not run_id:
                return {"success": False, "error": "run_id required for list_steps"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}/steps",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            steps = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": s.get("id"), "step_type": s.get("step_type"),
                        "status": s.get("status"), "created_at": s.get("created_at")} for s in steps]
            return {"success": True, "steps": summary, "count": len(summary)}

        elif operation == "get_trace":
            if not run_id:
                return {"success": False, "error": "run_id required for get_trace"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}/trace")
            if not result["success"]:
                return result
            return {"success": True, "trace": result["data"]}

        elif operation == "get_usage":
            if not run_id:
                return {"success": False, "error": "run_id required for get_usage"}
            result = await _api_call(tenant_id, "GET", f"/v1/runs/{run_id}/usage")
            if not result["success"]:
                return result
            return {"success": True, "usage": result["data"]}

        # --- Steps ---
        elif operation == "list_all_steps":
            # Try direct endpoint first; fall back to per-run iteration if Letta v0.16.4
            # returns 400 (server bug: order param has bool default instead of str)
            params = _paginate_params(limit, offset)
            if agent_id:
                params["agent_id"] = agent_id
            result = await _api_call(tenant_id, "GET", "/v1/steps", params=params)
            if result["success"]:
                steps = result["data"] if isinstance(result["data"], list) else []
                summary = [{"id": s.get("id"), "step_type": s.get("step_type"),
                            "run_id": s.get("run_id"), "status": s.get("status")} for s in steps]
                return {"success": True, "steps": summary, "count": len(summary)}

            # Fallback: iterate over recent runs and collect their steps
            runs_params: Dict[str, Any] = {"limit": 10, "offset": 0}
            if agent_id:
                runs_params["agent_id"] = agent_id
            runs_result = await _api_call(tenant_id, "GET", "/v1/runs", params=runs_params)
            if not runs_result["success"]:
                return {"success": False, "error": f"Direct /v1/steps failed ({result.get('error', 'unknown')}); fallback /v1/runs also failed: {runs_result.get('error')}"}
            runs = runs_result["data"] if isinstance(runs_result["data"], list) else []
            all_steps = []
            for run in runs:
                rid = run.get("id")
                if not rid:
                    continue
                step_result = await _api_call(tenant_id, "GET", f"/v1/runs/{rid}/steps",
                                              params=_paginate_params(limit, 0))
                if step_result["success"]:
                    run_steps = step_result["data"] if isinstance(step_result["data"], list) else []
                    for s in run_steps:
                        all_steps.append({"id": s.get("id"), "step_type": s.get("step_type"),
                                          "run_id": rid, "status": s.get("status")})
                if len(all_steps) >= limit:
                    break
            all_steps = all_steps[:limit]
            return {"success": True, "steps": all_steps, "count": len(all_steps),
                    "_note": "Fetched via per-run fallback (Letta v0.16.4 /v1/steps bug)"}

        elif operation == "get_step":
            if not step_id:
                return {"success": False, "error": "step_id required for get_step"}
            result = await _api_call(tenant_id, "GET", f"/v1/steps/{step_id}")
            if not result["success"]:
                return result
            return {"success": True, "step": result["data"]}

        elif operation == "add_feedback":
            if not step_id:
                return {"success": False, "error": "step_id required for add_feedback"}
            body: Dict[str, Any] = {}
            if feedback:
                body["feedback"] = feedback
            if feedback_score is not None:
                body["score"] = feedback_score
            result = await _api_call(tenant_id, "PATCH", f"/v1/steps/{step_id}/feedback", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "get_step_messages":
            if not step_id:
                return {"success": False, "error": "step_id required for get_step_messages"}
            result = await _api_call(tenant_id, "GET", f"/v1/steps/{step_id}/messages")
            if not result["success"]:
                return result
            return {"success": True, "messages": result["data"]}

        elif operation == "get_step_metrics":
            if not step_id:
                return {"success": False, "error": "step_id required for get_step_metrics"}
            result = await _api_call(tenant_id, "GET", f"/v1/steps/{step_id}/metrics")
            if not result["success"]:
                return result
            return {"success": True, "metrics": result["data"]}

        elif operation == "get_step_trace":
            if not step_id:
                return {"success": False, "error": "step_id required for get_step_trace"}
            result = await _api_call(tenant_id, "GET", f"/v1/steps/{step_id}/trace")
            if not result["success"]:
                return result
            return {"success": True, "trace": result["data"]}

        # --- Transactions ---
        elif operation == "update_transaction":
            if not transaction_id or not transaction_status:
                return {"success": False, "error": "transaction_id and transaction_status required for update_transaction"}
            if not step_id:
                return {"success": False, "error": "step_id also required for update_transaction"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/steps/{step_id}/transaction/{transaction_id}",
                                     json_body={"status": transaction_status})
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, list_active, get, delete, get_messages, get_metrics, list_steps, get_trace, get_usage, list_all_steps, get_step, add_feedback, get_step_messages, get_step_metrics, get_step_trace, update_transaction"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 13: Archive Management (9 operations)
# ============================================================================

@mcp.tool
async def lt_archive(
    tenant_id: str,
    operation: str,
    archive_id: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    embedding_model: Optional[str] = None,
    text: Optional[str] = None,
    texts: Optional[List[str]] = None,
    passage_id: Optional[str] = None,
    limit: int = 15,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage archives — shared archival memory stores that can be attached to agents.

    Archives are standalone archival memory collections. Unlike agent-specific archival
    memory, archives can be shared across multiple agents. They store passages
    (text chunks with embeddings) for semantic search.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            CRUD: "list", "create", "get", "update", "delete"
            Relations: "list_agents"
            Passages: "create_passage", "batch_create_passages", "delete_passage"
        archive_id: UUID of the archive.
        name: Archive name (create, update).
        description: Archive description (create, update).
        embedding_model: Embedding model handle (create). E.g., "openai/text-embedding-3-small".
        text: Passage text (create_passage).
        texts: List of passage texts (batch_create_passages).
        passage_id: UUID of a passage (delete_passage).
        limit: Max results. Defaults to 15.
        offset: Pagination offset.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/archives", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            archives = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name"),
                        "description": _truncate(a.get("description"), 100),
                        "created_at": a.get("created_at")} for a in archives]
            return {"success": True, "archives": summary, "count": len(summary)}

        elif operation == "create":
            if not name:
                return {"success": False, "error": "name required for create"}
            body: Dict[str, Any] = {"name": name}
            if description:
                body["description"] = description
            if embedding_model:
                body["embedding"] = embedding_model
            result = await _api_call(tenant_id, "POST", "/v1/archives", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "archive": result["data"], "archive_id": result["data"].get("id")}

        elif operation == "get":
            if not archive_id:
                return {"success": False, "error": "archive_id required for get"}
            result = await _api_call(tenant_id, "GET", f"/v1/archives/{archive_id}")
            if not result["success"]:
                return result
            return {"success": True, "archive": result["data"]}

        elif operation == "update":
            if not archive_id:
                return {"success": False, "error": "archive_id required for update"}
            body = {}
            if name:
                body["name"] = name
            if description:
                body["description"] = description
            result = await _api_call(tenant_id, "PATCH", f"/v1/archives/{archive_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "archive": result["data"]}

        elif operation == "delete":
            if not archive_id:
                return {"success": False, "error": "archive_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/archives/{archive_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Archive {archive_id} deleted"}

        elif operation == "list_agents":
            if not archive_id:
                return {"success": False, "error": "archive_id required for list_agents"}
            result = await _api_call(tenant_id, "GET", f"/v1/archives/{archive_id}/agents",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            agents = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": a.get("id"), "name": a.get("name")} for a in agents]
            return {"success": True, "agents": summary, "count": len(summary)}

        elif operation == "create_passage":
            if not archive_id or not text:
                return {"success": False, "error": "archive_id and text required for create_passage"}
            result = await _api_call(tenant_id, "POST", f"/v1/archives/{archive_id}/passages",
                                     json_body={"text": text})
            if not result["success"]:
                return result
            return {"success": True, "passage": result["data"]}

        elif operation == "batch_create_passages":
            if not archive_id or not texts:
                return {"success": False, "error": "archive_id and texts required for batch_create_passages"}
            passages = [{"text": t} for t in texts]
            result = await _api_call(tenant_id, "POST", f"/v1/archives/{archive_id}/passages/batch",
                                     json_body={"passages": passages})
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "delete_passage":
            if not passage_id:
                return {"success": False, "error": "passage_id required for delete_passage"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/passages/{passage_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Passage {passage_id} deleted"}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, create, get, update, delete, list_agents, create_passage, batch_create_passages, delete_passage"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 14: Model & Provider Management (10 operations)
# ============================================================================

@mcp.tool
async def lt_model_provider(
    tenant_id: str,
    operation: str,
    provider_id: Optional[str] = None,
    name: Optional[str] = None,
    provider_type: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    limit: int = 50,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage LLM models and providers — list available models, configure providers.

    View and manage the LLM and embedding model providers configured on the Letta
    instance. Providers connect to model APIs (OpenAI, Anthropic, local, etc.).

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            Models: "list_models", "list_embedding_models"
            Providers: "list_providers", "create_provider", "get_provider",
                       "update_provider", "delete_provider", "check_providers",
                       "check_provider", "refresh_provider"
        provider_id: UUID of the provider.
        name: Provider name (create_provider).
        provider_type: Provider type (create_provider, check_providers).
                       E.g., "openai", "anthropic", "ollama".
        api_key: API key for the provider (create_provider, update_provider, check_providers).
        base_url: Custom base URL (create_provider, update_provider).
        config: Additional provider config dict (create_provider, update_provider).
        limit: Max results. Defaults to 50.
        offset: Pagination offset.
    """
    try:
        if operation == "list_models":
            result = await _api_call(tenant_id, "GET", "/v1/models", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            models = result["data"] if isinstance(result["data"], list) else []
            summary = [{"model": m.get("model") or m.get("name"),
                        "provider": m.get("provider") or m.get("provider_name"),
                        "context_window": m.get("context_window")} for m in models]
            return {"success": True, "models": summary, "count": len(summary)}

        elif operation == "list_embedding_models":
            result = await _api_call(tenant_id, "GET", "/v1/models/embedding",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            models = result["data"] if isinstance(result["data"], list) else []
            summary = [{"model": m.get("model") or m.get("name"),
                        "provider": m.get("provider") or m.get("provider_name"),
                        "embedding_dim": m.get("embedding_dim")} for m in models]
            return {"success": True, "models": summary, "count": len(summary)}

        elif operation == "list_providers":
            result = await _api_call(tenant_id, "GET", "/v1/providers", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            providers = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": p.get("id"), "name": p.get("name"),
                        "provider_type": p.get("provider_type")} for p in providers]
            return {"success": True, "providers": summary, "count": len(summary)}

        elif operation == "create_provider":
            if not name or not provider_type:
                return {"success": False, "error": "name and provider_type required for create_provider"}
            body: Dict[str, Any] = {"name": name, "provider_type": provider_type}
            if api_key:
                body["api_key"] = api_key
            if base_url:
                body["base_url"] = base_url
            if config:
                body.update(config)
            result = await _api_call(tenant_id, "POST", "/v1/providers", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "provider": result["data"]}

        elif operation == "get_provider":
            if not provider_id:
                return {"success": False, "error": "provider_id required for get_provider"}
            result = await _api_call(tenant_id, "GET", f"/v1/providers/{provider_id}")
            if not result["success"]:
                return result
            return {"success": True, "provider": result["data"]}

        elif operation == "update_provider":
            if not provider_id:
                return {"success": False, "error": "provider_id required for update_provider"}
            body = {}
            if name:
                body["name"] = name
            if api_key:
                body["api_key"] = api_key
            if base_url:
                body["base_url"] = base_url
            if config:
                body.update(config)
            result = await _api_call(tenant_id, "PATCH", f"/v1/providers/{provider_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "provider": result["data"]}

        elif operation == "delete_provider":
            if not provider_id:
                return {"success": False, "error": "provider_id required for delete_provider"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/providers/{provider_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Provider {provider_id} deleted"}

        elif operation == "check_providers":
            if not provider_type or not api_key:
                return {"success": False, "error": "provider_type and api_key required for check_providers (validates a provider config before creating)"}
            body: Dict[str, Any] = {"provider_type": provider_type, "api_key": api_key}
            if base_url:
                body["base_url"] = base_url
            result = await _api_call(tenant_id, "POST", "/v1/providers/check", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "check_provider":
            if not provider_id:
                return {"success": False, "error": "provider_id required for check_provider"}
            result = await _api_call(tenant_id, "POST", f"/v1/providers/{provider_id}/check")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "refresh_provider":
            if not provider_id:
                return {"success": False, "error": "provider_id required for refresh_provider"}
            result = await _api_call(tenant_id, "PATCH", f"/v1/providers/{provider_id}/refresh")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list_models, list_embedding_models, list_providers, create_provider, get_provider, update_provider, delete_provider, check_providers, check_provider, refresh_provider"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 15: Sandbox Configuration (12 operations)
# ============================================================================

@mcp.tool
async def lt_sandbox(
    tenant_id: str,
    operation: str,
    sandbox_id: Optional[str] = None,
    sandbox_type: Optional[str] = None,
    env_var_id: Optional[str] = None,
    key: Optional[str] = None,
    value: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Manage sandbox configurations for tool execution environments.

    Sandboxes provide isolated execution environments for agent tools. Configure
    E2B cloud sandboxes or local sandboxes, manage environment variables, and
    control the execution context for tool code.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            CRUD: "list", "create", "update", "delete"
            Presets: "create_e2b_default", "create_local_default",
                     "create_local", "recreate_venv"
            Env Vars: "list_env_vars", "create_env_var", "update_env_var", "delete_env_var"
        sandbox_id: UUID of the sandbox config.
        sandbox_type: Type of sandbox (create). E.g., "e2b", "local".
        env_var_id: UUID of an environment variable.
        key: Environment variable key (create_env_var, update_env_var).
        value: Environment variable value (create_env_var, update_env_var).
        config: Sandbox configuration dict (create, update).
        limit: Max results. Defaults to 20.
        offset: Pagination offset.
    """
    try:
        if operation == "list":
            result = await _api_call(tenant_id, "GET", "/v1/sandbox-config",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            configs = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": c.get("id"), "sandbox_type": c.get("sandbox_type"),
                        "created_at": c.get("created_at")} for c in configs]
            return {"success": True, "sandboxes": summary, "count": len(summary)}

        elif operation == "create":
            body: Dict[str, Any] = {}
            if sandbox_type:
                body["sandbox_type"] = sandbox_type
            if config:
                body.update(config)
            result = await _api_call(tenant_id, "POST", "/v1/sandbox-config", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "sandbox": result["data"]}

        elif operation == "create_e2b_default":
            result = await _api_call(tenant_id, "POST", "/v1/sandbox-config/e2b/default")
            if not result["success"]:
                return result
            return {"success": True, "sandbox": result["data"]}

        elif operation == "create_local":
            body = config or {}
            result = await _api_call(tenant_id, "POST", "/v1/sandbox-config/local", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "sandbox": result["data"]}

        elif operation == "create_local_default":
            result = await _api_call(tenant_id, "POST", "/v1/sandbox-config/local/default")
            if not result["success"]:
                return result
            return {"success": True, "sandbox": result["data"]}

        elif operation == "recreate_venv":
            result = await _api_call(tenant_id, "POST", "/v1/sandbox-config/local/recreate-venv")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Virtual environment recreated for sandbox {sandbox_id}"}

        elif operation == "update":
            if not sandbox_id:
                return {"success": False, "error": "sandbox_id required for update"}
            body = config or {}
            result = await _api_call(tenant_id, "PATCH", f"/v1/sandbox-config/{sandbox_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "sandbox": result["data"]}

        elif operation == "delete":
            if not sandbox_id:
                return {"success": False, "error": "sandbox_id required for delete"}
            result = await _api_call(tenant_id, "DELETE", f"/v1/sandbox-config/{sandbox_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Sandbox config {sandbox_id} deleted"}

        # --- Environment Variables ---
        elif operation == "list_env_vars":
            if not sandbox_id:
                return {"success": False, "error": "sandbox_id required for list_env_vars"}
            result = await _api_call(tenant_id, "GET", f"/v1/sandbox-config/{sandbox_id}/environment-variable",
                                     params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            env_vars = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": e.get("id"), "key": e.get("key"),
                        "value": _truncate(e.get("value"), 50)} for e in env_vars]
            return {"success": True, "env_vars": summary, "count": len(summary)}

        elif operation == "create_env_var":
            if not sandbox_id or not key or value is None:
                return {"success": False, "error": "sandbox_id, key, and value required for create_env_var"}
            result = await _api_call(tenant_id, "POST", f"/v1/sandbox-config/{sandbox_id}/environment-variable",
                                     json_body={"key": key, "value": value})
            if not result["success"]:
                return result
            return {"success": True, "env_var": result["data"]}

        elif operation == "update_env_var":
            if not env_var_id:
                return {"success": False, "error": "env_var_id required for update_env_var"}
            body = {}
            if key:
                body["key"] = key
            if value is not None:
                body["value"] = value
            result = await _api_call(tenant_id, "PATCH",
                                     f"/v1/sandbox-config/environment-variable/{env_var_id}", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "env_var": result["data"]}

        elif operation == "delete_env_var":
            if not env_var_id:
                return {"success": False, "error": "env_var_id required for delete_env_var"}
            result = await _api_call(tenant_id, "DELETE",
                                     f"/v1/sandbox-config/environment-variable/{env_var_id}")
            if not result["success"]:
                return result
            return {"success": True, "message": f"Env var {env_var_id} deleted"}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list, create, create_e2b_default, create_local, create_local_default, recreate_venv, update, delete, list_env_vars, create_env_var, update_env_var, delete_env_var"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Tool 16: Miscellaneous Operations (8 operations)
# ============================================================================

@mcp.tool
async def lt_misc(
    tenant_id: str,
    operation: str,
    query: Optional[str] = None,
    agent_id: Optional[str] = None,
    message: Optional[str] = None,
    messages: Optional[List[Dict[str, str]]] = None,
    model: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Miscellaneous Letta operations — tags, global search, chat completions, health.

    Provides cross-cutting utilities that don't fit into a specific resource category:
    tag management, global message/passage search, direct LLM chat completions,
    and system health checks.

    Args:
        tenant_id: Tenant identifier.
        operation: One of:
            Tags: "list_tags"
            Search: "search_messages", "search_passages"
            Messages: "list_messages", "batch_messages"
            Storage: "get_embedding_storage"
            LLM: "chat_completion"
            System: "health"
        query: Search query (search_messages, search_passages).
        agent_id: Filter by agent UUID (search_messages, list_messages).
        message: Single message for chat_completion.
        messages: Message list for chat_completion/batch. Format: [{"role": "user", "content": "..."}].
        model: LLM model for chat_completion. E.g., "openai/gpt-4o".
        limit: Max results. Defaults to 20.
        offset: Pagination offset.
    """
    try:
        if operation == "list_tags":
            result = await _api_call(tenant_id, "GET", "/v1/tags", params=_paginate_params(limit, offset))
            if not result["success"]:
                return result
            tags = result["data"] if isinstance(result["data"], list) else []
            return {"success": True, "tags": tags, "count": len(tags)}

        elif operation == "search_messages":
            params = _paginate_params(limit, offset)
            if query:
                params["query"] = query
            if agent_id:
                params["agent_id"] = agent_id
            result = await _api_call(tenant_id, "GET", "/v1/messages", params=params)
            if not result["success"]:
                return result
            messages_data = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": m.get("id"), "role": m.get("role"),
                        "content": _truncate(m.get("content") or m.get("text", ""), 500),
                        "agent_id": m.get("agent_id"),
                        "created_at": m.get("created_at")} for m in messages_data]
            return {"success": True, "messages": summary, "count": len(summary)}

        elif operation == "list_messages":
            params = _paginate_params(limit, offset)
            if agent_id:
                params["agent_id"] = agent_id
            result = await _api_call(tenant_id, "GET", "/v1/messages", params=params)
            if not result["success"]:
                return result
            messages_data = result["data"] if isinstance(result["data"], list) else []
            summary = [{"id": m.get("id"), "role": m.get("role"),
                        "content": _truncate(m.get("content") or m.get("text", ""), 500),
                        "agent_id": m.get("agent_id")} for m in messages_data]
            return {"success": True, "messages": summary, "count": len(summary)}

        elif operation == "batch_messages":
            if not messages:
                return {"success": False, "error": "messages list required for batch_messages"}
            result = await _api_call(tenant_id, "POST", "/v1/messages/batch", json_body={"messages": messages})
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "search_passages":
            body: Dict[str, Any] = {"limit": limit}
            if query:
                body["query_text"] = query
            if agent_id:
                body["agent_id"] = agent_id
            result = await _api_call(tenant_id, "POST", "/v1/passages/search", json_body=body)
            if not result["success"]:
                return result
            raw = result["data"] if isinstance(result["data"], list) else []
            summary = []
            for item in raw:
                p = item.get("passage", item) if isinstance(item, dict) else item
                summary.append({"id": p.get("id"), "text": _truncate(p.get("text"), 200),
                                "agent_id": p.get("agent_id"),
                                "source_id": p.get("source_id"),
                                "score": item.get("score") if isinstance(item, dict) else None})
            return {"success": True, "passages": summary, "count": len(summary)}

        elif operation == "get_embedding_storage":
            result = await _api_call(tenant_id, "GET", "/v1/embeddings/total_storage_size")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        elif operation == "chat_completion":
            if not message and not messages:
                return {"success": False, "error": "message or messages required for chat_completion"}
            body: Dict[str, Any] = {}
            if messages:
                body["messages"] = messages
            elif message:
                body["messages"] = [{"role": "user", "content": message}]
            if model:
                body["model"] = model
            result = await _api_call(tenant_id, "POST", "/v1/chat/completions", json_body=body)
            if not result["success"]:
                return result
            return {"success": True, "response": result["data"]}

        elif operation == "health":
            result = await _api_call(tenant_id, "GET", "/v1/health")
            if not result["success"]:
                return result
            return {"success": True, "data": result["data"]}

        else:
            return {"success": False, "error": f"Unknown operation '{operation}'. Valid: list_tags, search_messages, list_messages, batch_messages, search_passages, get_embedding_storage, chat_completion, health"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Main entry point
# ============================================================================

def main():
    import os
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8012"))
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()
