"""
OpenProject MCP Server

A FastMCP server providing OpenProject API v3 integration.
Uses environment variables for configuration (OPENPROJECT_URL, OPENPROJECT_API_KEY).
"""

import os
import json
import logging
import base64
from typing import Optional, Dict, Any, AsyncIterator, Union, Annotated
from contextlib import asynccontextmanager

from fastmcp import FastMCP, Context
from starlette.requests import Request
from starlette.responses import JSONResponse
from pydantic import field_validator, BeforeValidator

try:
    from mcp_servers.openproject.client import OpenProjectClient
except ImportError:
    from .client import OpenProjectClient

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global client instance
client: Optional[OpenProjectClient] = None


# Lifespan function for initialization and cleanup
@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[None]:
    """Manage server lifespan - initialize OpenProject client from environment variables."""
    global client

    # Initialize: create OpenProject client from environment variables
    base_url = os.getenv("OPENPROJECT_URL")
    api_key = os.getenv("OPENPROJECT_API_KEY")
    proxy = os.getenv("OPENPROJECT_PROXY")  # Optional

    if not base_url or not api_key:
        logger.error("OPENPROJECT_URL or OPENPROJECT_API_KEY not set!")
        logger.info("Please set the required environment variables")
    else:
        client = OpenProjectClient(base_url, api_key, proxy)
        logger.info(f"✅ OpenProject Client initialized for {base_url}")

        # Optional: Test connection on startup
        if os.getenv("TEST_CONNECTION_ON_STARTUP", "false").lower() == "true":
            try:
                await client.test_connection()
                logger.info("✅ API connection test successful!")
            except Exception as e:
                logger.error(f"❌ API connection test failed: {e}")

    yield

    # Cleanup: client doesn't need explicit cleanup (aiohttp sessions are context managers)
    client = None


# Create server with lifespan
mcp = FastMCP("OpenProject Server", lifespan=lifespan)


# ============================================================================
# Health Check
# ============================================================================

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "service": "openproject-mcp-server",
        "version": "1.0.0",
        "client_initialized": client is not None
    })


# ============================================================================
# Tools
# ============================================================================

