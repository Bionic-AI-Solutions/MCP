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
    """Test the connection to the OpenProject API."""
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
    """List all OpenProject projects."""
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
    """List work packages with optional filtering."""
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
    """List available work package types."""
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
    """Create a new work package."""
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
    """Get detailed information about a specific work package."""
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
    """Update an existing work package."""
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
    """Delete a work package."""
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
    """List all users in the OpenProject instance."""
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
    """Get detailed information about a specific user."""
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
    """List all available work package statuses."""
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
    """List all available work package priorities."""
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
    """Get detailed information about a specific project."""
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
    """Create a new project."""
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
    """Update an existing project."""
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
    """Delete a project."""
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
    """
    Set a parent work package for a work package.
    
    Use cases:
    - Set Story as child of Epic
    - Set Task as child of Story
    - Organize work package hierarchy
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
    """
    Remove the parent relationship from a work package.
    
    Makes the work package a top-level item (no parent).
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
    """
    Get child work packages of a parent work package.
    
    Args:
        parent_id: ID of the parent work package
        project_id: Optional project filter
        type_id: Optional filter by work package type
        status: Optional filter by status ("open", "closed", or "all")
        include_descendants: If True, include all descendants (children of children)
    
    Use cases:
    - List all stories under an epic
    - List all tasks under a story
    - Check if story has tasks before closing
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
    """
    Get the full hierarchy of a work package (ancestors and descendants).
    
    Use cases:
    - Visualize full hierarchy (Epic → Feature → Story → Task)
    - Understand work package context
    - Generate tree views
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
    """
    Create multiple work packages in batch.
    
    Args:
        project_id: Project ID for all work packages
        work_packages: JSON string array of work package definitions, each with:
            - subject (required): Title of the work package
            - type_id (required): Work package type ID
            - description: Optional description
            - parent_id: Optional parent work package ID
            - status_id: Optional status ID
            - priority_id: Optional priority ID
            - assignee_id: Optional assignee user ID
            - startDate: Optional start date (YYYY-MM-DD)
            - dueDate: Optional due date (YYYY-MM-DD)
        continue_on_error: If True, continue creating even if some fail
    
    Example work_packages JSON:
    [
        {"subject": "Task 1", "type_id": 36, "description": "First task"},
        {"subject": "Task 2", "type_id": 36, "parent_id": 100}
    ]
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
    """
    Update multiple work packages in batch.
    
    Args:
        updates: JSON string array of update objects, each with:
            - work_package_id (required): ID of work package to update
            - subject: New subject
            - description: New description
            - type_id: New type ID
            - status_id: New status ID
            - priority_id: New priority ID
            - assignee_id: New assignee ID
            - parent_id: New parent ID
            - percentage_done: New percentage (0-100)
            - startDate: New start date
            - dueDate: New due date
        continue_on_error: If True, continue updating even if some fail
    
    Example updates JSON:
    [
        {"work_package_id": 100, "status_id": 72},
        {"work_package_id": 101, "assignee_id": 5, "percentage_done": 50}
    ]
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
    """
    Advanced work package query with flexible filtering.
    
    Args:
        project_id: Optional project ID to scope the query
        filters: JSON string of filter array, e.g.:
            [{"type": {"operator": "=", "values": ["41"]}},
             {"status": {"operator": "o", "values": null}}]
            
            Common operators:
            - "=" : equals
            - "!" : not equals
            - "o" : open (for status)
            - "c" : closed (for status)
            - "~" : contains (for text fields)
            - ">=" : greater than or equal
            - "<=" : less than or equal
            
            Common filter fields:
            - type, status, priority, assignee, author
            - parent, project, version
            - subject, description (use ~ operator)
            - created_at, updated_at (use date operators)
            
        sort_by: Sort specification, e.g. "subject:asc" or "updated_at:desc"
        group_by: Group by attribute, e.g. "status", "type", "assignee"
        page: Page number (1-based)
        page_size: Number of results per page (max 100)
    
    Use cases:
    - Find all open stories under Epic 1
    - Find all tasks assigned to a user
    - Search work packages by subject pattern
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
    """
    Search work packages by subject text.
    
    Args:
        query: Search text to find in subject (uses contains/~ operator)
        project_id: Optional project ID to limit search scope
        type_ids: Optional comma-separated type IDs to filter by
        status: "open", "closed", or "all"
        limit: Maximum number of results (default 20)
    
    Use cases:
    - Quick search for work packages by subject
    - Find work packages containing specific keywords
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
    """
    Create a relationship between two work packages.
    
    Args:
        from_work_package_id: Source work package ID
        to_work_package_id: Target work package ID
        relation_type: Type of relation:
            - "relates": General relation
            - "duplicates": This duplicates another
            - "duplicated": This is duplicated by another
            - "blocks": This blocks another
            - "blocked": This is blocked by another
            - "precedes": This precedes another (must finish first)
            - "follows": This follows another (must wait for it)
            - "includes": This includes another
            - "partof": This is part of another
            - "requires": This requires another
            - "required": This is required by another
        description: Optional description of the relation
        lag: Optional lag in days (for precedes/follows relations)
    
    Use cases:
    - Link blocking tasks
    - Create dependency chains
    - Track related or duplicate work packages
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
    """
    List work package relations.
    
    Args:
        work_package_id: Optional work package ID to get relations for
        relation_type: Optional relation type to filter (relates, blocks, precedes, etc.)
    
    Use cases:
    - View all dependencies for a work package
    - Check for blocking work packages
    - Understand relationship graph
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
    """Delete a work package relation."""
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
    """
    Add a comment to a work package.
    
    Args:
        work_package_id: ID of the work package
        comment: Comment text (supports markdown)
        notify: Whether to notify watchers (default True)
    
    Use cases:
    - Add progress updates
    - Document decisions
    - Communicate with team members
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
    """
    List activities (comments and changes) for a work package.
    
    Use cases:
    - View work package history
    - Review comments
    - Track changes over time
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
    """
    Add a watcher to a work package.
    
    Watchers receive notifications about changes to the work package.
    
    Use cases:
    - Subscribe stakeholders to updates
    - Ensure team members stay informed
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
    """Remove a watcher from a work package."""
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
    """List all watchers of a work package."""
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
    """
    Assign or reassign a work package.
    
    Args:
        work_package_id: ID of the work package
        assignee_id: User ID to assign (None to unassign)
        responsible_id: User ID for responsible person (optional)
    
    Use cases:
    - Assign tasks to developers
    - Reassign work packages
    - Set responsible person for oversight
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
    """
    Log time spent on a work package.
    
    Args:
        work_package_id: ID of the work package
        hours: Number of hours spent (e.g., 1.5 for 1 hour 30 minutes)
        activity_id: Optional time entry activity/category ID
        spent_on: Date the time was spent (YYYY-MM-DD), defaults to today
        comment: Optional comment describing the work done
    
    Use cases:
    - Track development time
    - Log meeting time
    - Record effort for reporting
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
    """
    List time entries with optional filters.
    
    Args:
        work_package_id: Filter by work package
        project_id: Filter by project
        user_id: Filter by user who logged time
        from_date: Filter entries from this date (YYYY-MM-DD)
        to_date: Filter entries up to this date (YYYY-MM-DD)
    
    Use cases:
    - View time logged on a work package
    - Generate time reports
    - Track team effort
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
    """
    List available time entry activities (categories).
    
    Use this to find valid activity_id values for logging time.
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
    """
    List attachments on a work package.
    
    Use cases:
    - View attached files
    - Get attachment IDs for download
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
    """
    Add an attachment to a work package.
    
    Args:
        work_package_id: ID of the work package
        file_data: Base64-encoded file content
        filename: Name of the file to attach
        content_type: MIME type of the file (default: application/octet-stream)
        description: Optional description of the attachment
    
    Use cases:
    - Attach documents to work packages
    - Upload screenshots or images
    - Add supporting files
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
    """Delete an attachment."""
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
    """
    List all custom fields configured in OpenProject.
    
    Use this to discover available custom fields and their IDs
    for use with update_work_package_custom_fields.
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
    """
    Update custom field values on a work package.
    
    Args:
        work_package_id: ID of the work package
        custom_fields: JSON string mapping custom field keys to values, e.g.:
            {"customField1": "value1", "customField2": 123}
            
            Use list_custom_fields to find field IDs.
            The key format is "customField{id}".
    
    Use cases:
    - Set custom metadata
    - Track additional information not in standard fields
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
    """
    Get the schema for a work package, including available status transitions.
    
    This shows which status transitions are allowed from the current status,
    as well as available types, priorities, and assignees.
    
    Use cases:
    - Determine valid next statuses
    - Check available types and priorities
    - Understand available transitions
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
    """
    Update the status of a work package with optional comment.
    
    Args:
        work_package_id: ID of the work package
        status_id: New status ID (use list_statuses or get_work_package_schema to find valid IDs)
        comment: Optional comment explaining the status change
        percentage_done: Optional progress percentage (0-100)
    
    Use cases:
    - Transition work packages through workflow
    - Document status changes with context
    - Update progress with status
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
    """
    Get users who can be assigned to work packages in a project.
    
    Use cases:
    - Find valid assignee IDs
    - List team members for assignment
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


