"""
Langfuse MCP Server (Multi-tenant)

A FastMCP server providing Langfuse observability and tracing operations with multi-tenant support.
Each tenant uses their own Langfuse API keys.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.langfuse.tenant_manager import LangfuseTenantManager
except ImportError:
    from .tenant_manager import LangfuseTenantManager

# Initialize tenant manager
tenant_manager = LangfuseTenantManager()


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize tenants from Redis and cleanup on shutdown."""
    # Initialize: load tenants from Redis and environment
    await tenant_manager.initialize()
    yield
    # Cleanup: close all connections and Redis connection
    await tenant_manager.close_all()


# Create server with lifespan
mcp = FastMCP("Langfuse Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "langfuse-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def lf_register_tenant(
    tenant_id: str,
    secret_key: str,
    public_key: str,
    base_url: str = "https://langfuse.bionicaisolutions.com",
    max_concurrent_requests: int = 100,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new Langfuse tenant configuration with concurrency control.

    Sets up a new tenant in the multi-tenant Langfuse MCP server by storing the
    tenant's API credentials and connection settings. This must be called before
    any other Langfuse tool can be used for the given tenant. The tenant
    configuration is persisted to Redis so it survives server restarts.

    Use this tool when onboarding a new project or organization that needs its own
    isolated Langfuse tracing environment. Each tenant operates with independent
    API keys and a configurable concurrency limit to prevent any single tenant
    from overwhelming the Langfuse backend.

    Args:
        tenant_id (str): Unique identifier for this tenant. Used as the lookup
            key in all subsequent tool calls. Must be unique across the server.
        secret_key (str): Langfuse secret API key for authentication (typically
            starts with "sk-lf-..."). Obtained from the Langfuse project settings.
        public_key (str): Langfuse public API key for authentication (typically
            starts with "pk-lf-..."). Obtained from the Langfuse project settings.
        base_url (str): Base URL of the Langfuse instance to connect to.
            Defaults to "https://langfuse.bionicaisolutions.com". Override this
            when using a self-hosted or alternative Langfuse deployment.
        max_concurrent_requests (int): Maximum number of concurrent API requests
            allowed for this tenant. Defaults to 100. Adjust based on the
            tenant's expected workload and the Langfuse instance capacity.

    Returns:
        Dict with:
        - success (bool): Whether the registration succeeded.
        - message (str): Confirmation message on success.
        - error (str): Error message if the registration failed.

    Note:
        Re-registering an existing tenant_id will overwrite the previous
        configuration. Ensure the secret_key and public_key correspond to the
        same Langfuse project.
    """
    if ctx:
        await ctx.info(f"Registering Langfuse tenant: {tenant_id}")

    try:
        from mcp_servers.langfuse.tenant_manager import LangfuseTenantConfig

        config = LangfuseTenantConfig(
            tenant_id=tenant_id,
            secret_key=secret_key,
            public_key=public_key,
            base_url=base_url,
            max_concurrent_requests=max_concurrent_requests,
        )

        await tenant_manager.register_tenant(config)
        return {
            "success": True,
            "message": f"Tenant '{tenant_id}' registered successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_trace(
    tenant_id: str,
    name: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new trace in Langfuse for a given tenant.

    A trace is the top-level object in the Langfuse observability hierarchy. It
    represents a single end-to-end execution, such as an API request, an agent
    run, or a pipeline invocation. All other observations (spans, generations,
    events) and scores are attached to a trace.

    Use this tool at the start of any workflow you want to observe. After
    creating a trace, use the returned trace ID with lf_create_span,
    lf_create_generation, lf_create_event, or lf_create_score to build a
    detailed execution tree underneath it.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project will receive
            the trace. Must be registered via lf_register_tenant first.
        name (str): Human-readable name for the trace (e.g., "chat-completion",
            "document-qa-pipeline"). Used for filtering and display in the
            Langfuse dashboard.
        user_id (str | None): Optional identifier of the end user who triggered
            the traced operation. Enables per-user analytics in Langfuse.
            Defaults to None.
        session_id (str | None): Optional session identifier to group related
            traces together (e.g., a multi-turn conversation). Defaults to None.
        metadata (Dict[str, Any] | None): Optional arbitrary key-value metadata
            to attach to the trace (e.g., {"environment": "production",
            "version": "2.1.0"}). Defaults to None.
        tags (List[str] | None): Optional list of string tags for categorization
            and filtering in the Langfuse UI (e.g., ["beta", "high-priority"]).
            Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the trace was created successfully.
        - trace (dict): The created trace object including its id, which is
          needed for attaching child observations and scores.
        - error (str): Error message if the operation failed.

    Note:
        The trace hierarchy in Langfuse is: Trace -> Span/Generation/Event.
        A trace must exist before you can attach spans, generations, events,
        or scores to it.
    """
    if ctx:
        await ctx.info(f"Creating trace '{name}' for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.trace(
            name=name,
            user_id=user_id,
            session_id=session_id,
            metadata=metadata,
            tags=tags,
        )
        return {
            "success": True,
            "trace": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_span(
    tenant_id: str,
    trace_id: str,
    name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a span observation within an existing Langfuse trace.

    A span represents a timed unit of work inside a trace that is NOT a large
    language model call. Typical use cases include database queries, API calls
    to external services, data preprocessing steps, retrieval operations, or
    any other discrete stage in a pipeline that you want to measure and inspect.

    Use this tool when you need to record the duration and metadata of a
    non-LLM operation within a traced workflow. For LLM-specific calls, use
    lf_create_generation instead, which captures model-specific fields such as
    model name, parameters, input prompts, and output completions.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project contains the
            target trace. Must be registered via lf_register_tenant first.
        trace_id (str): The ID of the parent trace to attach this span to.
            Obtain this from the response of lf_create_trace.
        name (str): Human-readable name for the span (e.g., "vector-db-lookup",
            "fetch-user-profile", "parse-document"). Displayed in the Langfuse
            trace timeline.
        start_time (str | None): ISO 8601 formatted start timestamp for the
            span (e.g., "2025-01-15T10:30:00Z"). If omitted, Langfuse uses the
            server-side receive time. Defaults to None.
        end_time (str | None): ISO 8601 formatted end timestamp for the span.
            If omitted, the span remains open until explicitly ended or the
            trace is finalized. Defaults to None.
        metadata (Dict[str, Any] | None): Optional arbitrary key-value metadata
            to attach to the span (e.g., {"db": "pgvector", "top_k": 5}).
            Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the span was created successfully.
        - span (dict): The created span object including its id.
        - error (str): Error message if the operation failed.

    Note:
        Spans differ from generations in that they do not carry LLM-specific
        fields (model, model_parameters, input, output). If you are recording
        an LLM call, use lf_create_generation instead to capture the full
        context of the model invocation.
    """
    if ctx:
        await ctx.info(f"Creating span '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.span(
            trace_id=trace_id,
            name=name,
            start_time=start_time,
            end_time=end_time,
            metadata=metadata,
        )
        return {
            "success": True,
            "span": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_generation(
    tenant_id: str,
    trace_id: str,
    name: str,
    model: Optional[str] = None,
    model_parameters: Optional[Dict[str, Any]] = None,
    input: Optional[Any] = None,
    output: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a generation (LLM call) observation within an existing Langfuse trace.

    A generation is a specialized observation type designed to capture all details
    of a large language model invocation, including the model used, its
    configuration parameters, the input prompt or messages, and the generated
    output. Langfuse uses this data to compute token usage, cost estimates, and
    latency metrics for LLM calls.

    Use this tool whenever you want to record a call to an LLM (e.g., OpenAI,
    Anthropic, a local model) as part of a traced workflow. For non-LLM
    operations such as database queries, retrieval steps, or general processing,
    use lf_create_span instead.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project contains the
            target trace. Must be registered via lf_register_tenant first.
        trace_id (str): The ID of the parent trace to attach this generation to.
            Obtain this from the response of lf_create_trace.
        name (str): Human-readable name for the generation (e.g.,
            "gpt4-summarize", "claude-extract-entities"). Displayed in the
            Langfuse trace timeline.
        model (str | None): The name or identifier of the LLM used (e.g.,
            "gpt-4o", "claude-3-opus", "llama-3-70b"). Langfuse uses this to
            look up token pricing for cost calculation. Defaults to None.
        model_parameters (Dict[str, Any] | None): Optional dictionary of model
            configuration parameters (e.g., {"temperature": 0.7, "max_tokens":
            1024, "top_p": 0.9}). Defaults to None.
        input (Any | None): The input sent to the LLM. Can be a string, a list
            of message dicts, or any JSON-serializable structure representing
            the prompt. Defaults to None.
        output (Any | None): The output received from the LLM. Can be a string,
            a message dict, or any JSON-serializable structure representing the
            completion. Defaults to None.
        metadata (Dict[str, Any] | None): Optional arbitrary key-value metadata
            to attach to the generation (e.g., {"prompt_version": "v3",
            "use_case": "summarization"}). Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the generation was created successfully.
        - generation (dict): The created generation object including its id.
        - error (str): Error message if the operation failed.

    Note:
        Generations are distinct from spans: they include LLM-specific fields
        (model, model_parameters, input, output) that enable Langfuse to
        compute token usage and cost analytics. Always prefer lf_create_generation
        over lf_create_span when recording LLM calls.
    """
    if ctx:
        await ctx.info(f"Creating generation '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.generation(
            trace_id=trace_id,
            name=name,
            model=model,
            model_parameters=model_parameters,
            input=input,
            output=output,
            metadata=metadata,
        )
        return {
            "success": True,
            "generation": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_event(
    tenant_id: str,
    trace_id: str,
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create an event observation within an existing Langfuse trace.

    An event is a lightweight, point-in-time observation that records something
    notable that happened during a traced execution. Unlike spans, events have
    no duration; they mark a single moment in time. Typical use cases include
    logging user actions, recording decision points, flagging errors or
    warnings, or noting cache hits/misses.

    Use this tool when you need to annotate a trace with a timestamped marker
    that does not require start/end timing. For timed operations, use
    lf_create_span (non-LLM) or lf_create_generation (LLM calls) instead.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project contains the
            target trace. Must be registered via lf_register_tenant first.
        trace_id (str): The ID of the parent trace to attach this event to.
            Obtain this from the response of lf_create_trace.
        name (str): Human-readable name for the event (e.g., "cache-miss",
            "user-feedback-received", "fallback-triggered"). Displayed in the
            Langfuse trace timeline.
        metadata (Dict[str, Any] | None): Optional arbitrary key-value metadata
            to attach to the event (e.g., {"cache_key": "user:123",
            "reason": "key_expired"}). Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the event was created successfully.
        - event (dict): The created event object including its id.
        - error (str): Error message if the operation failed.

    Note:
        Events are point-in-time markers with no duration. If you need to
        measure how long an operation takes, use lf_create_span or
        lf_create_generation instead.
    """
    if ctx:
        await ctx.info(f"Creating event '{name}' for trace {trace_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.event(
            trace_id=trace_id,
            name=name,
            metadata=metadata,
        )
        return {
            "success": True,
            "event": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_create_score(
    tenant_id: str,
    name: str,
    value: float,
    trace_id: Optional[str] = None,
    observation_id: Optional[str] = None,
    comment: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a score to evaluate a trace or a specific observation within a trace.

    Scores are numeric evaluations attached to traces or individual observations
    (spans, generations, events) in Langfuse. They are used to capture quality
    metrics, user feedback, automated evaluation results, or any quantitative
    assessment of an LLM application's behavior. Langfuse aggregates scores
    across traces for analytics and monitoring dashboards.

    Use this tool after a trace (or part of a trace) has completed and you want
    to record an evaluation. Common examples include user satisfaction ratings,
    relevance scores from automated evaluators, factual accuracy checks, or
    latency-based quality scores.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project will receive
            the score. Must be registered via lf_register_tenant first.
        name (str): Name of the score metric (e.g., "relevance", "accuracy",
            "user-satisfaction", "hallucination-check"). Used for grouping and
            filtering in the Langfuse analytics dashboard.
        value (float): Numeric score value. The scale is user-defined; common
            conventions include 0.0-1.0 for normalized scores, 1-5 for Likert
            scales, or binary 0/1 for pass/fail checks.
        trace_id (str | None): The ID of the trace to score. Either trace_id or
            observation_id (or both) should be provided so the score can be
            associated with the correct object. Defaults to None.
        observation_id (str | None): The ID of a specific observation (span,
            generation, or event) within a trace to score. Use this when the
            evaluation applies to a single step rather than the entire trace.
            Defaults to None.
        comment (str | None): Optional free-text comment explaining the score
            or providing additional context (e.g., "User explicitly said the
            answer was helpful" or "Failed factual accuracy on claim #3").
            Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the score was created successfully.
        - score (dict): The created score object including its id.
        - error (str): Error message if the operation failed.

    Note:
        At least one of trace_id or observation_id should be provided. When
        both are supplied, the score is linked to the specific observation
        within the given trace. Multiple scores with different names can be
        attached to the same trace or observation to capture different
        evaluation dimensions.
    """
    if ctx:
        await ctx.info(f"Creating score '{name}' with value {value}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.score(
            trace_id=trace_id,
            name=name,
            value=value,
            observation_id=observation_id,
            comment=comment,
        )
        return {
            "success": True,
            "score": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_get_trace(
    tenant_id: str,
    trace_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Retrieve a complete trace by its ID from Langfuse.

    Fetches the full trace object including all of its nested observations
    (spans, generations, events) and associated scores. This is useful for
    inspecting the execution history of a traced workflow, debugging issues,
    or building custom analytics on top of raw trace data.

    Use this tool when you need to review what happened during a specific
    traced execution, verify that observations were recorded correctly, or
    extract data from a completed trace for downstream processing.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project contains the
            trace. Must be registered via lf_register_tenant first.
        trace_id (str): The unique identifier of the trace to retrieve. This is
            the id returned by lf_create_trace when the trace was created.

    Returns:
        Dict with:
        - success (bool): Whether the retrieval succeeded.
        - trace (dict): The full trace object, including its name, metadata,
          tags, user_id, session_id, and nested observations (spans,
          generations, events) with their details.
        - error (str): Error message if the operation failed (e.g., trace not
          found or tenant not registered).

    Note:
        The trace must have been flushed to the Langfuse backend before it can
        be retrieved. If the trace was just created, there may be a brief delay
        before it becomes available via this endpoint.
    """
    if ctx:
        await ctx.info(f"Getting trace {trace_id} for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.get_trace(trace_id)
        return {
            "success": True,
            "trace": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


@mcp.tool
async def lf_get_project(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Retrieve project information for a registered Langfuse tenant.

    Fetches metadata about the Langfuse project associated with the given
    tenant, including the project name, ID, and configuration details. This is
    useful for verifying that a tenant's API keys are valid and correctly
    configured, or for displaying project context in a management dashboard.

    Use this tool to confirm connectivity to the Langfuse backend after
    registering a tenant, or to retrieve project details for display or
    logging purposes.

    Args:
        tenant_id (str): Tenant identifier whose Langfuse project information
            to retrieve. Must be registered via lf_register_tenant first.

    Returns:
        Dict with:
        - success (bool): Whether the retrieval succeeded.
        - project (dict): The project object containing details such as the
          project name, ID, and other configuration metadata from the Langfuse
          instance.
        - error (str): Error message if the operation failed (e.g., invalid
          API keys or tenant not registered).

    Note:
        This tool makes an authenticated API call to the Langfuse backend. If
        the tenant's API keys are invalid or expired, the call will fail with
        an authentication error. Use this as a quick connectivity and
        credential validation check after registering a tenant.
    """
    if ctx:
        await ctx.info(f"Getting project info for tenant: {tenant_id}")

    try:
        client_info = await tenant_manager.get_client(tenant_id)
        client = client_info["client"]

        result = await client.get_project()
        return {
            "success": True,
            "project": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("langfuse://{tenant_id}/info")
async def get_tenant_info(tenant_id: str) -> str:
    """Get information about a tenant."""
    try:
        client_info = await tenant_manager.get_client(tenant_id)
        config = client_info["config"]
        return json.dumps({
            "tenant_id": config.tenant_id,
            "base_url": config.base_url,
            "max_concurrent_requests": config.max_concurrent_requests,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("langfuse://info")
def langfuse_info() -> str:
    """Get information about the Langfuse MCP server."""
    return "Langfuse MCP Server - Multi-tenant observability and tracing"


def main():
    """Run the Langfuse server with HTTP transport for remote access."""
    import os
    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8011"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    # This allows each request to work independently without session management
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    # JSON format returns plain JSON instead of SSE format
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(transport=transport, host=host, port=port, stateless_http=stateless, json_response=json_response)


if __name__ == "__main__":
    main()