@mcp.tool
async def test_connection(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Test the connection to the OpenProject API.

    Verifies that the server can reach the configured OpenProject instance and
    that the API key is valid. Use this tool to diagnose connectivity issues or
    confirm that the MCP server is properly configured before issuing other
    commands.

    Args:
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the connection test passed.
        - message (str): Human-readable result description.
        - api_version (str): The _type field from the API root (e.g. "Root").
        - instance_version (str): The OpenProject version string.
        - proxy (str, optional): The proxy URL if one is configured.
    """
    if not client:
        raise Exception("OpenProject Client not initialized. Please set OPENPROJECT_URL and OPENPROJECT_API_KEY environment variables.")

    if ctx:
        await ctx.info("Testing OpenProject API connection...")

    result = await client.test_connection()

    response = {
        "success": True,
        "message": "API connection successful!",
        "api_version": result.get("_type", "Unknown"),
        "instance_version": result.get("instanceVersion", "Unknown"),
    }

    if client.proxy:
        response["proxy"] = client.proxy

    return response


@mcp.tool
async def list_projects(
    active_only: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all projects visible to the authenticated user in OpenProject.

    Retrieves a summary of every project the API key has access to. By default
    only active projects are returned; set active_only to False to include
    archived or inactive projects as well.

    Use this tool when you need to discover project IDs before calling
    project-scoped tools such as list_work_packages, create_work_package, or
    get_available_assignees.

    Args:
        active_only: If True (default), only return projects whose status is
            active. Set to False to include all projects regardless of status.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of projects returned.
        - projects (list[dict]): List of project summaries, each containing:
            - id (int): Project ID.
            - name (str): Project display name.
            - description (str): Plain-text project description.
            - active (bool): Whether the project is currently active.
            - public (bool): Whether the project is publicly visible.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing projects (active_only={active_only})...")

    filters = None
    if active_only:
        filters = json.dumps([{"active": {"operator": "=", "values": ["t"]}}])

    result = await client.get_projects(filters)
    projects = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(projects),
        "projects": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": p.get("description", {}).get("raw", ""),
                "active": p.get("active", False),
                "public": p.get("public", False),
            }
            for p in projects
        ],
    }


def _coerce_to_int(value: Union[int, str, None]) -> Optional[int]:
    """Coerce value to int, handling both int and string inputs."""
    if value is None:
        return None
    if isinstance(value, str):
        return int(value)
    return int(value)


# Type aliases for ID parameters that accept both int and str
# Using Union[int, str] ensures the JSON Schema accepts both types
# The BeforeValidator converts strings to ints at validation time
def _str_to_int(v: Any) -> int:
    """Convert string to int for ID parameters."""
    if isinstance(v, str):
        return int(v)
    return v

def _str_to_int_or_none(v: Any) -> Optional[int]:
    """Convert string to int or None for optional ID parameters."""
    if v is None:
        return None
    if isinstance(v, str):
        return int(v)
    return v

# These types accept both int and str in the schema, converting str to int
IntOrStr = Annotated[Union[int, str], BeforeValidator(_str_to_int)]
OptionalIntOrStr = Annotated[Optional[Union[int, str]], BeforeValidator(_str_to_int_or_none)]


@mcp.tool
async def list_work_packages(
    project_id: OptionalIntOrStr = None,
    status: str = "open",
    offset: OptionalIntOrStr = None,
    page_size: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List work packages with optional filtering by project and status.

    Returns a paginated list of work packages (tasks, stories, epics, bugs,
    etc.) across all projects or scoped to a single project. Results include
    basic metadata such as subject, type, status, assignee, and progress.

    Use this tool for a quick overview of work packages. For more advanced
    filtering (by type, priority, date ranges, custom fields, etc.), prefer
    query_work_packages instead.

    Args:
        project_id: Restrict results to this project. Accepts an integer
            project ID or its string representation. None (default) returns
            work packages across all accessible projects.
        status: Filter by work-package status. Accepted values:
            - "open" (default): Only open / in-progress work packages.
            - "closed": Only completed / closed work packages.
            - "all" or any other value: No status filter applied.
        offset: 1-based offset for pagination. None uses the API default (1).
        page_size: Number of results per page. None uses the API default (20).
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - total (int): Total number of matching work packages (across all pages).
        - count (int): Number of work packages in this page.
        - offset (int): Current pagination offset.
        - page_size (int): Current page size.
        - work_packages (list[dict]): List of work package summaries, each with:
            - id (int): Work package ID.
            - subject (str): Title / subject line.
            - type (str): Work package type name (e.g. "Task", "Epic").
            - status (str): Current status name (e.g. "New", "In progress").
            - project (str): Parent project name.
            - assignee (str): Assigned user name, or "Unassigned".
            - percentage_done (int): Completion percentage (0-100).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing work packages (project_id={project_id}, status={status})...")

    filters = None
    if status == "open":
        filters = json.dumps([{"status_id": {"operator": "o", "values": None}}])
    elif status == "closed":
        filters = json.dumps([{"status_id": {"operator": "c", "values": None}}])

    result = await client.get_work_packages(project_id, filters, offset, page_size)
    work_packages = result.get("_embedded", {}).get("elements", [])

    total = result.get("total", len(work_packages))
    count = result.get("count", len(work_packages))

    return {
        "success": True,
        "total": total,
        "count": count,
        "offset": result.get("offset", offset or 1),
        "page_size": result.get("pageSize", page_size or 20),
        "work_packages": [
            {
                "id": wp.get("id"),
                "subject": wp.get("subject", "No title"),
                "type": wp.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
                "status": wp.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
                "project": wp.get("_embedded", {}).get("project", {}).get("name", "Unknown"),
                "assignee": wp.get("_embedded", {}).get("assignee", {}).get("name", "Unassigned") if wp.get("_embedded", {}).get("assignee") else "Unassigned",
                "percentage_done": wp.get("percentageDone", 0),
            }
            for wp in work_packages
        ],
    }


@mcp.tool
async def list_types(
    project_id: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List available work package types configured in OpenProject.

    Returns every work package type (e.g. Task, Bug, Feature, Epic, Milestone)
    that is enabled globally or within a specific project. Use the returned
    type IDs when creating or updating work packages via create_work_package,
    update_work_package, or query_work_packages.

    When project_id is provided, only types enabled for that project are
    returned. Without a project_id, all globally defined types are listed.

    Args:
        project_id: Optional project ID to scope the type list. If provided,
            only types available in that project are returned. None (default)
            returns all globally configured types.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of types returned.
        - types (list[dict]): List of type definitions, each containing:
            - id (int): Type ID (use this when creating/filtering work packages).
            - name (str): Human-readable type name (e.g. "Task", "Epic").
            - is_default (bool): Whether this type is the default for new work packages.
            - is_milestone (bool): Whether this type represents a milestone (zero-duration).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing work package types (project_id={project_id})...")

    result = await client.get_types(project_id)
    types = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(types),
        "types": [
            {
                "id": t.get("id"),
                "name": t.get("name", "Unnamed"),
                "is_default": t.get("isDefault", False),
                "is_milestone": t.get("isMilestone", False),
            }
            for t in types
        ],
    }


@mcp.tool
async def create_work_package(
    project_id: IntOrStr,
    subject: str,
    type_id: IntOrStr,
    description: Optional[str] = None,
    priority_id: OptionalIntOrStr = None,
    assignee_id: OptionalIntOrStr = None,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new work package (task, story, epic, bug, etc.) in a project.

    Creates a single work package in the specified project. You must provide at
    minimum a project ID, a subject (title), and a type ID. Use list_types to
    discover valid type IDs, list_priorities for priority IDs, and list_users or
    get_available_assignees for assignee IDs.

    To create multiple work packages at once, use bulk_create_work_packages
    instead. To set a parent after creation, call set_work_package_parent.

    Args:
        project_id: ID of the project to create the work package in.
        subject: Title / subject line of the work package.
        type_id: Work package type ID (e.g. Task, Bug, Epic). Use list_types
            to find valid IDs for the target project.
        description: Optional markdown description providing details about the
            work package.
        priority_id: Optional priority ID. Use list_priorities to find valid
            values. If omitted, the instance default priority is used.
        assignee_id: Optional user ID to assign the work package to. Use
            get_available_assignees to find valid user IDs for the project.
        start_date: Optional start date in ISO 8601 format (YYYY-MM-DD).
        due_date: Optional due/finish date in ISO 8601 format (YYYY-MM-DD).
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the creation succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Summary of the created work package containing:
            - id (int): Newly assigned work package ID.
            - subject (str): The subject/title.
            - type (str): Type name.
            - status (str): Initial status name (typically "New").
            - project (str): Parent project name.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Creating work package in project {project_id}...")

    data = {
        "project": project_id,
        "subject": subject,
        "type": type_id,
    }

    if description:
        data["description"] = description
    if priority_id:
        data["priority_id"] = priority_id
    if assignee_id:
        data["assignee_id"] = assignee_id
    if start_date:
        data["startDate"] = start_date
    if due_date:
        data["dueDate"] = due_date

    result = await client.create_work_package(data)

    return {
        "success": True,
        "message": "Work package created successfully",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject", "N/A"),
            "type": result.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
            "status": result.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
            "project": result.get("_embedded", {}).get("project", {}).get("name", "Unknown"),
        },
    }


@mcp.tool
async def get_work_package(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a specific work package by its ID.

    Retrieves the full representation of a single work package, including all
    standard fields, embedded resources (type, status, priority, project,
    assignee), custom field values, dates, description, and HAL links. This
    returns the raw OpenProject API v3 response for maximum detail.

    Use this when you need complete information about a work package, such as
    its full description, custom fields, or linked resources. For a lighter
    listing of multiple work packages, use list_work_packages or
    query_work_packages instead.

    Args:
        work_package_id: The numeric ID of the work package to retrieve.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package (dict): Full OpenProject API v3 work package object
            including all fields, _embedded resources, and _links. Key fields
            include id, subject, description, startDate, dueDate,
            percentageDone, createdAt, updatedAt, and nested type/status/
            priority/project/assignee objects under _embedded.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting work package {work_package_id}...")

    result = await client.get_work_package(work_package_id)

    return {
        "success": True,
        "work_package": result,
    }


@mcp.tool
async def update_work_package(
    work_package_id: IntOrStr,
    subject: Optional[str] = None,
    description: Optional[str] = None,
    type_id: OptionalIntOrStr = None,
    status_id: OptionalIntOrStr = None,
    priority_id: OptionalIntOrStr = None,
    assignee_id: OptionalIntOrStr = None,
    percentage_done: OptionalIntOrStr = None,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update one or more fields on an existing work package.

    Performs a partial update (PATCH) on the specified work package. Only the
    fields you provide will be changed; all other fields remain untouched. At
    least one field should be provided, otherwise the call is a no-op.

    For status-specific transitions with an accompanying comment, consider
    using update_work_package_status instead. For assigning users, you may
    also use the dedicated assign_work_package tool. For custom field updates,
    use update_work_package_custom_fields.

    Note: OpenProject enforces workflow rules on status transitions. Use
    get_work_package_schema to discover which status transitions are allowed
    from the work package's current status before attempting to change it.

    Args:
        work_package_id: ID of the work package to update.
        subject: New title / subject line. None leaves it unchanged.
        description: New markdown description. None leaves it unchanged.
        type_id: New type ID. Use list_types for valid values. None leaves
            it unchanged.
        status_id: New status ID. Use list_statuses or get_work_package_schema
            for valid transitions. None leaves it unchanged.
        priority_id: New priority ID. Use list_priorities for valid values.
            None leaves it unchanged.
        assignee_id: New assignee user ID. Use get_available_assignees for
            valid values. None leaves it unchanged.
        percentage_done: New completion percentage (0-100). None leaves it
            unchanged.
        start_date: New start date in ISO 8601 format (YYYY-MM-DD). None
            leaves it unchanged.
        due_date: New due date in ISO 8601 format (YYYY-MM-DD). None leaves
            it unchanged.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the update succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Full updated work package object from the
            OpenProject API, including all fields, _embedded resources, and
            _links.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Updating work package {work_package_id}...")

    data = {}
    if subject is not None:
        data["subject"] = subject
    if description is not None:
        data["description"] = description
    if type_id is not None:
        data["type_id"] = type_id
    if status_id is not None:
        data["status_id"] = status_id
    if priority_id is not None:
        data["priority_id"] = priority_id
    if assignee_id is not None:
        data["assignee_id"] = assignee_id
    if percentage_done is not None:
        data["percentage_done"] = percentage_done
    if start_date is not None:
        data["startDate"] = start_date
    if due_date is not None:
        data["dueDate"] = due_date

    result = await client.update_work_package(work_package_id, data)

    return {
        "success": True,
        "message": "Work package updated successfully",
        "work_package": result,
    }


@mcp.tool
async def delete_work_package(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Permanently delete a work package from OpenProject.

    Removes the specified work package and all of its associated data
    (comments, activities, time entries linked solely to it, etc.). This
    action is irreversible.

    Deleting a parent work package does NOT automatically delete its children;
    children become top-level work packages. If you need to remove an entire
    subtree, delete the children first.

    Args:
        work_package_id: ID of the work package to delete.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message including the deleted ID.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Deleting work package {work_package_id}...")

    await client.delete_work_package(work_package_id)

    return {
        "success": True,
        "message": f"Work package {work_package_id} deleted successfully",
    }


@mcp.tool
async def list_users(
    active_only: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all users registered in the OpenProject instance.

    Returns user accounts visible to the authenticated API key. By default
    only active users are included; set active_only to False to also list
    locked, invited, or registered users.

    Use this tool to discover user IDs for assignment (assignee_id),
    watchers, or filtering work packages by author/assignee. For
    project-specific assignable users, prefer get_available_assignees.

    Args:
        active_only: If True (default), only return users with "active"
            status. Set to False to include all user statuses.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of users returned.
        - users (list[dict]): List of user summaries, each containing:
            - id (int): User ID.
            - name (str): Display name.
            - email (str): Email address, or "N/A" if hidden.
            - status (str): Account status (e.g. "active", "locked").
            - admin (bool): Whether the user has admin privileges.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing users (active_only={active_only})...")

    filters = None
    if active_only:
        filters = json.dumps([{"status": {"operator": "=", "values": ["active"]}}])

    result = await client.get_users(filters)
    users = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(users),
        "users": [
            {
                "id": u.get("id"),
                "name": u.get("name", "Unnamed"),
                "email": u.get("email", "N/A"),
                "status": u.get("status", "Unknown"),
                "admin": u.get("admin", False),
            }
            for u in users
        ],
    }


@mcp.tool
async def get_user(
    user_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a specific user by their ID.

    Retrieves the full user profile from the OpenProject API, including name,
    email, status, admin flag, avatar URL, creation date, and any other
    profile fields. Returns the raw API response for maximum detail.

    Use this when you need complete information about a particular user,
    for example to verify their email, check admin status, or inspect
    their profile metadata.

    Args:
        user_id: The numeric ID of the user to retrieve.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - user (dict): Full OpenProject API v3 user object including all
            fields such as id, name, email, login, status, admin, avatar,
            createdAt, updatedAt, and _links.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting user {user_id}...")

    result = await client.get_user(user_id)

    return {
        "success": True,
        "user": result,
    }


@mcp.tool
async def list_statuses(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """List all available work package statuses defined in OpenProject.

    Returns every status configured in the instance (e.g. "New",
    "In progress", "Closed", "Rejected"). Use the returned status IDs when
    updating work package statuses via update_work_package or
    update_work_package_status.

    Note: Not all statuses may be reachable from a given work package's
    current status due to workflow rules. Use get_work_package_schema to
    see which transitions are allowed for a specific work package.

    Args:
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of statuses returned.
        - statuses (list[dict]): List of status definitions, each containing:
            - id (int): Status ID (use this in update calls).
            - name (str): Human-readable status name.
            - is_default (bool): Whether this is the default status for new
                work packages.
            - is_closed (bool): Whether this status represents a closed/done
                state. Useful for determining if a work package is complete.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing work package statuses...")

    result = await client.get_statuses()
    statuses = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(statuses),
        "statuses": [
            {
                "id": s.get("id"),
                "name": s.get("name", "Unnamed"),
                "is_default": s.get("isDefault", False),
                "is_closed": s.get("isClosed", False),
            }
            for s in statuses
        ],
    }


