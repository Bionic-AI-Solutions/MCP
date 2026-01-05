"""
OpenProject API Client

Client for the OpenProject API v3 with optional proxy support.
Adapted from openproject-mcp-server for FastMCP integration.
"""

import os
import json
import logging
import base64
import ssl
from typing import Dict, Optional
from urllib.parse import quote
import aiohttp

logger = logging.getLogger(__name__)


class OpenProjectClient:
    """Client for the OpenProject API v3 with optional proxy support"""

    def __init__(self, base_url: str, api_key: str, proxy: Optional[str] = None):
        """
        Initialize the OpenProject client.

        Args:
            base_url: The base URL of the OpenProject instance
            api_key: API key for authentication
            proxy: Optional HTTP proxy URL
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.proxy = proxy

        # Setup headers with Basic Auth
        self.headers = {
            "Authorization": f"Basic {self._encode_api_key()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OpenProject-MCP/1.0.0",
        }

        logger.info(f"OpenProject Client initialized for: {self.base_url}")
        if self.proxy:
            logger.info(f"Using proxy: {self.proxy}")

    def _encode_api_key(self) -> str:
        """Encode API key for Basic Auth"""
        credentials = f"apikey:{self.api_key}"
        return base64.b64encode(credentials.encode()).decode()

    async def _request(
        self, method: str, endpoint: str, data: Optional[Dict] = None
    ) -> Dict:
        """
        Execute an API request.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Optional request body data

        Returns:
            Dict: Response data from the API

        Raises:
            Exception: If the request fails
        """
        url = f"{self.base_url}/api/v3{endpoint}"

        logger.debug(f"API Request: {method} {url}")
        if data:
            logger.debug(f"Request body: {json.dumps(data, indent=2)}")

        # Configure SSL and timeout
        ssl_context = ssl.create_default_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            try:
                # Build request parameters
                request_params = {
                    "method": method,
                    "url": url,
                    "headers": self.headers,
                    "json": data,
                }

                # Add proxy if configured
                if self.proxy:
                    request_params["proxy"] = self.proxy

                async with session.request(**request_params) as response:
                    response_text = await response.text()

                    logger.debug(f"Response status: {response.status}")

                    # Parse response
                    try:
                        response_json = (
                            json.loads(response_text) if response_text else {}
                        )
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON response: {response_text[:200]}...")
                        response_json = {}

                    # Handle errors
                    if response.status >= 400:
                        error_msg = self._format_error_message(
                            response.status, response_text
                        )
                        raise Exception(error_msg)

                    return response_json

            except aiohttp.ClientError as e:
                logger.error(f"Network error: {str(e)}")
                raise Exception(f"Network error accessing {url}: {str(e)}")

    def _format_error_message(self, status: int, response_text: str) -> str:
        """Format error message based on HTTP status code"""
        base_msg = f"API Error {status}: {response_text}"

        error_hints = {
            401: "Authentication failed. Please check your API key.",
            403: "Access denied. The user lacks required permissions.",
            404: "Resource not found. Please verify the URL and resource exists.",
            407: "Proxy authentication required.",
            500: "Internal server error. Please try again later.",
            502: "Bad gateway. The server or proxy is not responding correctly.",
            503: "Service unavailable. The server might be under maintenance.",
        }

        if status in error_hints:
            base_msg += f"\n\n{error_hints[status]}"

        return base_msg

    # API Methods - copied from original openproject-mcp.py
    # These methods are used by the FastMCP tools
    
    async def test_connection(self) -> Dict:
        """Test the API connection and authentication"""
        logger.info("Testing API connection...")
        return await self._request("GET", "")

    async def get_projects(self, filters: Optional[str] = None) -> Dict:
        """Retrieve all projects."""
        endpoint = "/projects"
        if filters:
            encoded_filters = quote(filters)
            endpoint += f"?filters={encoded_filters}"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_work_packages(
        self,
        project_id: Optional[int] = None,
        filters: Optional[str] = None,
        offset: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Dict:
        """Retrieve work packages."""
        if project_id:
            endpoint = f"/projects/{project_id}/work_packages"
        else:
            endpoint = "/work_packages"

        query_params = []
        if filters:
            encoded_filters = quote(filters)
            query_params.append(f"filters={encoded_filters}")
        if offset is not None:
            query_params.append(f"offset={offset}")
        if page_size is not None:
            query_params.append(f"pageSize={page_size}")

        if query_params:
            endpoint += "?" + "&".join(query_params)

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def create_work_package(self, data: Dict) -> Dict:
        """Create a new work package."""
        form_payload = {"_links": {}}
        if "project" in data:
            form_payload["_links"]["project"] = {
                "href": f"/api/v3/projects/{data['project']}"
            }
        if "type" in data:
            form_payload["_links"]["type"] = {"href": f"/api/v3/types/{data['type']}"}
        if "subject" in data:
            form_payload["subject"] = data["subject"]

        form = await self._request("POST", "/work_packages/form", form_payload)
        payload = form.get("payload", form_payload)
        payload["lockVersion"] = form.get("lockVersion", 0)

        if "description" in data:
            payload["description"] = {"raw": data["description"]}
        if "priority_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["priority"] = {
                "href": f"/api/v3/priorities/{data['priority_id']}"
            }
        if "assignee_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["assignee"] = {
                "href": f"/api/v3/users/{data['assignee_id']}"
            }
        if "startDate" in data:
            payload["startDate"] = data["startDate"]
        if "dueDate" in data:
            payload["dueDate"] = data["dueDate"]
        if "date" in data:
            payload["date"] = data["date"]

        return await self._request("POST", "/work_packages", payload)

    async def get_types(self, project_id: Optional[int] = None) -> Dict:
        """Retrieve available work package types."""
        if project_id:
            endpoint = f"/projects/{project_id}/types"
        else:
            endpoint = "/types"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_users(self, filters: Optional[str] = None) -> Dict:
        """Retrieve users."""
        endpoint = "/users"
        if filters:
            encoded_filters = quote(filters)
            endpoint += f"?filters={encoded_filters}"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_user(self, user_id: int) -> Dict:
        """Retrieve a specific user by ID."""
        return await self._request("GET", f"/users/{user_id}")

    async def get_memberships(
        self, project_id: Optional[int] = None, user_id: Optional[int] = None
    ) -> Dict:
        """Retrieve memberships."""
        endpoint = "/memberships"
        filters = []
        if project_id:
            filters.append({"project": {"operator": "=", "values": [str(project_id)]}})
        if user_id:
            filters.append({"user": {"operator": "=", "values": [str(user_id)]}})

        if filters:
            filter_string = quote(json.dumps(filters))
            endpoint += f"?filters={filter_string}"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_statuses(self) -> Dict:
        """Retrieve available work package statuses."""
        result = await self._request("GET", "/statuses")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_priorities(self) -> Dict:
        """Retrieve available work package priorities."""
        result = await self._request("GET", "/priorities")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_work_package(self, work_package_id: int) -> Dict:
        """Retrieve a specific work package by ID."""
        return await self._request("GET", f"/work_packages/{work_package_id}")

    async def update_work_package(self, work_package_id: int, data: Dict) -> Dict:
        """Update an existing work package."""
        current_wp = await self.get_work_package(work_package_id)
        payload = {"lockVersion": current_wp.get("lockVersion", 0)}

        if "subject" in data:
            payload["subject"] = data["subject"]
        if "description" in data:
            payload["description"] = {"raw": data["description"]}
        if "type_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["type"] = {"href": f"/api/v3/types/{data['type_id']}"}
        if "status_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["status"] = {
                "href": f"/api/v3/statuses/{data['status_id']}"
            }
        if "priority_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["priority"] = {
                "href": f"/api/v3/priorities/{data['priority_id']}"
            }
        if "assignee_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["assignee"] = {
                "href": f"/api/v3/users/{data['assignee_id']}"
            }
        if "percentage_done" in data:
            payload["percentageDone"] = data["percentage_done"]
        if "startDate" in data:
            payload["startDate"] = data["startDate"]
        if "dueDate" in data:
            payload["dueDate"] = data["dueDate"]
        if "date" in data:
            payload["date"] = data["date"]

        return await self._request(
            "PATCH", f"/work_packages/{work_package_id}", payload
        )

    async def delete_work_package(self, work_package_id: int) -> bool:
        """Delete a work package."""
        await self._request("DELETE", f"/work_packages/{work_package_id}")
        return True

    async def get_time_entries(self, filters: Optional[str] = None) -> Dict:
        """Retrieve time entries."""
        endpoint = "/time_entries"
        if filters:
            encoded_filters = quote(filters)
            endpoint += f"?filters={encoded_filters}"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def create_time_entry(self, data: Dict) -> Dict:
        """Create a new time entry."""
        payload = {}
        if "work_package_id" in data:
            payload["_links"] = {
                "workPackage": {
                    "href": f"/api/v3/work_packages/{data['work_package_id']}"
                }
            }
        if "hours" in data:
            payload["hours"] = f"PT{data['hours']}H"
        if "spent_on" in data:
            payload["spentOn"] = data["spent_on"]
        if "comment" in data:
            payload["comment"] = {"raw": data["comment"]}
        if "activity_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["activity"] = {
                "href": f"/api/v3/time_entries/activities/{data['activity_id']}"
            }

        return await self._request("POST", "/time_entries", payload)

    async def update_time_entry(self, time_entry_id: int, data: Dict) -> Dict:
        """Update an existing time entry."""
        current_te = await self._request("GET", f"/time_entries/{time_entry_id}")
        payload = {"lockVersion": current_te.get("lockVersion", 0)}

        if "hours" in data:
            payload["hours"] = f"PT{data['hours']}H"
        if "spent_on" in data:
            payload["spentOn"] = data["spent_on"]
        if "comment" in data:
            payload["comment"] = {"raw": data["comment"]}
        if "activity_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["activity"] = {
                "href": f"/api/v3/time_entries/activities/{data['activity_id']}"
            }

        return await self._request("PATCH", f"/time_entries/{time_entry_id}", payload)

    async def delete_time_entry(self, time_entry_id: int) -> bool:
        """Delete a time entry."""
        await self._request("DELETE", f"/time_entries/{time_entry_id}")
        return True

    async def get_versions(self, project_id: Optional[int] = None) -> Dict:
        """Retrieve project versions."""
        if project_id:
            endpoint = f"/projects/{project_id}/versions"
        else:
            endpoint = "/versions"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def create_version(self, project_id: int, data: Dict) -> Dict:
        """Create a new project version."""
        payload = {
            "_links": {"definingProject": {"href": f"/api/v3/projects/{project_id}"}}
        }
        if "name" in data:
            payload["name"] = data["name"]
        if "description" in data:
            payload["description"] = {"raw": data["description"]}
        if "start_date" in data:
            payload["startDate"] = data["start_date"]
        if "end_date" in data:
            payload["endDate"] = data["end_date"]
        if "status" in data:
            payload["status"] = data["status"]

        return await self._request("POST", "/versions", payload)

    async def check_permissions(self) -> Dict:
        """Check user permissions and capabilities."""
        try:
            return await self._request("GET", "/users/me")
        except Exception as e:
            logger.error(f"Failed to check permissions: {e}")
            return {}

    async def get_project(self, project_id: int) -> Dict:
        """Retrieve a specific project by ID."""
        return await self._request("GET", f"/projects/{project_id}")

    async def create_project(self, data: Dict) -> Dict:
        """Create a new project."""
        payload = {}
        if "name" in data:
            payload["name"] = data["name"]
        if "identifier" in data:
            payload["identifier"] = data["identifier"]
        if "description" in data:
            payload["description"] = {"raw": data["description"]}
        if "public" in data:
            payload["public"] = data["public"]
        if "status" in data:
            payload["status"] = data["status"]
        if "parent_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["parent"] = {
                "href": f"/api/v3/projects/{data['parent_id']}"
            }

        return await self._request("POST", "/projects", payload)

    async def update_project(self, project_id: int, data: Dict) -> Dict:
        """Update an existing project."""
        try:
            current_project = await self.get_project(project_id)
            lock_version = current_project.get("lockVersion", 0)
        except:
            lock_version = 0

        payload = {"lockVersion": lock_version}
        if "name" in data:
            payload["name"] = data["name"]
        if "identifier" in data:
            payload["identifier"] = data["identifier"]
        if "description" in data:
            payload["description"] = {"raw": data["description"]}
        if "public" in data:
            payload["public"] = data["public"]
        if "status" in data:
            payload["status"] = data["status"]
        if "parent_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["parent"] = {
                "href": f"/api/v3/projects/{data['parent_id']}"
            }

        return await self._request("PATCH", f"/projects/{project_id}", payload)

    async def delete_project(self, project_id: int) -> bool:
        """Delete a project."""
        await self._request("DELETE", f"/projects/{project_id}")
        return True

    async def get_roles(self) -> Dict:
        """Retrieve available roles."""
        result = await self._request("GET", "/roles")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def get_role(self, role_id: int) -> Dict:
        """Retrieve a specific role by ID."""
        return await self._request("GET", f"/roles/{role_id}")

    async def create_membership(self, data: Dict) -> Dict:
        """Create a new membership."""
        payload = {"_links": {}}
        if "project_id" in data:
            payload["_links"]["project"] = {
                "href": f"/api/v3/projects/{data['project_id']}"
            }
        if "user_id" in data:
            payload["_links"]["principal"] = {
                "href": f"/api/v3/users/{data['user_id']}"
            }
        elif "group_id" in data:
            payload["_links"]["principal"] = {
                "href": f"/api/v3/groups/{data['group_id']}"
            }
        if "role_ids" in data:
            payload["_links"]["roles"] = [
                {"href": f"/api/v3/roles/{role_id}"} for role_id in data["role_ids"]
            ]
        elif "role_id" in data:
            payload["_links"]["roles"] = [{"href": f"/api/v3/roles/{data['role_id']}"}]
        if "notification_message" in data:
            payload["notificationMessage"] = {"raw": data["notification_message"]}

        return await self._request("POST", "/memberships", payload)

    async def update_membership(self, membership_id: int, data: Dict) -> Dict:
        """Update an existing membership."""
        try:
            current_membership = await self.get_membership(membership_id)
            lock_version = current_membership.get("lockVersion", 0)
        except:
            lock_version = 0

        payload = {"lockVersion": lock_version}
        if "role_ids" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["roles"] = [
                {"href": f"/api/v3/roles/{role_id}"} for role_id in data["role_ids"]
            ]
        elif "role_id" in data:
            if "_links" not in payload:
                payload["_links"] = {}
            payload["_links"]["roles"] = [{"href": f"/api/v3/roles/{data['role_id']}"}]
        if "notification_message" in data:
            payload["notificationMessage"] = {"raw": data["notification_message"]}

        return await self._request("PATCH", f"/memberships/{membership_id}", payload)

    async def delete_membership(self, membership_id: int) -> bool:
        """Delete a membership."""
        await self._request("DELETE", f"/memberships/{membership_id}")
        return True

    async def get_membership(self, membership_id: int) -> Dict:
        """Retrieve a specific membership by ID."""
        return await self._request("GET", f"/memberships/{membership_id}")

    async def set_work_package_parent(
        self, work_package_id: int, parent_id: int
    ) -> Dict:
        """Set a parent for a work package."""
        try:
            current_wp = await self.get_work_package(work_package_id)
            lock_version = current_wp.get("lockVersion", 0)
        except:
            lock_version = 0

        payload = {
            "lockVersion": lock_version,
            "_links": {"parent": {"href": f"/api/v3/work_packages/{parent_id}"}},
        }

        return await self._request(
            "PATCH", f"/work_packages/{work_package_id}", payload
        )

    async def remove_work_package_parent(self, work_package_id: int) -> Dict:
        """Remove parent relationship from a work package."""
        try:
            current_wp = await self.get_work_package(work_package_id)
            lock_version = current_wp.get("lockVersion", 0)
        except:
            lock_version = 0

        payload = {"lockVersion": lock_version, "_links": {"parent": None}}

        return await self._request(
            "PATCH", f"/work_packages/{work_package_id}", payload
        )

    async def list_work_package_children(
        self, parent_id: int, include_descendants: bool = False
    ) -> Dict:
        """List all child work packages of a parent."""
        if include_descendants:
            filters = json.dumps(
                [{"descendantsOf": {"operator": "=", "values": [str(parent_id)]}}]
            )
        else:
            filters = json.dumps(
                [{"parent": {"operator": "=", "values": [str(parent_id)]}}]
            )

        endpoint = f"/work_packages?filters={quote(filters)}"
        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def create_work_package_relation(self, data: Dict) -> Dict:
        """Create a relationship between work packages."""
        from_id = data.get("from_id")
        if not from_id:
            raise ValueError("from_id is required")
        
        payload = {
            "_links": {
                "to": {"href": f"/api/v3/work_packages/{data['to_id']}"}
            }
        }
        
        if "relation_type" in data:
            payload["type"] = data["relation_type"]
        if "lag" in data:
            payload["lag"] = data["lag"]
        if "description" in data:
            payload["description"] = data["description"]

        # OpenProject creates relations on the source work package
        return await self._request("POST", f"/work_packages/{from_id}/relations", payload)

    async def list_work_package_relations(
        self, work_package_id: Optional[int] = None, filters: Optional[str] = None
    ) -> Dict:
        """List work package relations."""
        if work_package_id:
            # Get relations for a specific work package
            endpoint = f"/work_packages/{work_package_id}/relations"
        else:
            endpoint = "/relations"
        
        if filters:
            encoded_filters = quote(filters)
            endpoint += f"?filters={encoded_filters}"

        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def update_work_package_relation(self, relation_id: int, data: Dict) -> Dict:
        """Update an existing work package relation."""
        try:
            current_relation = await self.get_work_package_relation(relation_id)
            lock_version = current_relation.get("lockVersion", 0)
        except:
            lock_version = 0

        payload = {"lockVersion": lock_version}
        if "relation_type" in data:
            payload["type"] = data["relation_type"]
        if "lag" in data:
            payload["lag"] = data["lag"]
        if "description" in data:
            payload["description"] = data["description"]

        return await self._request("PATCH", f"/relations/{relation_id}", payload)

    async def delete_work_package_relation(self, relation_id: int) -> bool:
        """Delete a work package relation."""
        await self._request("DELETE", f"/relations/{relation_id}")
        return True

    async def get_work_package_relation(self, relation_id: int) -> Dict:
        """Retrieve a specific work package relation by ID."""
        return await self._request("GET", f"/relations/{relation_id}")

    # =========================================================================
    # Work Package Hierarchy Methods
    # =========================================================================

    async def get_work_package_hierarchy(
        self, work_package_id: int, include_ancestors: bool = True, include_descendants: bool = True
    ) -> Dict:
        """
        Get the full hierarchy of a work package (ancestors and descendants).
        
        Returns:
            Dict with work_package, ancestors, and descendants
        """
        result = {
            "work_package": await self.get_work_package(work_package_id),
            "ancestors": [],
            "descendants": []
        }
        
        # Get ancestors by traversing parent links
        if include_ancestors:
            current_wp = result["work_package"]
            while True:
                parent_link = current_wp.get("_links", {}).get("parent", {})
                parent_href = parent_link.get("href") if parent_link else None
                if not parent_href:
                    break
                # Extract parent ID from href
                parent_id = int(parent_href.split("/")[-1])
                parent_wp = await self.get_work_package(parent_id)
                result["ancestors"].insert(0, parent_wp)  # Insert at beginning to maintain order
                current_wp = parent_wp
        
        # Get descendants using parent filter (direct children only, then recurse if needed)
        if include_descendants:
            # Get all children recursively
            all_descendants = []
            to_process = [work_package_id]
            processed = set()
            
            while to_process:
                current_id = to_process.pop(0)
                if current_id in processed:
                    continue
                processed.add(current_id)
                
                # Get direct children
                children_result = await self.list_work_package_children(current_id, include_descendants=False)
                children = children_result.get("_embedded", {}).get("elements", [])
                
                for child in children:
                    child_id = child.get("id")
                    if child_id and child_id not in processed:
                        all_descendants.append(child)
                        to_process.append(child_id)
            
            result["descendants"] = all_descendants
        
        return result

    # =========================================================================
    # Work Package Activities/Comments Methods
    # =========================================================================

    async def get_work_package_activities(
        self, work_package_id: int, offset: Optional[int] = None, page_size: Optional[int] = None
    ) -> Dict:
        """Get activities (including comments) for a work package."""
        endpoint = f"/work_packages/{work_package_id}/activities"
        query_params = []
        if offset is not None:
            query_params.append(f"offset={offset}")
        if page_size is not None:
            query_params.append(f"pageSize={page_size}")
        if query_params:
            endpoint += "?" + "&".join(query_params)
        
        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def add_work_package_comment(
        self, work_package_id: int, comment: str, notify: bool = True
    ) -> Dict:
        """Add a comment to a work package."""
        payload = {
            "comment": {"raw": comment}
        }
        endpoint = f"/work_packages/{work_package_id}/activities"
        if not notify:
            endpoint += "?notify=false"
        return await self._request("POST", endpoint, payload)

    # =========================================================================
    # Work Package Watchers Methods
    # =========================================================================

    async def get_work_package_watchers(self, work_package_id: int) -> Dict:
        """Get watchers of a work package."""
        result = await self._request("GET", f"/work_packages/{work_package_id}/watchers")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def add_work_package_watcher(self, work_package_id: int, user_id: int) -> Dict:
        """Add a watcher to a work package."""
        payload = {
            "_links": {
                "user": {"href": f"/api/v3/users/{user_id}"}
            }
        }
        return await self._request("POST", f"/work_packages/{work_package_id}/watchers", payload)

    async def remove_work_package_watcher(self, work_package_id: int, user_id: int) -> bool:
        """Remove a watcher from a work package."""
        await self._request("DELETE", f"/work_packages/{work_package_id}/watchers/{user_id}")
        return True

    # =========================================================================
    # Work Package Attachments Methods
    # =========================================================================

    async def get_work_package_attachments(self, work_package_id: int) -> Dict:
        """Get attachments of a work package."""
        result = await self._request("GET", f"/work_packages/{work_package_id}/attachments")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def add_work_package_attachment(
        self, work_package_id: int, file_data: bytes, filename: str, 
        content_type: str = "application/octet-stream", description: Optional[str] = None
    ) -> Dict:
        """
        Add an attachment to a work package.
        
        Note: This uses multipart form data upload.
        """
        url = f"{self.base_url}/api/v3/work_packages/{work_package_id}/attachments"
        
        # Build form data
        form_data = aiohttp.FormData()
        form_data.add_field('file', file_data, filename=filename, content_type=content_type)
        if description:
            form_data.add_field('metadata', json.dumps({"description": {"raw": description}}), 
                              content_type='application/json')
        
        # Custom headers for multipart (without Content-Type as aiohttp will set it)
        headers = {
            "Authorization": f"Basic {self._encode_api_key()}",
            "Accept": "application/json",
            "User-Agent": "OpenProject-MCP/1.0.0",
        }
        
        ssl_context = ssl.create_default_context()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        timeout = aiohttp.ClientTimeout(total=60)  # Longer timeout for uploads
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            request_params = {
                "method": "POST",
                "url": url,
                "headers": headers,
                "data": form_data,
            }
            if self.proxy:
                request_params["proxy"] = self.proxy
            
            async with session.request(**request_params) as response:
                response_text = await response.text()
                if response.status >= 400:
                    raise Exception(self._format_error_message(response.status, response_text))
                return json.loads(response_text) if response_text else {}

    async def delete_attachment(self, attachment_id: int) -> bool:
        """Delete an attachment."""
        await self._request("DELETE", f"/attachments/{attachment_id}")
        return True

    async def get_attachment(self, attachment_id: int) -> Dict:
        """Get attachment details."""
        return await self._request("GET", f"/attachments/{attachment_id}")

    # =========================================================================
    # Custom Fields Methods
    # =========================================================================

    async def get_custom_fields(self) -> Dict:
        """Get all custom fields."""
        result = await self._request("GET", "/custom_fields")
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    async def update_work_package_custom_fields(
        self, work_package_id: int, custom_fields: Dict
    ) -> Dict:
        """
        Update custom fields on a work package.
        
        Args:
            work_package_id: The work package ID
            custom_fields: Dict mapping custom field IDs to values, e.g. {"customField1": "value"}
        """
        current_wp = await self.get_work_package(work_package_id)
        payload = {"lockVersion": current_wp.get("lockVersion", 0)}
        
        # Custom fields are set directly on the payload
        for field_key, value in custom_fields.items():
            payload[field_key] = value
        
        return await self._request("PATCH", f"/work_packages/{work_package_id}", payload)

    # =========================================================================
    # Work Package Schema & Workflow Methods
    # =========================================================================

    async def get_work_package_schema(self, work_package_id: int) -> Dict:
        """
        Get the schema for a work package, including allowed status transitions.
        Uses the work package form endpoint to get available values.
        """
        # Get the current work package first
        current_wp = await self.get_work_package(work_package_id)
        
        # Use the form endpoint to get allowed values for updates
        # The form endpoint returns schema with allowedValues for fields
        payload = {
            "lockVersion": current_wp.get("lockVersion", 0)
        }
        
        form_result = await self._request("POST", f"/work_packages/{work_package_id}/form", payload)
        return form_result.get("_embedded", {}).get("schema", {})

    async def get_work_package_available_assignees(
        self, project_id: int
    ) -> Dict:
        """Get available assignees for work packages in a project."""
        # OpenProject uses /projects/{id}/available_assignees or memberships
        try:
            result = await self._request("GET", f"/projects/{project_id}/available_assignees")
            if "_embedded" not in result:
                result["_embedded"] = {"elements": []}
            return result
        except Exception:
            # Fallback to memberships endpoint
            try:
                result = await self.get_memberships(project_id=project_id)
                # Extract users from memberships
                members = result.get("_embedded", {}).get("elements", [])
                users = []
                for m in members:
                    principal = m.get("_embedded", {}).get("principal", {})
                    if principal.get("_type") == "User":
                        users.append(principal)
                return {"_embedded": {"elements": users}}
            except:
                return {"_embedded": {"elements": []}}

    async def get_available_relations_for_work_package(self, work_package_id: int) -> Dict:
        """Get available relation types for a work package."""
        return await self._request("GET", f"/work_packages/{work_package_id}/available_relation_candidates")

    # =========================================================================
    # Time Entry Activities Methods
    # =========================================================================

    async def get_time_entry_activities(self, project_id: Optional[int] = None) -> Dict:
        """Get time entry activities (categories for time tracking)."""
        # The activities endpoint is available at /time_entries/activities in OpenProject
        # But may require project context in some versions
        if project_id:
            endpoint = f"/projects/{project_id}/types"  # Fallback to types for now
            # Try project-specific activities if available
            try:
                result = await self._request("GET", f"/projects/{project_id}/time_entry_activities")
                if "_embedded" not in result:
                    result["_embedded"] = {"elements": []}
                return result
            except:
                pass
        
        # Try global activities endpoint
        try:
            result = await self._request("GET", "/time_entries/activities")
            if "_embedded" not in result:
                result["_embedded"] = {"elements": []}
            return result
        except:
            # Return empty result if endpoint not available
            return {"_embedded": {"elements": []}}

    async def get_time_entry(self, time_entry_id: int) -> Dict:
        """Get a specific time entry."""
        return await self._request("GET", f"/time_entries/{time_entry_id}")

    # =========================================================================
    # Work Package Query Methods
    # =========================================================================

    async def query_work_packages(
        self,
        project_id: Optional[int] = None,
        filters: Optional[list] = None,
        sort_by: Optional[str] = None,
        group_by: Optional[str] = None,
        offset: Optional[int] = None,
        page_size: Optional[int] = None,
        select: Optional[list] = None,
    ) -> Dict:
        """
        Advanced work package query with flexible filters.
        
        Args:
            project_id: Optional project ID to scope the query
            filters: List of filter objects, e.g. [{"status_id": {"operator": "=", "values": ["1", "2"]}}]
            sort_by: Sort specification, e.g. "subject:asc" or [["subject", "asc"], ["id", "desc"]]
            group_by: Group by attribute, e.g. "status"
            offset: Pagination offset
            page_size: Number of results per page
            select: List of fields to include in response
        """
        if project_id:
            endpoint = f"/projects/{project_id}/work_packages"
        else:
            endpoint = "/work_packages"
        
        query_params = []
        
        if filters:
            encoded_filters = quote(json.dumps(filters))
            query_params.append(f"filters={encoded_filters}")
        
        if sort_by:
            if isinstance(sort_by, list):
                sort_spec = json.dumps(sort_by)
            else:
                sort_spec = f'[["{sort_by.split(":")[0]}", "{sort_by.split(":")[1] if ":" in sort_by else "asc"}"]]'
            query_params.append(f"sortBy={quote(sort_spec)}")
        
        if group_by:
            query_params.append(f"groupBy={group_by}")
        
        if offset is not None:
            query_params.append(f"offset={offset}")
        
        if page_size is not None:
            query_params.append(f"pageSize={page_size}")
        
        if select:
            query_params.append(f"select={','.join(select)}")
        
        if query_params:
            endpoint += "?" + "&".join(query_params)
        
        result = await self._request("GET", endpoint)
        if "_embedded" not in result:
            result["_embedded"] = {"elements": []}
        elif "elements" not in result.get("_embedded", {}):
            result["_embedded"]["elements"] = []
        return result

    # =========================================================================
    # Bulk Operations Methods
    # =========================================================================

    async def bulk_create_work_packages(
        self, project_id: int, work_packages: list, continue_on_error: bool = False
    ) -> Dict:
        """
        Create multiple work packages in batch.
        
        Args:
            project_id: Project ID for all work packages
            work_packages: List of work package definitions
            continue_on_error: If True, continue creating even if some fail
            
        Returns:
            Dict with created work packages and any errors
        """
        results = {
            "success": True,
            "created": [],
            "errors": [],
            "total_requested": len(work_packages),
        }
        
        for i, wp_data in enumerate(work_packages):
            try:
                # Ensure project is set
                wp_data["project"] = project_id
                
                # Build the payload
                form_payload = {"_links": {}}
                form_payload["_links"]["project"] = {"href": f"/api/v3/projects/{project_id}"}
                
                if "type" in wp_data or "type_id" in wp_data:
                    type_id = wp_data.get("type") or wp_data.get("type_id")
                    form_payload["_links"]["type"] = {"href": f"/api/v3/types/{type_id}"}
                
                if "subject" in wp_data:
                    form_payload["subject"] = wp_data["subject"]
                
                # Get form to validate and prepare
                form = await self._request("POST", "/work_packages/form", form_payload)
                payload = form.get("payload", form_payload)
                payload["lockVersion"] = form.get("lockVersion", 0)
                
                # Add optional fields
                if "description" in wp_data:
                    payload["description"] = {"raw": wp_data["description"]}
                
                if "priority_id" in wp_data or "priority" in wp_data:
                    priority_id = wp_data.get("priority_id") or wp_data.get("priority")
                    if "_links" not in payload:
                        payload["_links"] = {}
                    payload["_links"]["priority"] = {"href": f"/api/v3/priorities/{priority_id}"}
                
                if "assignee_id" in wp_data or "assignee" in wp_data:
                    assignee_id = wp_data.get("assignee_id") or wp_data.get("assignee")
                    if "_links" not in payload:
                        payload["_links"] = {}
                    payload["_links"]["assignee"] = {"href": f"/api/v3/users/{assignee_id}"}
                
                if "parent_id" in wp_data or "parent" in wp_data:
                    parent_id = wp_data.get("parent_id") or wp_data.get("parent")
                    if "_links" not in payload:
                        payload["_links"] = {}
                    payload["_links"]["parent"] = {"href": f"/api/v3/work_packages/{parent_id}"}
                
                if "status_id" in wp_data or "status" in wp_data:
                    status_id = wp_data.get("status_id") or wp_data.get("status")
                    if "_links" not in payload:
                        payload["_links"] = {}
                    payload["_links"]["status"] = {"href": f"/api/v3/statuses/{status_id}"}
                
                if "startDate" in wp_data:
                    payload["startDate"] = wp_data["startDate"]
                if "dueDate" in wp_data:
                    payload["dueDate"] = wp_data["dueDate"]
                if "estimatedTime" in wp_data:
                    payload["estimatedTime"] = wp_data["estimatedTime"]
                
                # Create the work package
                created_wp = await self._request("POST", "/work_packages", payload)
                results["created"].append({
                    "index": i,
                    "id": created_wp.get("id"),
                    "subject": created_wp.get("subject"),
                })
                
            except Exception as e:
                error_info = {
                    "index": i,
                    "subject": wp_data.get("subject", "Unknown"),
                    "error": str(e),
                }
                results["errors"].append(error_info)
                results["success"] = False
                
                if not continue_on_error:
                    break
        
        results["created_count"] = len(results["created"])
        results["error_count"] = len(results["errors"])
        
        return results

    async def bulk_update_work_packages(
        self, updates: list, continue_on_error: bool = False
    ) -> Dict:
        """
        Update multiple work packages in batch.
        
        Args:
            updates: List of dicts with work_package_id and update data
            continue_on_error: If True, continue updating even if some fail
            
        Returns:
            Dict with updated work packages and any errors
        """
        results = {
            "success": True,
            "updated": [],
            "errors": [],
            "total_requested": len(updates),
        }
        
        for i, update_data in enumerate(updates):
            try:
                wp_id = update_data.get("work_package_id") or update_data.get("id")
                if not wp_id:
                    raise ValueError("work_package_id is required")
                
                # Build update payload
                data = {}
                for key in ["subject", "description", "type_id", "status_id", 
                           "priority_id", "assignee_id", "parent_id",
                           "percentage_done", "startDate", "dueDate", "estimatedTime"]:
                    if key in update_data:
                        data[key] = update_data[key]
                
                # Perform update
                updated_wp = await self.update_work_package(wp_id, data)
                results["updated"].append({
                    "index": i,
                    "id": updated_wp.get("id"),
                    "subject": updated_wp.get("subject"),
                })
                
            except Exception as e:
                error_info = {
                    "index": i,
                    "work_package_id": update_data.get("work_package_id") or update_data.get("id"),
                    "error": str(e),
                }
                results["errors"].append(error_info)
                results["success"] = False
                
                if not continue_on_error:
                    break
        
        results["updated_count"] = len(results["updated"])
        results["error_count"] = len(results["errors"])
        
        return results


