"""
MeiliSearch MCP Server (Multi-tenant)

A FastMCP server providing MeiliSearch search engine operations with multi-tenant support.
"""

import json
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    from mcp_servers.meilisearch.tenant_manager import MeiliSearchTenantManager
    from mcp_servers.meilisearch.client import MeiliSearchClientWrapper
except ImportError:
    from .tenant_manager import MeiliSearchTenantManager
    from .client import MeiliSearchClientWrapper

# Initialize tenant manager
tenant_manager = MeiliSearchTenantManager()


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
mcp = FastMCP("MeiliSearch Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "meilisearch-mcp-server",
        "version": "1.0.0",
        "tenant_manager_initialized": tenant_manager is not None
    })


# ============================================================================
# Request/Response Models
# ============================================================================

class SearchRequest(BaseModel):
    """Request model for search operations."""

    tenant_id: str = Field(..., description="Tenant identifier")
    index_uid: str = Field(..., description="Index UID to search")
    query: str = Field(..., description="Search query string")
    limit: int = Field(default=20, description="Maximum number of results")
    offset: int = Field(default=0, description="Offset for pagination")


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def ms_register_tenant(
    tenant_id: str,
    url: str,
    api_key: Optional[str] = None,
    timeout: int = 5,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Register a new MeiliSearch tenant configuration.

    Creates and stores a connection configuration for a MeiliSearch instance,
    identified by a unique tenant ID. Use this tool before performing any other
    MeiliSearch operations for a given tenant. If a tenant with the same ID
    already exists, its configuration will be overwritten.

    Tenant configurations are persisted to Redis (when available) so they
    survive server restarts. Tenants can also be pre-configured via environment
    variables (e.g., MEILISEARCH_TENANT_<ID>_URL, MEILISEARCH_TENANT_<ID>_API_KEY).

    Args:
        tenant_id: Unique identifier for this tenant. Used in all subsequent
            operations to route requests to the correct MeiliSearch instance.
        url: Full URL of the MeiliSearch server, including protocol and port
            (e.g., 'http://meilisearch.meilisearch:7700' or 'http://localhost:7700').
        api_key: Optional MeiliSearch API key (master key or search key). Required
            if the MeiliSearch instance has authentication enabled. Defaults to None.
        timeout: HTTP request timeout in seconds for all operations against this
            tenant's MeiliSearch instance. Defaults to 5.

    Returns:
        Dict with:
        - success (bool): Whether the registration succeeded.
        - message (str): Confirmation message including the tenant ID.
    """
    if ctx:
        await ctx.info(f"Registering MeiliSearch tenant: {tenant_id}")

    try:
        from mcp_servers.meilisearch.tenant_manager import MeiliSearchTenantConfig
    except ImportError:
        from .tenant_manager import MeiliSearchTenantConfig

    config = MeiliSearchTenantConfig(
        tenant_id=tenant_id,
        url=url,
        api_key=api_key,
        timeout=timeout,
    )

    await tenant_manager.register_tenant(config)
    return {"success": True, "message": f"Tenant '{tenant_id}' registered successfully"}


@mcp.tool
async def ms_list_indexes(
    tenant_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all indexes for a MeiliSearch tenant.

    Retrieves metadata for every index on the tenant's MeiliSearch instance.
    Use this to discover available indexes before searching or managing documents.
    This is useful for exploring what data is available or verifying that a
    newly created index appears in the list.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to query. The
            tenant must have been previously registered via ms_register_tenant
            or configured through environment variables.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - tenant_id (str): The tenant identifier that was queried.
        - count (int): Total number of indexes found.
        - indexes (list[dict]): List of index objects, each containing:
            - uid (str): The unique identifier of the index.
            - primary_key (str | None): The primary key attribute, or None if not set.
            - created_at (str): ISO 8601 timestamp of when the index was created.
            - updated_at (str): ISO 8601 timestamp of the last update.
    """
    if ctx:
        await ctx.info(f"Listing indexes for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    indexes = wrapper.list_indexes()

    return {
        "success": True,
        "tenant_id": tenant_id,
        "count": len(indexes),
        "indexes": indexes,
    }


@mcp.tool
async def ms_get_index(
    tenant_id: str,
    index_uid: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information and statistics about a specific MeiliSearch index.

    Retrieves metadata and live statistics for a single index, including the
    document count and current indexing status. Use this to check whether an
    index exists, inspect its primary key, or monitor whether a background
    indexing task has completed.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to query.
        index_uid: The unique identifier (UID) of the index to inspect.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - tenant_id (str): The tenant identifier that was queried.
        - index (dict): Index details containing:
            - uid (str): The unique identifier of the index.
            - primary_key (str | None): The primary key attribute, or None if not set.
            - created_at (str): ISO 8601 timestamp of when the index was created.
            - updated_at (str): ISO 8601 timestamp of the last update.
            - number_of_documents (int): Total number of documents stored in the index.
            - is_indexing (bool): Whether MeiliSearch is currently processing
              documents for this index.
    """
    if ctx:
        await ctx.info(f"Getting index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    index_info = wrapper.get_index(index_uid)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "index": index_info,
    }


@mcp.tool
async def ms_create_index(
    tenant_id: str,
    index_uid: str,
    primary_key: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new search index on a MeiliSearch tenant.

    Creates an empty index with the given UID. An index is a collection of
    documents that can be searched. You must create an index before adding
    documents to it (unless you rely on MeiliSearch's auto-index creation
    during document insertion).

    If a primary_key is not provided, MeiliSearch will attempt to infer it from
    the first document added to the index. It is recommended to set the
    primary_key explicitly to avoid unexpected behavior.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to use.
        index_uid: The unique identifier (UID) for the new index. Must be an
            alphanumeric string (hyphens and underscores allowed). This UID is
            used in all subsequent document and search operations.
        primary_key: Optional name of the attribute that serves as the unique
            document identifier. If not provided, MeiliSearch will try to infer
            it when the first document is added. Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the index was created successfully.
        - tenant_id (str): The tenant identifier that was used.
        - index (dict): Newly created index details containing:
            - uid (str): The unique identifier of the index.
            - primary_key (str | None): The primary key attribute, or None if not set.
            - created_at (str): ISO 8601 timestamp of when the index was created.
            - updated_at (str): ISO 8601 timestamp of the last update.
    """
    if ctx:
        await ctx.info(f"Creating index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.create_index(index_uid, primary_key)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "index": result,
    }


@mcp.tool
async def ms_delete_index(
    tenant_id: str,
    index_uid: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Permanently delete a MeiliSearch index and all of its documents.

    Removes the specified index and every document it contains. This action is
    irreversible -- the index UID can be reused afterward, but all previously
    stored documents and settings will be lost.

    Use this when you need to clean up unused indexes, reset an index completely,
    or remove test data.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to use.
        index_uid: The unique identifier (UID) of the index to delete. The
            index must exist or an error will be raised.

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message including the deleted index UID.
    """
    if ctx:
        await ctx.info(f"Deleting index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    wrapper.delete_index(index_uid)

    return {
        "success": True,
        "message": f"Index '{index_uid}' deleted successfully",
    }


@mcp.tool
async def ms_add_documents(
    tenant_id: str,
    index_uid: str,
    documents: str,  # JSON string of documents array
    primary_key: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add or replace documents in a MeiliSearch index.

    Accepts a JSON-encoded array of document objects and enqueues them for
    indexing. If a document with the same primary key already exists in the
    index, it will be completely replaced by the new version.

    Indexing is asynchronous -- the documents are enqueued as a task and
    processed in the background. The returned task object can be used to track
    progress (e.g., via ms_get_index to check the is_indexing flag). Documents
    may not be immediately searchable after this call returns.

    Common use cases:
    - Bulk-loading data into an index for the first time.
    - Updating existing documents by re-adding them with the same primary key.
    - Incrementally adding new records to an existing dataset.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to use.
        index_uid: The UID of the target index. The index should already exist,
            though MeiliSearch may auto-create it depending on configuration.
        documents: A JSON-encoded string containing an array of document objects.
            Each document must be a JSON object (dict). Example:
            '[{"id": 1, "title": "Foo"}, {"id": 2, "title": "Bar"}]'
        primary_key: Optional name of the attribute that serves as the unique
            document identifier. Only needed if the index does not already have
            a primary key set. Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the documents were successfully enqueued.
        - tenant_id (str): The tenant identifier that was used.
        - task (dict): MeiliSearch task information containing:
            - task_uid (int): Unique task identifier for tracking.
            - index_uid (str): The index the task belongs to.
            - status (str): Task status (typically "enqueued" on success).
            - type (str): The task type (e.g., "documentAdditionOrUpdate").
        - error (str): Present instead of task/tenant_id when the input JSON
          is malformed or is not an array.

    Note:
        The documents parameter must be a valid JSON string representing an
        array of objects. Passing a single object (not wrapped in an array) or
        invalid JSON will return an error without contacting MeiliSearch.
    """
    if ctx:
        await ctx.info(f"Adding documents to index '{index_uid}' for tenant: {tenant_id}")

    try:
        docs = json.loads(documents)
        if not isinstance(docs, list):
            return {"success": False, "error": "Documents must be a JSON array"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.add_documents(index_uid, docs, primary_key)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "task": result,
    }


@mcp.tool
async def ms_search(
    tenant_id: str,
    index_uid: str,
    query: str,
    limit: int = 20,
    offset: int = 0,
    filter: Optional[str] = None,
    sort: Optional[str] = None,  # JSON string array
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search for documents in a MeiliSearch index using full-text search.

    Performs a full-text search query against the specified index and returns
    matching documents ranked by relevance. MeiliSearch provides typo-tolerant,
    prefix-based searching out of the box -- queries like "hary poter" will
    still match "Harry Potter".

    Use this tool whenever you need to find documents by text content. For
    retrieving a single document by its exact ID, use ms_get_document instead.

    Common use cases:
    - Searching a product catalog by name or description.
    - Finding articles or blog posts matching a keyword.
    - Implementing paginated search results with limit and offset.
    - Filtering search results by category, date range, or other facets.
    - Sorting results by a specific attribute (e.g., price, date).

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to query.
        index_uid: The UID of the index to search.
        query: The search query string. MeiliSearch supports typo tolerance
            and prefix matching. An empty string returns all documents (up to
            the limit).
        limit: Maximum number of documents to return. Defaults to 20.
            Maximum value is determined by MeiliSearch server configuration.
        offset: Number of documents to skip for pagination. Defaults to 0.
            Use in combination with limit to paginate through results (e.g.,
            offset=20, limit=20 for the second page).
        filter: Optional filter expression to narrow results. Uses MeiliSearch
            filter syntax (e.g., "genre = 'horror'" or "price > 10 AND
            price < 50"). Filterable attributes must be configured in the
            index settings beforehand. Defaults to None.
        sort: Optional JSON-encoded string array of sort expressions. Each
            element should be "attribute:asc" or "attribute:desc" (e.g.,
            '["price:asc", "rating:desc"]'). Sortable attributes must be
            configured in the index settings. Invalid JSON is silently ignored.
            Defaults to None.

    Returns:
        Dict with:
        - success (bool): Whether the search succeeded.
        - tenant_id (str): The tenant identifier that was queried.
        - query (str): The original search query string.
        - hits (list[dict]): List of matching documents, ordered by relevance
          (or by the specified sort order).
        - estimated_total_hits (int): Estimated total number of documents
          matching the query (may be approximate for large result sets).
        - limit (int): The limit that was applied.
        - offset (int): The offset that was applied.
        - processing_time_ms (int): Time in milliseconds MeiliSearch spent
          processing the search request.

    Note:
        Attributes used in filter and sort expressions must be explicitly
        declared as filterable or sortable in the index settings before use.
        If they are not configured, MeiliSearch will return an error.
    """
    if ctx:
        await ctx.info(f"Searching index '{index_uid}' with query '{query}' for tenant: {tenant_id}")

    sort_list = None
    if sort:
        try:
            sort_list = json.loads(sort)
            if not isinstance(sort_list, list):
                sort_list = None
        except json.JSONDecodeError:
            sort_list = None

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.search(
        index_uid,
        query,
        limit=limit,
        offset=offset,
        filter=filter,
        sort=sort_list,
    )

    return {
        "success": True,
        "tenant_id": tenant_id,
        "query": query,
        "hits": result.get("hits", []),
        "estimated_total_hits": result.get("estimatedTotalHits", 0),
        "limit": limit,
        "offset": offset,
        "processing_time_ms": result.get("processingTimeMs", 0),
    }


@mcp.tool
async def ms_get_document(
    tenant_id: str,
    index_uid: str,
    document_id: str,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Retrieve a single document from a MeiliSearch index by its unique ID.

    Fetches the complete document object identified by its primary key value.
    Use this when you know the exact document ID and need its full contents
    without performing a search. This is faster and more precise than searching
    when you already have the document's identifier.

    Common use cases:
    - Looking up a specific record after finding its ID in search results.
    - Verifying that a document was correctly indexed after an add operation.
    - Retrieving full document details for display or further processing.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to query.
        index_uid: The UID of the index containing the document.
        document_id: The value of the document's primary key field. This is
            passed as a string, but will be matched against the primary key
            attribute of the index (which may be numeric or string-valued).

    Returns:
        Dict with:
        - success (bool): Whether the document was found and retrieved.
        - tenant_id (str): The tenant identifier that was queried.
        - document (dict): The full document object with all its fields. The
          exact structure depends on the data that was indexed.

    Note:
        If no document exists with the given ID, MeiliSearch will raise an
        error. Use ms_search to check for existence when unsure.
    """
    if ctx:
        await ctx.info(f"Getting document '{document_id}' from index '{index_uid}' for tenant: {tenant_id}")

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    document = wrapper.get_document(index_uid, document_id)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "document": document,
    }


@mcp.tool
async def ms_delete_documents(
    tenant_id: str,
    index_uid: str,
    document_ids: str,  # JSON string array
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete one or more documents from a MeiliSearch index by their IDs.

    Removes the specified documents from the index. Like document addition,
    deletion is processed asynchronously -- the returned task can be used to
    track when the operation completes. Documents that do not exist are silently
    ignored (no error is raised for missing IDs).

    Use this when you need to remove specific records from the index without
    affecting other documents. To delete an entire index and all its documents,
    use ms_delete_index instead.

    Common use cases:
    - Removing outdated or incorrect records from the search index.
    - Implementing user-initiated deletion (e.g., a user deletes their content).
    - Cleaning up test data after integration tests.

    Args:
        tenant_id: Tenant identifier whose MeiliSearch instance to use.
        index_uid: The UID of the index containing the documents to delete.
        document_ids: A JSON-encoded string containing an array of document ID
            values (primary key values) to delete. Example: '["doc1", "doc2"]'
            or '[1, 2, 3]' depending on the primary key type.

    Returns:
        Dict with:
        - success (bool): Whether the deletion was successfully enqueued.
        - tenant_id (str): The tenant identifier that was used.
        - task (dict): MeiliSearch task information containing:
            - task_uid (int): Unique task identifier for tracking.
            - index_uid (str): The index the task belongs to.
            - status (str): Task status (typically "enqueued" on success).
            - type (str): The task type (e.g., "documentDeletion").
        - error (str): Present instead of task/tenant_id when the input JSON
          is malformed or is not an array.

    Note:
        The document_ids parameter must be a valid JSON string representing an
        array. Passing a single ID (not wrapped in an array) or invalid JSON
        will return an error without contacting MeiliSearch.
    """
    if ctx:
        await ctx.info(f"Deleting documents from index '{index_uid}' for tenant: {tenant_id}")

    try:
        ids = json.loads(document_ids)
        if not isinstance(ids, list):
            return {"success": False, "error": "Document IDs must be a JSON array"}
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON: {str(e)}"}

    client = await tenant_manager.get_client(tenant_id)
    wrapper = MeiliSearchClientWrapper(client)
    result = wrapper.delete_documents(index_uid, ids)

    return {
        "success": True,
        "tenant_id": tenant_id,
        "task": result,
    }


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("meilisearch://{tenant_id}/info")
async def get_info_resource(tenant_id: str) -> str:
    """Get information about a tenant as a resource."""
    try:
        client = await tenant_manager.get_client(tenant_id)
        wrapper = MeiliSearchClientWrapper(client)
        indexes = wrapper.list_indexes()

        result = {
            "tenant_id": tenant_id,
            "status": "active",
            "index_count": len(indexes),
            "indexes": indexes,
        }
    except Exception as e:
        result = {
            "tenant_id": tenant_id,
            "status": "error",
            "error": str(e),
        }
    return json.dumps(result, indent=2)


@mcp.resource("meilisearch://info")
def server_info() -> str:
    """Get information about the MeiliSearch MCP server."""
    return "MeiliSearch MCP Server - Multi-tenant search engine operations"


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the MeiliSearch server."""
    mcp.run()


if __name__ == "__main__":
    main()