@mcp.tool
async def list_priorities(ctx: Optional[Context] = None) -> Dict[str, Any]:
    """List all available work package priorities defined in OpenProject.

    Returns the full set of priority levels (e.g. "Low", "Normal", "High",
    "Immediate"). Use the returned priority IDs when creating or updating
    work packages via create_work_package or update_work_package.

    Args:
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of priorities returned.
        - priorities (list[dict]): List of priority definitions, each with:
            - id (int): Priority ID (use this in create/update calls).
            - name (str): Human-readable priority name (e.g. "High").
            - is_default (bool): Whether this is the default priority for
                new work packages.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing work package priorities...")

    result = await client.get_priorities()
    priorities = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(priorities),
        "priorities": [
            {
                "id": p.get("id"),
                "name": p.get("name", "Unnamed"),
                "is_default": p.get("isDefault", False),
            }
            for p in priorities
        ],
    }


@mcp.tool
async def get_project(
    project_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get detailed information about a specific project by its ID.

    Retrieves the full project representation from the OpenProject API,
    including name, identifier, description, status, visibility, creation
    date, and all linked resources. Returns the raw API response for
    maximum detail.

    Use this when you need complete project metadata beyond what
    list_projects provides, such as the project description, custom fields,
    or linked modules.

    Args:
        project_id: The numeric ID of the project to retrieve.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - project (dict): Full OpenProject API v3 project object including
            all fields such as id, name, identifier, description, active,
            public, status, createdAt, updatedAt, and _links.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting project {project_id}...")

    result = await client.get_project(project_id)

    return {
        "success": True,
        "project": result,
    }


@mcp.tool
async def create_project(
    name: str,
    identifier: str,
    description: Optional[str] = None,
    public: Optional[bool] = None,
    status: Optional[str] = None,
    parent_id: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a new project in OpenProject.

    Creates a top-level or sub-project. The identifier must be unique across
    the entire OpenProject instance and is used in URLs. It should consist of
    lowercase letters, digits, and hyphens only.

    Args:
        name: Display name for the project (e.g. "Mobile App Redesign").
        identifier: URL-safe unique identifier (e.g. "mobile-app-redesign").
            Must be lowercase with hyphens, no spaces. Cannot be changed
            after creation in some OpenProject versions.
        description: Optional markdown description of the project's purpose.
        public: Whether the project is publicly visible. None uses the
            instance default (typically False).
        status: Optional project status string (e.g. "on_track",
            "at_risk", "off_track"). None uses the default.
        parent_id: Optional parent project ID to create this as a
            sub-project. None creates a top-level project.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the creation succeeded.
        - message (str): Confirmation message.
        - project (dict): Full API response for the newly created project,
            including its assigned id, name, identifier, and all other fields.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Creating project '{name}'...")

    data = {
        "name": name,
        "identifier": identifier,
    }

    if description:
        data["description"] = description
    if public is not None:
        data["public"] = public
    if status:
        data["status"] = status
    if parent_id:
        data["parent_id"] = parent_id

    result = await client.create_project(data)

    return {
        "success": True,
        "message": "Project created successfully",
        "project": result,
    }


@mcp.tool
async def update_project(
    project_id: IntOrStr,
    name: Optional[str] = None,
    identifier: Optional[str] = None,
    description: Optional[str] = None,
    public: Optional[bool] = None,
    status: Optional[str] = None,
    parent_id: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update one or more fields on an existing project.

    Performs a partial update (PATCH) on the specified project. Only the
    fields you provide will be changed; all other fields remain untouched.

    Note: Changing the identifier may break existing bookmarks or
    integrations that reference the project by its old identifier.

    Args:
        project_id: ID of the project to update.
        name: New display name. None leaves it unchanged.
        identifier: New URL-safe identifier. None leaves it unchanged.
            Use with caution as this changes the project's URL.
        description: New markdown description. None leaves it unchanged.
        public: New visibility setting. None leaves it unchanged.
        status: New project status (e.g. "on_track", "at_risk",
            "off_track"). None leaves it unchanged.
        parent_id: New parent project ID, or use to move a project under
            a different parent. None leaves it unchanged.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the update succeeded.
        - message (str): Confirmation message.
        - project (dict): Full updated project object from the API.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Updating project {project_id}...")

    data = {}
    if name is not None:
        data["name"] = name
    if identifier is not None:
        data["identifier"] = identifier
    if description is not None:
        data["description"] = description
    if public is not None:
        data["public"] = public
    if status is not None:
        data["status"] = status
    if parent_id is not None:
        data["parent_id"] = parent_id

    result = await client.update_project(project_id, data)

    return {
        "success": True,
        "message": "Project updated successfully",
        "project": result,
    }


@mcp.tool
async def delete_project(
    project_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Permanently delete a project and all its contents from OpenProject.

    Removes the specified project along with all of its work packages, wiki
    pages, forums, time entries, and other project-scoped data. This action
    is irreversible.

    Sub-projects are NOT automatically deleted; they become top-level
    projects. Delete sub-projects first if you want to remove them as well.

    Args:
        project_id: ID of the project to delete.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message including the deleted project ID.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Deleting project {project_id}...")

    await client.delete_project(project_id)

    return {
        "success": True,
        "message": f"Project {project_id} deleted successfully",
    }


# ============================================================================
# Priority 1: Hierarchy & Relationships Tools
# ============================================================================

@mcp.tool
async def set_work_package_parent(
    work_package_id: IntOrStr,
    parent_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Set a parent work package for a work package, establishing a hierarchy.

    Creates or updates the parent-child relationship so that the specified
    work package becomes a child of the given parent. OpenProject supports
    multi-level hierarchies such as Epic > Feature > Story > Task.

    If the work package already has a different parent, this replaces the
    existing parent relationship. To remove a parent without setting a new
    one, use remove_work_package_parent instead.

    Note: Both work packages must be in the same project, or cross-project
    parent-child must be enabled in the OpenProject configuration.

    Args:
        work_package_id: ID of the work package that will become the child.
        parent_id: ID of the work package that will become the parent.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Summary with:
            - id (int): The child work package ID.
            - subject (str): The child's subject/title.
            - parent_id (int): The newly set parent ID.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Setting parent {parent_id} for work package {work_package_id}...")

    result = await client.set_work_package_parent(work_package_id, parent_id)

    return {
        "success": True,
        "message": f"Parent set successfully for work package {work_package_id}",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject"),
            "parent_id": parent_id,
        },
    }


@mcp.tool
async def remove_work_package_parent(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove the parent relationship from a work package, making it top-level.

    Clears the parent link so the work package becomes a root-level item
    with no parent in the hierarchy. Any children of this work package are
    not affected and remain as its children.

    Args:
        work_package_id: ID of the work package whose parent link to remove.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Summary with:
            - id (int): The work package ID.
            - subject (str): The work package subject/title.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Removing parent from work package {work_package_id}...")

    result = await client.remove_work_package_parent(work_package_id)

    return {
        "success": True,
        "message": f"Parent removed from work package {work_package_id}",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject"),
        },
    }


@mcp.tool
async def get_work_package_children(
    parent_id: IntOrStr,
    project_id: OptionalIntOrStr = None,
    type_id: OptionalIntOrStr = None,
    status: Optional[str] = None,
    include_descendants: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get child work packages of a given parent work package.

    Retrieves all direct children of the specified parent work package. When
    include_descendants is True, the entire subtree is returned (children,
    grandchildren, etc.). Results can be further filtered by project, type,
    or status.

    Common use cases:
    - List all stories under an epic to review sprint scope.
    - List all tasks under a story to check completeness.
    - Verify all children are closed before closing a parent.
    - Get the full breakdown of an epic across multiple levels.

    Args:
        parent_id: ID of the parent work package whose children to retrieve.
        project_id: Optional project ID filter. Only return children
            belonging to this project (useful for cross-project hierarchies).
        type_id: Optional type ID filter. Only return children of this
            work package type (e.g. only Tasks, only Stories).
        status: Optional status filter:
            - "open": Only return children with non-closed statuses.
            - "closed": Only return children with closed statuses.
            - None or any other value: Return all children regardless of status.
        include_descendants: If True, recursively include all descendants
            (children of children, etc.), not just direct children. Default
            is False (direct children only).
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - parent_id (int): The parent work package ID queried.
        - count (int): Number of children/descendants returned.
        - include_descendants (bool): Whether descendants were included.
        - children (list[dict]): List of child work packages, each with:
            - id (int): Child work package ID.
            - subject (str): Child subject/title.
            - type (str): Type name (e.g. "Task", "Story").
            - status (str): Current status name.
            - assignee (str): Assigned user name, or "Unassigned".
            - percentage_done (int): Completion percentage (0-100).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting children of work package {parent_id}...")

    result = await client.list_work_package_children(parent_id, include_descendants)
    children = result.get("_embedded", {}).get("elements", [])

    # Apply additional filters in memory if specified
    if type_id:
        children = [c for c in children
                   if c.get("_embedded", {}).get("type", {}).get("id") == type_id]

    if status == "open":
        children = [c for c in children
                   if not c.get("_embedded", {}).get("status", {}).get("isClosed", False)]
    elif status == "closed":
        children = [c for c in children
                   if c.get("_embedded", {}).get("status", {}).get("isClosed", False)]

    if project_id:
        children = [c for c in children
                   if c.get("_embedded", {}).get("project", {}).get("id") == project_id]

    return {
        "success": True,
        "parent_id": parent_id,
        "count": len(children),
        "include_descendants": include_descendants,
        "children": [
            {
                "id": c.get("id"),
                "subject": c.get("subject"),
                "type": c.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
                "status": c.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
                "assignee": c.get("_embedded", {}).get("assignee", {}).get("name", "Unassigned")
                           if c.get("_embedded", {}).get("assignee") else "Unassigned",
                "percentage_done": c.get("percentageDone", 0),
            }
            for c in children
        ],
    }


@mcp.tool
async def get_work_package_hierarchy(
    work_package_id: IntOrStr,
    include_ancestors: bool = True,
    include_descendants: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the full hierarchy tree for a work package (ancestors and descendants).

    Retrieves the complete hierarchical context of a work package, including
    all ancestor work packages (parent, grandparent, etc. up to the root)
    and all descendant work packages (children, grandchildren, etc. down to
    the leaves). This provides a complete picture of where a work package
    sits in the project structure.

    Common use cases:
    - Visualize the full hierarchy path (e.g. Epic > Feature > Story > Task).
    - Understand the context of a work package within the project plan.
    - Generate tree views or breadcrumb navigation for work packages.
    - Audit the decomposition of an epic into its constituent work items.

    Args:
        work_package_id: ID of the work package to get the hierarchy for.
        include_ancestors: If True (default), include all ancestor work
            packages up to the root. Set to False to skip ancestors.
        include_descendants: If True (default), include all descendant work
            packages down to the leaves. Set to False to skip descendants.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package (dict): The target work package summary with id,
            subject, type, and status.
        - ancestors (list[dict]): Ordered list of ancestor work packages
            from the immediate parent to the root, each with id, subject,
            type, and status.
        - ancestors_count (int): Number of ancestors.
        - descendants (list[dict]): List of all descendant work packages,
            each with id, subject, type, and status.
        - descendants_count (int): Number of descendants.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting hierarchy for work package {work_package_id}...")

    result = await client.get_work_package_hierarchy(
        work_package_id, include_ancestors, include_descendants
    )

    wp = result.get("work_package", {})
    ancestors = result.get("ancestors", [])
    descendants = result.get("descendants", [])

    def format_wp(w):
        return {
            "id": w.get("id"),
            "subject": w.get("subject"),
            "type": w.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
            "status": w.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
        }

    return {
        "success": True,
        "work_package": format_wp(wp),
        "ancestors": [format_wp(a) for a in ancestors],
        "ancestors_count": len(ancestors),
        "descendants": [format_wp(d) for d in descendants],
        "descendants_count": len(descendants),
    }


# ============================================================================
# Priority 2: Bulk Operations Tools
# ============================================================================

@mcp.tool
async def bulk_create_work_packages(
    project_id: IntOrStr,
    work_packages: str,  # JSON string of work package definitions
    continue_on_error: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create multiple work packages in a single batch operation.

    Accepts a JSON array of work package definitions and creates them all
    within the specified project. This is significantly more efficient than
    calling create_work_package repeatedly when you need to create many
    items at once (e.g. populating a sprint backlog, creating a task
    breakdown for a story, or setting up a project template).

    Work packages are created sequentially. If continue_on_error is False
    (the default), creation stops at the first failure. If True, failures
    are recorded and remaining items are still attempted.

    Args:
        project_id: Project ID where all work packages will be created.
        work_packages: JSON string containing an array of work package
            definitions. Each element is an object with:
            - subject (str, required): Title of the work package.
            - type_id (int, required): Work package type ID.
            - description (str, optional): Markdown description.
            - parent_id (int, optional): Parent work package ID for hierarchy.
            - status_id (int, optional): Initial status ID.
            - priority_id (int, optional): Priority ID.
            - assignee_id (int, optional): Assignee user ID.
            - startDate (str, optional): Start date (YYYY-MM-DD).
            - dueDate (str, optional): Due date (YYYY-MM-DD).
            Example:
            [
                {"subject": "Task 1", "type_id": 36, "description": "First task"},
                {"subject": "Task 2", "type_id": 36, "parent_id": 100}
            ]
        continue_on_error: If True, continue creating remaining work
            packages even if one fails. If False (default), stop at the
            first error.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the overall operation succeeded (all items
            created without errors).
        - created (list): List of successfully created work package summaries.
        - errors (list): List of error details for any failed creations.
        - created_count (int): Number of successfully created work packages.
        - error_count (int): Number of failed creations.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Bulk creating work packages in project {project_id}...")

    # Parse JSON string to list
    try:
        wp_list = json.loads(work_packages)
        if not isinstance(wp_list, list):
            raise ValueError("work_packages must be a JSON array")
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in work_packages: {str(e)}",
        }

    result = await client.bulk_create_work_packages(project_id, wp_list, continue_on_error)

    return result


@mcp.tool
async def bulk_update_work_packages(
    updates: str,  # JSON string of updates
    continue_on_error: bool = False,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update multiple work packages in a single batch operation.

    Accepts a JSON array of update objects, each specifying a work package ID
    and the fields to change. This is far more efficient than calling
    update_work_package repeatedly when you need to make changes across many
    work packages (e.g. closing all tasks in a sprint, reassigning a batch,
    or updating progress on multiple items).

    Updates are applied sequentially. If continue_on_error is False (the
    default), the operation stops at the first failure. If True, failures
    are recorded and remaining updates are still attempted.

    Args:
        updates: JSON string containing an array of update objects. Each
            element must include:
            - work_package_id (int, required): ID of the work package to update.
            And one or more fields to change:
            - subject (str, optional): New title.
            - description (str, optional): New markdown description.
            - type_id (int, optional): New type ID.
            - status_id (int, optional): New status ID.
            - priority_id (int, optional): New priority ID.
            - assignee_id (int, optional): New assignee user ID.
            - parent_id (int, optional): New parent work package ID.
            - percentage_done (int, optional): New progress percentage (0-100).
            - startDate (str, optional): New start date (YYYY-MM-DD).
            - dueDate (str, optional): New due date (YYYY-MM-DD).
            Example:
            [
                {"work_package_id": 100, "status_id": 72},
                {"work_package_id": 101, "assignee_id": 5, "percentage_done": 50}
            ]
        continue_on_error: If True, continue updating remaining work
            packages even if one fails. If False (default), stop at the
            first error.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the overall operation succeeded (all items
            updated without errors).
        - updated (list): List of successfully updated work package summaries.
        - errors (list): List of error details for any failed updates.
        - updated_count (int): Number of successfully updated work packages.
        - error_count (int): Number of failed updates.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Bulk updating work packages...")

    # Parse JSON string to list
    try:
        update_list = json.loads(updates)
        if not isinstance(update_list, list):
            raise ValueError("updates must be a JSON array")
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in updates: {str(e)}",
        }

    result = await client.bulk_update_work_packages(update_list, continue_on_error)

    return result


# ============================================================================
# Priority 3: Enhanced Querying & Filtering Tools
# ============================================================================

@mcp.tool
async def query_work_packages(
    project_id: OptionalIntOrStr = None,
    filters: Optional[str] = None,
    sort_by: Optional[str] = None,
    group_by: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Advanced work package query with flexible filtering, sorting, and grouping.

    Provides full control over work package queries using OpenProject's filter
    syntax. This is the most powerful query tool and supports filtering on
    any standard or custom field with a variety of operators.

    For simple subject text searches, prefer search_work_packages. For basic
    listing with just project/status filtering, prefer list_work_packages.

    Common use cases:
    - Find all open stories under a specific epic.
    - List tasks assigned to a user sorted by due date.
    - Search work packages by subject pattern.
    - Filter by date ranges, custom fields, or multiple criteria.
    - Group results by status, type, or assignee for reporting.

    Args:
        project_id: Optional project ID to scope the query to a single
            project. None queries across all accessible projects.
        filters: Optional JSON string containing an array of filter objects.
            Each filter is a dict with a field name mapped to an operator
            and values. Example:
            [
                {"type": {"operator": "=", "values": ["41"]}},
                {"status": {"operator": "o", "values": null}}
            ]
            Common operators:
            - "=" : Equals (exact match).
            - "!" : Not equals.
            - "o" : Open status (use with status_id, values should be null).
            - "c" : Closed status (use with status_id, values should be null).
            - "~" : Contains (for text fields like subject, description).
            - ">=" : Greater than or equal (for dates, numbers).
            - "<=" : Less than or equal (for dates, numbers).
            - "**" : All (matches any value, useful for "is set" checks).
            - "!*" : None (matches null/empty, for "is not set" checks).
            Common filter fields:
            - type, status, status_id, priority, assignee, author, responsible
            - parent, project, version
            - subject, description (use ~ operator for text search)
            - created_at, updated_at (use date operators like >=, <=)
            - customField{N} (for custom fields by their ID)
        sort_by: Optional sort specification as "field:direction", e.g.
            "subject:asc", "updated_at:desc", "priority:asc". Only one
            sort criterion is supported per query.
        group_by: Optional field name to group results by, e.g. "status",
            "type", "assignee", "priority". Useful for summary views.
        page: Page number for pagination (1-based). Default is 1.
        page_size: Number of results per page (1-100). Default is 20.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - total (int): Total matching work packages across all pages.
        - count (int): Number of work packages in this page.
        - page (int): Current page number.
        - page_size (int): Items per page.
        - total_pages (int): Total number of pages.
        - work_packages (list[dict]): List of work package summaries, each with:
            - id (int): Work package ID.
            - subject (str): Title / subject line.
            - type (str): Type name and type_id.
            - status (str): Status name and status_id.
            - priority (str): Priority name.
            - project (str): Project name.
            - assignee (str): Assignee name or "Unassigned".
            - percentage_done (int): Completion percentage.
            - start_date (str | None): Start date (YYYY-MM-DD).
            - due_date (str | None): Due date (YYYY-MM-DD).
            - created_at (str): ISO 8601 creation timestamp.
            - updated_at (str): ISO 8601 last update timestamp.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Querying work packages...")

    # Parse filters if provided as JSON string
    filter_list = None
    if filters:
        try:
            filter_list = json.loads(filters)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON in filters: {str(e)}",
            }

    # Calculate offset from page
    offset = (page - 1) * page_size + 1

    result = await client.query_work_packages(
        project_id=project_id,
        filters=filter_list,
        sort_by=sort_by,
        group_by=group_by,
        offset=offset,
        page_size=page_size,
    )

    work_packages = result.get("_embedded", {}).get("elements", [])
    total = result.get("total", len(work_packages))

    return {
        "success": True,
        "total": total,
        "count": len(work_packages),
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total else 1,
        "work_packages": [
            {
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "type": wp.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
                "type_id": wp.get("_embedded", {}).get("type", {}).get("id"),
                "status": wp.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
                "status_id": wp.get("_embedded", {}).get("status", {}).get("id"),
                "priority": wp.get("_embedded", {}).get("priority", {}).get("name", "Unknown"),
                "project": wp.get("_embedded", {}).get("project", {}).get("name", "Unknown"),
                "assignee": wp.get("_embedded", {}).get("assignee", {}).get("name", "Unassigned")
                           if wp.get("_embedded", {}).get("assignee") else "Unassigned",
                "percentage_done": wp.get("percentageDone", 0),
                "start_date": wp.get("startDate"),
                "due_date": wp.get("dueDate"),
                "created_at": wp.get("createdAt"),
                "updated_at": wp.get("updatedAt"),
            }
            for wp in work_packages
        ],
    }


@mcp.tool
async def search_work_packages(
    query: str,
    project_id: OptionalIntOrStr = None,
    type_ids: Optional[str] = None,
    status: str = "open",
    limit: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Search work packages by subject text with optional filters.

    Performs a text search on work package subjects using the "contains"
    operator. This is a convenience wrapper around query_work_packages
    optimized for quick keyword searches.

    For more advanced filtering (date ranges, custom fields, complex
    multi-criteria queries), use query_work_packages instead.

    Args:
        query: Search text to match against work package subjects. Uses
            a "contains" match, so "auth" will match "Authentication",
            "OAuth setup", etc. Case sensitivity depends on the database
            configuration.
        project_id: Optional project ID to restrict the search scope.
            None searches across all accessible projects.
        type_ids: Optional comma-separated string of type IDs to filter by.
            For example, "1,2,3" to only search Tasks, Bugs, and Features.
            Use list_types to discover valid type IDs.
        status: Filter by status:
            - "open" (default): Only search open/in-progress work packages.
            - "closed": Only search closed/done work packages.
            - "all" or any other value: Search all work packages.
        limit: Maximum number of results to return. Default is 20.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the search succeeded.
        - query (str): The search text that was used.
        - count (int): Number of matching work packages returned.
        - work_packages (list[dict]): List of matching work packages, each with:
            - id (int): Work package ID.
            - subject (str): Title / subject line.
            - type (str): Type name.
            - status (str): Status name.
            - project (str): Project name.
            - description_preview (str): First 200 characters of the
                description (truncated with "..."), or empty string.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Searching work packages for '{query}'...")

    # Build filters - use subject filter with contains operator
    filters = [{"subject": {"operator": "~", "values": [query]}}]

    if status == "open":
        filters.append({"status_id": {"operator": "o", "values": None}})
    elif status == "closed":
        filters.append({"status_id": {"operator": "c", "values": None}})

    if type_ids:
        type_id_list = [t.strip() for t in type_ids.split(",")]
        filters.append({"type": {"operator": "=", "values": type_id_list}})

    result = await client.query_work_packages(
        project_id=project_id,
        filters=filters,
        page_size=limit,
    )

    work_packages = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "query": query,
        "count": len(work_packages),
        "work_packages": [
            {
                "id": wp.get("id"),
                "subject": wp.get("subject"),
                "type": wp.get("_embedded", {}).get("type", {}).get("name", "Unknown"),
                "status": wp.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
                "project": wp.get("_embedded", {}).get("project", {}).get("name", "Unknown"),
                "description_preview": (wp.get("description", {}).get("raw", "")[:200] + "...")
                                       if wp.get("description", {}).get("raw", "") else "",
            }
            for wp in work_packages
        ],
    }


# ============================================================================
# Priority 4: Work Package Relations Tools
# ============================================================================

@mcp.tool
async def create_work_package_relation(
    from_work_package_id: IntOrStr,
    to_work_package_id: IntOrStr,
    relation_type: str,
    description: Optional[str] = None,
    lag: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Create a typed relationship between two work packages.

    Establishes a directed relation from one work package to another. Relations
    are distinct from parent-child hierarchy (use set_work_package_parent for
    that). Relations model dependencies, duplicates, and other cross-cutting
    links between work packages.

    The relation is directional: the "from" work package is the source and the
    "to" work package is the target. The semantics depend on the relation_type.
    For example, "blocks" means the "from" work package blocks the "to" work
    package.

    Args:
        from_work_package_id: ID of the source (originating) work package.
        to_work_package_id: ID of the target (destination) work package.
        relation_type: The type of relation to create. Valid values:
            - "relates": General bidirectional relation (no dependency).
            - "duplicates": Source is a duplicate of target.
            - "duplicated": Source is duplicated by target.
            - "blocks": Source blocks target (target cannot proceed).
            - "blocked": Source is blocked by target.
            - "precedes": Source must finish before target can start.
            - "follows": Source follows target (target must finish first).
            - "includes": Source includes target.
            - "partof": Source is part of target.
            - "requires": Source requires target.
            - "required": Source is required by target.
        description: Optional text description explaining the nature of the
            relationship.
        lag: Optional lag in days, applicable to "precedes" and "follows"
            relations. Specifies a waiting period between the two work
            packages (e.g. lag=2 means a 2-day gap is required).
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the relation was created.
        - message (str): Confirmation message.
        - relation (dict): Created relation details with:
            - id (int): Relation ID.
            - type (str): Relation type.
            - from_id (int): Source work package ID.
            - to_id (int): Target work package ID.
            - description (str | None): Relation description.
            - lag (int | None): Lag in days, if applicable.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Creating {relation_type} relation from {from_work_package_id} to {to_work_package_id}...")

    data = {
        "from_id": from_work_package_id,
        "to_id": to_work_package_id,
        "relation_type": relation_type,
    }

    if description:
        data["description"] = description
    if lag is not None:
        data["lag"] = lag

    result = await client.create_work_package_relation(data)

    return {
        "success": True,
        "message": f"Relation created successfully",
        "relation": {
            "id": result.get("id"),
            "type": result.get("type"),
            "from_id": from_work_package_id,
            "to_id": to_work_package_id,
            "description": result.get("description"),
            "lag": result.get("lag"),
        },
    }


@mcp.tool
async def list_work_package_relations(
    work_package_id: OptionalIntOrStr = None,
    relation_type: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List relations for a work package or all relations in the instance.

    Retrieves work package relations, optionally scoped to a specific work
    package and/or filtered by relation type. Use this to understand
    dependencies, blockers, and other links between work packages.

    Common use cases:
    - View all dependencies and blockers for a work package before starting.
    - Find all "precedes" relations to understand a dependency chain.
    - Check what is blocking a specific work package.
    - Audit the relationship graph of a project.

    Args:
        work_package_id: Optional work package ID to get relations for. If
            provided, only relations involving this work package (as source
            or target) are returned. None returns all accessible relations.
        relation_type: Optional relation type to filter by. Valid values
            include "relates", "blocks", "blocked", "precedes", "follows",
            "duplicates", "duplicated", "includes", "partof", "requires",
            "required". None returns all relation types.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package_id (int | None): The queried work package ID, if any.
        - count (int): Number of relations returned.
        - relations (list[dict]): List of relation objects, each with:
            - id (int): Relation ID (use for deletion via
                delete_work_package_relation).
            - type (str): Relation type (e.g. "blocks", "precedes").
            - from_id (str): Source work package ID (extracted from HAL link).
            - to_id (str): Target work package ID (extracted from HAL link).
            - description (str | None): Relation description.
            - lag (int | None): Lag in days for temporal relations.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing work package relations...")

    # Build filters for relation type if specified
    filters = None
    if relation_type:
        filters = json.dumps([{"type": {"operator": "=", "values": [relation_type]}}])

    result = await client.list_work_package_relations(work_package_id, filters)
    relations = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "work_package_id": work_package_id,
        "count": len(relations),
        "relations": [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "from_id": r.get("_links", {}).get("from", {}).get("href", "").split("/")[-1],
                "to_id": r.get("_links", {}).get("to", {}).get("href", "").split("/")[-1],
                "description": r.get("description"),
                "lag": r.get("lag"),
            }
            for r in relations
        ],
    }


@mcp.tool
async def delete_work_package_relation(
    relation_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Delete an existing relation between two work packages.

    Permanently removes the specified relation. Use list_work_package_relations
    to find relation IDs. This does not delete the work packages themselves,
    only the link between them.

    Args:
        relation_id: ID of the relation to delete. Obtain this from the
            list_work_package_relations response.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message including the deleted relation ID.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Deleting relation {relation_id}...")

    await client.delete_work_package_relation(relation_id)

    return {
        "success": True,
        "message": f"Relation {relation_id} deleted successfully",
    }


# ============================================================================
# Priority 5: Activities & Comments Tools
# ============================================================================

@mcp.tool
async def add_work_package_comment(
    work_package_id: IntOrStr,
    comment: str,
    notify: bool = True,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a comment (activity note) to a work package.

    Posts a new comment on the specified work package, which appears in its
    activity log. Comments support markdown formatting and can optionally
    trigger email notifications to all watchers.

    Common use cases:
    - Document progress updates or status changes.
    - Record technical decisions or design rationale.
    - Ask questions or communicate with team members.
    - Leave notes for handoffs between team members.

    Args:
        work_package_id: ID of the work package to comment on.
        comment: The comment text. Supports markdown formatting including
            headings, bold, italic, code blocks, lists, and links.
        notify: Whether to send email notifications to watchers of the
            work package. Default is True. Set to False for minor or
            automated comments that do not warrant notifications.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the comment was added.
        - message (str): Confirmation message.
        - activity (dict): The created activity entry with:
            - id (int): Activity ID.
            - comment (str): The raw comment text.
            - created_at (str): ISO 8601 timestamp of when the comment was
                posted.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Adding comment to work package {work_package_id}...")

    result = await client.add_work_package_comment(work_package_id, comment, notify)

    return {
        "success": True,
        "message": "Comment added successfully",
        "activity": {
            "id": result.get("id"),
            "comment": result.get("comment", {}).get("raw", comment),
            "created_at": result.get("createdAt"),
        },
    }


@mcp.tool
async def list_work_package_activities(
    work_package_id: IntOrStr,
    limit: int = 20,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List the activity log (comments and change history) for a work package.

    Retrieves the chronological list of activities on a work package, including
    user comments, field changes (status updates, reassignments, etc.), and
    other modifications. Each activity includes who made the change and when.

    Common use cases:
    - Review the full history of a work package.
    - Read all comments and discussions.
    - Track who changed what and when for auditing purposes.
    - Understand the progression of a work package over time.

    Args:
        work_package_id: ID of the work package whose activity log to retrieve.
        limit: Maximum number of activity entries to return. Default is 20.
            Activities are returned in chronological order.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package_id (int): The queried work package ID.
        - count (int): Number of activity entries returned.
        - activities (list[dict]): List of activity entries, each with:
            - id (int): Activity ID.
            - comment (str): Comment text (empty string if the activity was
                a field change without a comment).
            - user (str): Name of the user who made the change.
            - created_at (str): ISO 8601 timestamp of the activity.
            - version (int): Activity version number (increments with each
                change to the work package).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing activities for work package {work_package_id}...")

    result = await client.get_work_package_activities(work_package_id, page_size=limit)
    activities = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "work_package_id": work_package_id,
        "count": len(activities),
        "activities": [
            {
                "id": a.get("id"),
                "comment": a.get("comment", {}).get("raw", "") if a.get("comment") else "",
                "user": a.get("_embedded", {}).get("user", {}).get("name", "Unknown"),
                "created_at": a.get("createdAt"),
                "version": a.get("version"),
            }
            for a in activities
        ],
    }


# ============================================================================
# Priority 6: Watchers & Assignments Tools
# ============================================================================

@mcp.tool
async def add_work_package_watcher(
    work_package_id: IntOrStr,
    user_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Add a user as a watcher to a work package.

    Subscribes the specified user to notifications for the given work package.
    Watchers receive email notifications when the work package is updated,
    commented on, or has its status changed. This is useful for keeping
    stakeholders, reviewers, or interested parties informed without assigning
    them directly.

    The user must have view permissions on the work package's project. Adding
    a user who is already watching has no effect.

    Args:
        work_package_id: ID of the work package to watch.
        user_id: ID of the user to add as a watcher. Use list_users or
            get_available_assignees to find valid user IDs.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the watcher was added.
        - message (str): Confirmation message.
        - user_id (int): The ID of the user added as watcher.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Adding watcher {user_id} to work package {work_package_id}...")

    result = await client.add_work_package_watcher(work_package_id, user_id)

    return {
        "success": True,
        "message": f"Watcher added to work package {work_package_id}",
        "user_id": user_id,
    }


@mcp.tool
async def remove_work_package_watcher(
    work_package_id: IntOrStr,
    user_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Remove a user from the watchers list of a work package.

    Unsubscribes the specified user from notifications for the given work
    package. The user will no longer receive email notifications about
    changes to this work package.

    Args:
        work_package_id: ID of the work package to unwatch.
        user_id: ID of the user to remove from watchers.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the watcher was removed.
        - message (str): Confirmation message including user and work
            package IDs.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Removing watcher {user_id} from work package {work_package_id}...")

    await client.remove_work_package_watcher(work_package_id, user_id)

    return {
        "success": True,
        "message": f"Watcher {user_id} removed from work package {work_package_id}",
    }


@mcp.tool
async def list_work_package_watchers(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all users currently watching a work package.

    Returns the list of users subscribed to notifications for the specified
    work package. Watchers are notified of changes, comments, and status
    updates.

    Use this to review who is being notified about a work package before
    making changes, or to audit notification subscriptions.

    Args:
        work_package_id: ID of the work package whose watchers to list.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package_id (int): The queried work package ID.
        - count (int): Number of watchers.
        - watchers (list[dict]): List of watcher user summaries, each with:
            - id (int): User ID.
            - name (str): User display name.
            - email (str): User email address (may be empty if hidden).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing watchers for work package {work_package_id}...")

    result = await client.get_work_package_watchers(work_package_id)
    watchers = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "work_package_id": work_package_id,
        "count": len(watchers),
        "watchers": [
            {
                "id": w.get("id"),
                "name": w.get("name", "Unknown"),
                "email": w.get("email", ""),
            }
            for w in watchers
        ],
    }


@mcp.tool
async def assign_work_package(
    work_package_id: IntOrStr,
    assignee_id: OptionalIntOrStr = None,
    responsible_id: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Assign or reassign a work package to a user.

    Sets the assignee and/or responsible person for a work package. The
    assignee is typically the person doing the work, while the responsible
    person provides oversight or approval.

    This is a convenience wrapper around update_work_package that focuses
    specifically on assignment fields. Use get_available_assignees to find
    valid user IDs for a given project.

    To unassign a work package, call this with assignee_id set explicitly.
    Note that in OpenProject, "unassign" behavior depends on whether the
    API accepts a null/empty assignee.

    Args:
        work_package_id: ID of the work package to assign.
        assignee_id: User ID to assign as the person doing the work. Use
            get_available_assignees to find valid IDs. Pass None to leave
            the current assignee unchanged.
        responsible_id: User ID to set as the responsible/accountable
            person. This is separate from the assignee and represents
            oversight. Pass None to leave unchanged.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the assignment succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Summary with:
            - id (int): Work package ID.
            - subject (str): Work package title.
            - assignee (str): New assignee name, or "Unassigned".
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Assigning work package {work_package_id}...")

    data = {}
    if assignee_id is not None:
        data["assignee_id"] = assignee_id
    if responsible_id is not None:
        data["responsible_id"] = responsible_id

    result = await client.update_work_package(work_package_id, data)

    assignee_name = "Unassigned"
    if result.get("_embedded", {}).get("assignee"):
        assignee_name = result["_embedded"]["assignee"].get("name", "Unknown")

    return {
        "success": True,
        "message": f"Work package {work_package_id} assigned",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject"),
            "assignee": assignee_name,
        },
    }


# ============================================================================
# Priority 7: Time Tracking Tools
# ============================================================================

@mcp.tool
async def log_time(
    work_package_id: IntOrStr,
    hours: float,
    activity_id: OptionalIntOrStr = None,
    spent_on: Optional[str] = None,
    comment: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Log time spent working on a work package.

    Creates a new time entry recording hours spent on the specified work
    package. Time entries are used for effort tracking, reporting, and
    billing. Each entry records who logged the time (based on the API key's
    user), how many hours, when the work was done, and optionally what
    category of work it was.

    Use list_time_entry_activities to discover valid activity/category IDs
    before logging time.

    Args:
        work_package_id: ID of the work package to log time against.
        hours: Number of hours spent. Supports decimal values (e.g. 1.5
            for 1 hour 30 minutes, 0.25 for 15 minutes).
        activity_id: Optional time entry activity/category ID (e.g.
            "Development", "Testing", "Management"). Use
            list_time_entry_activities to find valid IDs. If omitted,
            the default activity is used.
        spent_on: Date when the work was performed, in ISO 8601 format
            (YYYY-MM-DD). Defaults to today's date if not provided.
        comment: Optional free-text comment describing what was done
            during the logged time.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the time entry was created.
        - message (str): Confirmation message.
        - time_entry (dict): The created time entry with:
            - id (int): Time entry ID.
            - hours (str): Duration in ISO 8601 format (e.g. "PT1H30M").
            - spent_on (str): Date in YYYY-MM-DD format.
            - comment (str): Comment text, or empty string.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Logging {hours} hours on work package {work_package_id}...")

    # Default spent_on to today if not provided
    from datetime import date
    actual_spent_on = spent_on if spent_on else date.today().isoformat()

    data = {
        "work_package_id": work_package_id,
        "hours": hours,
        "spent_on": actual_spent_on,  # Always include spent_on
    }

    if activity_id:
        data["activity_id"] = activity_id
    if comment:
        data["comment"] = comment

    result = await client.create_time_entry(data)

    return {
        "success": True,
        "message": f"Time entry created for work package {work_package_id}",
        "time_entry": {
            "id": result.get("id"),
            "hours": result.get("hours"),
            "spent_on": result.get("spentOn"),
            "comment": result.get("comment", {}).get("raw", "") if result.get("comment") else "",
        },
    }


@mcp.tool
async def list_time_entries(
    work_package_id: OptionalIntOrStr = None,
    project_id: OptionalIntOrStr = None,
    user_id: OptionalIntOrStr = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List time entries with optional filtering by work package, project, user, or date range.

    Retrieves time log entries, useful for effort tracking, reporting, and
    auditing. Multiple filters can be combined to narrow results (e.g. a
    specific user's time on a specific project within a date range).

    Note: The work_package_id filter is applied in memory after fetching
    results, as not all OpenProject versions support it as an API filter.
    For large datasets, prefer filtering by project_id and/or date range
    to reduce the initial result set.

    Args:
        work_package_id: Optional work package ID to filter time entries.
            Only entries logged against this work package will be returned.
            Applied as a post-fetch filter.
        project_id: Optional project ID to filter entries by project.
        user_id: Optional user ID to filter entries by the person who
            logged the time.
        from_date: Optional start date for the date range filter, in
            ISO 8601 format (YYYY-MM-DD). Only entries on or after this
            date are returned.
        to_date: Optional end date for the date range filter, in ISO 8601
            format (YYYY-MM-DD). Only entries on or before this date are
            returned.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of time entries returned.
        - total_hours (float): Sum of all hours across returned entries,
            rounded to 2 decimal places.
        - time_entries (list[dict]): List of time entry objects, each with:
            - id (int): Time entry ID.
            - hours (str): Duration in ISO 8601 format (e.g. "PT2H").
            - spent_on (str): Date in YYYY-MM-DD format.
            - work_package_id (str): Associated work package ID.
            - user (str): Name of the user who logged the time.
            - comment (str): Comment text, or empty string.
            - activity (str): Activity/category name (e.g. "Development").
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing time entries...")

    filters = []

    # Only use project and date filters via API (work_package filter not supported in all versions)
    if project_id:
        filters.append({"project": {"operator": "=", "values": [str(project_id)]}})
    if user_id:
        filters.append({"user": {"operator": "=", "values": [str(user_id)]}})
    if from_date:
        filters.append({"spentOn": {"operator": ">=d", "values": [from_date]}})
    if to_date:
        filters.append({"spentOn": {"operator": "<=d", "values": [to_date]}})

    filter_str = json.dumps(filters) if filters else None
    result = await client.get_time_entries(filter_str)
    entries = result.get("_embedded", {}).get("elements", [])

    # Filter by work_package_id in memory if specified (not all OpenProject versions support this filter)
    if work_package_id:
        wp_id_str = str(work_package_id)
        entries = [
            e for e in entries
            if e.get("_links", {}).get("workPackage", {}).get("href", "").split("/")[-1] == wp_id_str
        ]

    # Calculate total hours
    total_hours = sum(
        float(e.get("hours", "PT0H").replace("PT", "").replace("H", "").replace("M", "")) / 60
        if "M" in e.get("hours", "") else float(e.get("hours", "PT0H").replace("PT", "").replace("H", ""))
        for e in entries
    )

    return {
        "success": True,
        "count": len(entries),
        "total_hours": round(total_hours, 2),
        "time_entries": [
            {
                "id": e.get("id"),
                "hours": e.get("hours"),
                "spent_on": e.get("spentOn"),
                "work_package_id": e.get("_links", {}).get("workPackage", {}).get("href", "").split("/")[-1],
                "user": e.get("_embedded", {}).get("user", {}).get("name", "Unknown"),
                "comment": e.get("comment", {}).get("raw", "") if e.get("comment") else "",
                "activity": e.get("_embedded", {}).get("activity", {}).get("name", "Unknown"),
            }
            for e in entries
        ],
    }


@mcp.tool
async def list_time_entry_activities(
    project_id: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List available time entry activity categories for logging time.

    Returns the set of activity types (e.g. "Development", "Testing",
    "Management", "Design") that can be used as the activity_id parameter
    when calling log_time. Activities define what kind of work was performed.

    When project_id is provided, only activities enabled for that project
    are returned. Without a project_id, all globally configured activities
    are listed.

    Args:
        project_id: Optional project ID to scope the activity list to a
            specific project. None returns all globally available activities.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of activities returned.
        - activities (list[dict]): List of activity definitions, each with:
            - id (int): Activity ID (use this as activity_id in log_time).
            - name (str): Human-readable activity name (e.g. "Development").
            - is_default (bool): Whether this is the default activity when
                none is specified.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing time entry activities...")

    result = await client.get_time_entry_activities(project_id)
    activities = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(activities),
        "activities": [
            {
                "id": a.get("id"),
                "name": a.get("name", "Unknown"),
                "is_default": a.get("isDefault", False),
            }
            for a in activities
        ],
    }


# ============================================================================
# Priority 8: Attachments Tools
# ============================================================================

@mcp.tool
async def list_work_package_attachments(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all file attachments on a work package.

    Retrieves metadata for every file attached to the specified work package,
    including filenames, sizes, MIME types, authors, and download URLs. Use
    this to check what files are already attached before uploading or to get
    attachment IDs for deletion.

    Args:
        work_package_id: ID of the work package whose attachments to list.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package_id (int): The queried work package ID.
        - count (int): Number of attachments.
        - attachments (list[dict]): List of attachment metadata, each with:
            - id (int): Attachment ID (use for deletion via
                delete_attachment).
            - filename (str): Original filename.
            - file_size (int): File size in bytes.
            - content_type (str): MIME type (e.g. "image/png",
                "application/pdf").
            - description (str): Attachment description, or empty string.
            - created_at (str): ISO 8601 upload timestamp.
            - author (str): Name of the user who uploaded the file.
            - download_url (str): Direct URL to download the file.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Listing attachments for work package {work_package_id}...")

    result = await client.get_work_package_attachments(work_package_id)
    attachments = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "work_package_id": work_package_id,
        "count": len(attachments),
        "attachments": [
            {
                "id": a.get("id"),
                "filename": a.get("fileName", "Unknown"),
                "file_size": a.get("fileSize"),
                "content_type": a.get("contentType"),
                "description": a.get("description", {}).get("raw", "") if a.get("description") else "",
                "created_at": a.get("createdAt"),
                "author": a.get("_embedded", {}).get("author", {}).get("name", "Unknown"),
                "download_url": a.get("_links", {}).get("downloadLocation", {}).get("href", ""),
            }
            for a in attachments
        ],
    }


@mcp.tool
async def add_work_package_attachment(
    work_package_id: IntOrStr,
    file_data: str,  # Base64-encoded file content
    filename: str,
    content_type: str = "application/octet-stream",
    description: Optional[str] = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Upload and attach a file to a work package.

    Attaches a file to the specified work package by uploading base64-encoded
    file content. The file becomes part of the work package's attachments and
    can be referenced in comments or the description.

    Common use cases:
    - Attach screenshots or mockups to a bug report or story.
    - Upload design documents, specifications, or meeting notes.
    - Add log files or error reports to an incident work package.
    - Attach test results or build artifacts.

    Note: The file_data must be base64-encoded. Large files may take longer
    to upload depending on network conditions and OpenProject configuration.

    Args:
        work_package_id: ID of the work package to attach the file to.
        file_data: The file content encoded as a base64 string. You can
            encode a file with base64.b64encode(file_bytes).decode().
        filename: The name to give the attached file (e.g. "screenshot.png",
            "report.pdf"). Include the file extension.
        content_type: MIME type of the file. Default is
            "application/octet-stream". Common values:
            - "image/png", "image/jpeg" for images
            - "application/pdf" for PDFs
            - "text/plain" for text files
            - "application/json" for JSON files
        description: Optional text description of the attachment explaining
            its contents or purpose.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the upload succeeded.
        - message (str): Confirmation message.
        - attachment (dict): Created attachment metadata with:
            - id (int): Attachment ID.
            - filename (str): The stored filename.
            - file_size (int): File size in bytes.
            - content_type (str): MIME type.
            - description (str): Attachment description.
            - created_at (str): ISO 8601 upload timestamp.

        If the base64 data is invalid:
        - success (bool): False.
        - error (str): Description of the decoding error.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Adding attachment '{filename}' to work package {work_package_id}...")

    # Decode base64 file data
    try:
        file_bytes = base64.b64decode(file_data)
    except Exception as e:
        return {
            "success": False,
            "error": f"Invalid base64 file data: {str(e)}",
        }

    result = await client.add_work_package_attachment(
        work_package_id,
        file_bytes,
        filename,
        content_type,
        description,
    )

    return {
        "success": True,
        "message": f"Attachment '{filename}' added to work package {work_package_id}",
        "attachment": {
            "id": result.get("id"),
            "filename": result.get("fileName", filename),
            "file_size": result.get("fileSize"),
            "content_type": result.get("contentType", content_type),
            "description": result.get("description", {}).get("raw", "") if result.get("description") else description or "",
            "created_at": result.get("createdAt"),
        },
    }


@mcp.tool
async def delete_attachment(
    attachment_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Permanently delete a file attachment from OpenProject.

    Removes the specified attachment and its stored file data. This action is
    irreversible. Use list_work_package_attachments to find attachment IDs.

    Note: The attachment is deleted regardless of which work package it
    belongs to. Ensure you have the correct attachment_id before deleting.

    Args:
        attachment_id: ID of the attachment to delete. Obtain this from
            the list_work_package_attachments response.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the deletion succeeded.
        - message (str): Confirmation message including the deleted
            attachment ID.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Deleting attachment {attachment_id}...")

    await client.delete_attachment(attachment_id)

    return {
        "success": True,
        "message": f"Attachment {attachment_id} deleted successfully",
    }


# ============================================================================
# Priority 9: Custom Fields Tools
# ============================================================================

@mcp.tool
async def list_custom_fields(
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """List all custom fields configured in the OpenProject instance.

    Returns metadata for every custom field, including names, data types,
    and the key format needed to read or update custom field values on work
    packages. Custom fields extend the standard work package schema with
    organization-specific metadata.

    Use this tool to discover:
    - Available custom fields and their IDs.
    - The correct key format ("customField{id}") for use with
      update_work_package_custom_fields.
    - Field types (text, integer, list, date, etc.) to know what values
      are expected.
    - Whether a field is required or available in all projects.

    Args:
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - count (int): Number of custom fields returned.
        - custom_fields (list[dict]): List of custom field definitions, each
            containing:
            - id (int): Custom field ID.
            - name (str): Human-readable field name (e.g. "Sprint Points").
            - field_format (str): Data type (e.g. "string", "int", "list",
                "date", "bool", "float", "text", "user").
            - is_required (bool): Whether the field must be filled in.
            - is_for_all (bool): Whether the field is enabled in all
                projects (vs. selected projects only).
            - custom_field_key (str): The key to use in API calls, formatted
                as "customField{id}" (e.g. "customField42").
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info("Listing custom fields...")

    result = await client.get_custom_fields()
    fields = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "count": len(fields),
        "custom_fields": [
            {
                "id": f.get("id"),
                "name": f.get("name", "Unknown"),
                "field_format": f.get("fieldFormat", "Unknown"),
                "is_required": f.get("isRequired", False),
                "is_for_all": f.get("isForAll", False),
                "custom_field_key": f"customField{f.get('id')}",  # Key to use in updates
            }
            for f in fields
        ],
    }


@mcp.tool
async def update_work_package_custom_fields(
    work_package_id: IntOrStr,
    custom_fields: str,  # JSON string of custom field values
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update custom field values on a work package.

    Sets one or more custom field values on the specified work package.
    Custom fields are organization-specific metadata fields that extend the
    standard work package schema. Use list_custom_fields to discover
    available fields and their expected data types.

    The custom_fields parameter must be a JSON string mapping custom field
    keys (in the format "customField{id}") to their new values. The value
    type must match the field's configured format (string, integer, date,
    etc.).

    Args:
        work_package_id: ID of the work package to update.
        custom_fields: JSON string mapping custom field keys to values.
            Keys must follow the format "customField{id}" where {id} is
            the custom field's numeric ID. Example:
            {"customField1": "sprint-42", "customField5": 8, "customField10": true}
            Use list_custom_fields to find field IDs and their expected
            value types.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the update succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Summary with:
            - id (int): Work package ID.
            - subject (str): Work package title.

        If the JSON is invalid:
        - success (bool): False.
        - error (str): Description of the JSON parsing error.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Updating custom fields on work package {work_package_id}...")

    try:
        fields_dict = json.loads(custom_fields)
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in custom_fields: {str(e)}",
        }

    result = await client.update_work_package_custom_fields(work_package_id, fields_dict)

    return {
        "success": True,
        "message": f"Custom fields updated on work package {work_package_id}",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject"),
        },
    }


# ============================================================================
# Priority 10: Workflow & Status Management Tools
# ============================================================================

@mcp.tool
async def get_work_package_schema(
    work_package_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the schema and allowed transitions for a specific work package.

    Retrieves the work package's form schema, which describes what field
    values are currently valid. Most importantly, this reveals the allowed
    status transitions from the work package's current status, based on the
    configured workflow rules.

    Use this tool before changing a work package's status to verify that
    the desired target status is a valid transition. Also useful for
    discovering available types and priorities for the work package's
    project context.

    Common use cases:
    - Determine which statuses a work package can be moved to next.
    - Check available types and priorities before updating.
    - Validate that a planned status transition is allowed by the workflow.
    - Debug "invalid transition" errors by checking allowed values.

    Args:
        work_package_id: ID of the work package whose schema to retrieve.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - work_package_id (int): The queried work package ID.
        - allowed_statuses (list[dict]): Statuses the work package can
            transition to, each with:
            - id (int): Status ID (use with update_work_package_status).
            - name (str): Status name (e.g. "In progress", "Closed").
            - is_closed (bool): Whether the status represents completion.
        - allowed_status_count (int): Number of allowed status transitions.
        - allowed_types (list[dict]): Types the work package can be changed
            to, each with:
            - id (int): Type ID.
            - name (str): Type name (e.g. "Task", "Bug").
        - allowed_priorities (list[dict]): Available priorities, each with:
            - id (int): Priority ID.
            - name (str): Priority name (e.g. "High", "Normal").
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting schema for work package {work_package_id}...")

    result = await client.get_work_package_schema(work_package_id)

    # Extract status transition info
    status_schema = result.get("status", {})
    allowed_statuses = status_schema.get("_embedded", {}).get("allowedValues", [])

    # Extract type info
    type_schema = result.get("type", {})
    allowed_types = type_schema.get("_embedded", {}).get("allowedValues", [])

    # Extract priority info
    priority_schema = result.get("priority", {})
    allowed_priorities = priority_schema.get("_embedded", {}).get("allowedValues", [])

    return {
        "success": True,
        "work_package_id": work_package_id,
        "allowed_statuses": [
            {
                "id": s.get("id"),
                "name": s.get("name", "Unknown"),
                "is_closed": s.get("isClosed", False),
            }
            for s in allowed_statuses
        ],
        "allowed_status_count": len(allowed_statuses),
        "allowed_types": [
            {
                "id": t.get("id"),
                "name": t.get("name", "Unknown"),
            }
            for t in allowed_types
        ],
        "allowed_priorities": [
            {
                "id": p.get("id"),
                "name": p.get("name", "Unknown"),
            }
            for p in allowed_priorities
        ],
    }


@mcp.tool
async def update_work_package_status(
    work_package_id: IntOrStr,
    status_id: IntOrStr,
    comment: Optional[str] = None,
    percentage_done: OptionalIntOrStr = None,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Update the status of a work package with an optional comment and progress.

    Changes the workflow status of a work package (e.g. from "New" to
    "In progress", or from "In progress" to "Closed"). Optionally adds a
    comment explaining the status change and updates the completion
    percentage in a single operation.

    This is a convenience tool that combines update_work_package (for the
    status and percentage) with add_work_package_comment (for the comment).
    The status change and comment are applied as separate API calls.

    Important: OpenProject enforces workflow rules that restrict which
    status transitions are valid. Use get_work_package_schema to check
    allowed transitions before calling this tool. If the transition is not
    allowed, the API will return an error.

    Args:
        work_package_id: ID of the work package whose status to update.
        status_id: Target status ID. Use list_statuses to see all
            statuses, or get_work_package_schema to see only the statuses
            that are valid transitions from the current status.
        comment: Optional comment explaining the reason for the status
            change. Supports markdown. The comment is posted as a separate
            activity entry on the work package.
        percentage_done: Optional completion percentage to set along with
            the status change (0-100). For example, set to 100 when
            closing, or 50 when marking as "In progress".
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the status update succeeded.
        - message (str): Confirmation message.
        - work_package (dict): Updated work package summary with:
            - id (int): Work package ID.
            - subject (str): Work package title.
            - status (str): New status name after the transition.
            - percentage_done (int): Current completion percentage.
        - comment_added (bool): Whether a comment was also posted.
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Updating status of work package {work_package_id} to {status_id}...")

    # Update status
    data = {"status_id": status_id}
    if percentage_done is not None:
        data["percentage_done"] = percentage_done

    result = await client.update_work_package(work_package_id, data)

    # Add comment if provided
    if comment:
        await client.add_work_package_comment(work_package_id, comment)

    return {
        "success": True,
        "message": f"Status updated for work package {work_package_id}",
        "work_package": {
            "id": result.get("id"),
            "subject": result.get("subject"),
            "status": result.get("_embedded", {}).get("status", {}).get("name", "Unknown"),
            "percentage_done": result.get("percentageDone", 0),
        },
        "comment_added": comment is not None,
    }


@mcp.tool
async def get_available_assignees(
    project_id: IntOrStr,
    ctx: Optional[Context] = None,
) -> Dict[str, Any]:
    """Get the list of users who can be assigned to work packages in a project.

    Returns all users who have the necessary permissions to be set as an
    assignee on work packages within the specified project. This is
    determined by the project's membership and role configuration.

    Use this tool to find valid user IDs before calling assign_work_package,
    create_work_package (with assignee_id), or update_work_package. This
    ensures you only attempt to assign users who actually have permission
    to be assigned in the given project.

    This differs from list_users, which returns all users in the instance
    regardless of project membership.

    Args:
        project_id: ID of the project to get assignable users for.
        ctx: Optional MCP context for logging progress.

    Returns:
        Dict with:
        - success (bool): Whether the operation succeeded.
        - project_id (int): The queried project ID.
        - count (int): Number of assignable users.
        - assignees (list[dict]): List of assignable users, each with:
            - id (int): User ID (use as assignee_id in work package
                operations).
            - name (str): User display name.
            - email (str): User email address (may be empty if hidden by
                privacy settings).
    """
    if not client:
        raise Exception("OpenProject Client not initialized.")

    if ctx:
        await ctx.info(f"Getting available assignees for project {project_id}...")

    result = await client.get_work_package_available_assignees(project_id)
    users = result.get("_embedded", {}).get("elements", [])

    return {
        "success": True,
        "project_id": project_id,
        "count": len(users),
        "assignees": [
            {
                "id": u.get("id"),
                "name": u.get("name", "Unknown"),
                "email": u.get("email", ""),
            }
            for u in users
        ],
    }


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the OpenProject server with HTTP transport for remote access."""
    import os

    # Use HTTP transport for remote access with native MCP protocol support
    transport = os.getenv("FASTMCP_TRANSPORT", "http")
    host = os.getenv("FASTMCP_HOST", "0.0.0.0")
    port = int(os.getenv("FASTMCP_PORT", "8006"))
    # Enable stateless HTTP mode for better compatibility with MCP clients like Cursor
    stateless = os.getenv("FASTMCP_STATELESS_HTTP", "true").lower() == "true"
    # Enable JSON response format for better Cursor compatibility
    json_response = os.getenv("FASTMCP_JSON_RESPONSE", "true").lower() == "true"
    # HTTP transport provides native MCP protocol support at /mcp endpoint
    # FastMCP automatically handles streamable HTTP protocol
    mcp.run(
        transport=transport,
        host=host,
        port=port,
        stateless_http=stateless,
        json_response=json_response,
    )


if __name__ == "__main__":
    main()
