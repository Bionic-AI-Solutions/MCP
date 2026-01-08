# OpenProject MCP Server - Usage Guide

## Overview

The OpenProject MCP server provides comprehensive project management operations through the OpenProject API. It supports projects, work packages, users, attachments, and more.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "openproject-mcp-remote": {
      "url": "https://mcp.baisoln.com/openproject/mcp",
      "description": "OpenProject MCP Server - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-openproject-server

# Server will be available at http://localhost:8006
```

## Configuration

The OpenProject server requires environment variables for API connection:

```bash
export OPENPROJECT_URL="https://your-openproject-instance.com"
export OPENPROJECT_API_KEY="your-api-key"
```

## Available Tools

The OpenProject server provides extensive tools for project management. Here are the key categories:

### Connection & Testing

#### `test_connection` - Test API Connection

Test the connection to the OpenProject API.

**Response:**
```json
{
  "success": true,
  "message": "API connection successful!",
  "api_version": "API",
  "instance_version": "13.0.0"
}
```

### Projects

#### `list_projects` - List Projects

List all OpenProject projects.

**Parameters:**
- `active_only` (optional): Show only active projects (default: `true`)

**Example:**
```json
{
  "active_only": true
}
```

**Response:**
```json
{
  "success": true,
  "count": 5,
  "projects": [
    {
      "id": 1,
      "name": "My Project",
      "description": "Project description",
      "active": true,
      "public": false
    }
  ]
}
```

### Work Packages

#### `list_work_packages` - List Work Packages

List work packages with optional filtering.

**Parameters:**
- `project_id` (optional): Filter by project ID
- `status` (optional): Filter by status - `"open"` or `"closed"` (default: `"open"`)
- `offset` (optional): Pagination offset
- `page_size` (optional): Number of results per page

**Example:**
```json
{
  "project_id": 1,
  "status": "open",
  "page_size": 20
}
```

#### `create_work_package` - Create Work Package

Create a new work package.

**Parameters:**
- `project_id` (required): Project ID
- `subject` (required): Work package subject/title
- `type_id` (required): Work package type ID
- `description` (optional): Work package description
- `priority_id` (optional): Priority ID
- `assignee_id` (optional): Assignee user ID
- `start_date` (optional): Start date (YYYY-MM-DD)
- `due_date` (optional): Due date (YYYY-MM-DD)

**Example:**
```json
{
  "project_id": 1,
  "subject": "Implement new feature",
  "type_id": 36,
  "description": "Detailed description here",
  "priority_id": 5,
  "assignee_id": 2
}
```

#### `get_work_package` - Get Work Package

Get detailed information about a specific work package.

**Parameters:**
- `work_package_id` (required): Work package ID

#### `update_work_package` - Update Work Package

Update an existing work package.

**Parameters:**
- `work_package_id` (required): Work package ID
- `subject` (optional): New subject
- `description` (optional): New description
- `status_id` (optional): New status ID
- `priority_id` (optional): New priority ID
- `assignee_id` (optional): New assignee ID
- `percentage_done` (optional): Completion percentage (0-100)
- `start_date` (optional): Start date
- `due_date` (optional): Due date

### Work Package Types & Statuses

#### `list_types` - List Work Package Types

List available work package types.

**Parameters:**
- `project_id` (optional): Filter by project ID

#### `list_statuses` - List Statuses

List all available work package statuses.

#### `list_priorities` - List Priorities

List all available work package priorities.

### Users

#### `list_users` - List Users

List all users in the OpenProject instance.

**Parameters:**
- `active_only` (optional): Show only active users (default: `true`)

#### `get_user` - Get User

Get detailed information about a specific user.

**Parameters:**
- `user_id` (required): User ID

### Attachments

#### `list_work_package_attachments` - List Attachments

List attachments for a work package.

**Parameters:**
- `work_package_id` (required): Work package ID

#### `add_work_package_attachment` - Add Attachment

Add an attachment to a work package.

**Parameters:**
- `work_package_id` (required): Work package ID
- `filename` (required): Name of the file
- `file_data` (required): Base64-encoded file content
- `content_type` (optional): MIME type of the file
- `description` (optional): Attachment description

**Example:**
```json
{
  "work_package_id": 123,
  "filename": "document.pdf",
  "file_data": "base64-encoded-content...",
  "content_type": "application/pdf",
  "description": "Project document"
}
```

#### `delete_attachment` - Delete Attachment

Delete an attachment.

**Parameters:**
- `attachment_id` (required): Attachment ID

### Advanced Features

#### `query_work_packages` - Advanced Query

Advanced work package query with flexible filtering.

**Parameters:**
- `project_id` (optional): Project ID to scope the query
- `filters` (optional): JSON string of filter array
- `sort_by` (optional): Sort specification (e.g., `"subject:asc"`)
- `group_by` (optional): Group by attribute
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Results per page (default: 20)

**Filter Example:**
```json
{
  "filters": "[{\"type\": {\"operator\": \"=\", \"values\": [\"41\"]}}, {\"status\": {\"operator\": \"o\", \"values\": null}}]"
}
```

#### `search_work_packages` - Search Work Packages

Search work packages by subject text.

**Parameters:**
- `query` (required): Search text
- `project_id` (optional): Filter by project
- `type_ids` (optional): Comma-separated type IDs
- `status` (optional): Filter by status - `"open"`, `"closed"`, or `"all"` (default: `"open"`)
- `limit` (optional): Maximum results (default: 20)

### Bulk Operations

#### `bulk_create_work_packages` - Bulk Create

Create multiple work packages in batch.

**Parameters:**
- `project_id` (required): Project ID for all work packages
- `work_packages` (required): JSON string array of work package definitions
- `continue_on_error` (optional): Continue even if some fail (default: `false`)

#### `bulk_update_work_packages` - Bulk Update

Update multiple work packages in batch.

**Parameters:**
- `updates` (required): JSON string array of update objects
- `continue_on_error` (optional): Continue even if some fail (default: `false`)

### Work Package Relations

#### `create_work_package_relation` - Create Relation

Create a relationship between two work packages.

**Parameters:**
- `from_work_package_id` (required): Source work package ID
- `to_work_package_id` (required): Target work package ID
- `relation_type` (required): Type of relation - `"relates"`, `"duplicates"`, `"blocks"`, `"precedes"`, etc.
- `description` (optional): Description of the relation
- `lag` (optional): Lag in days (for precedes/follows relations)

#### `list_work_package_relations` - List Relations

List work package relations.

**Parameters:**
- `work_package_id` (optional): Get relations for specific work package
- `relation_type` (optional): Filter by relation type

### Hierarchy Management

#### `set_work_package_parent` - Set Parent

Set a parent work package (e.g., Story as child of Epic).

**Parameters:**
- `work_package_id` (required): Child work package ID
- `parent_id` (required): Parent work package ID

#### `get_work_package_children` - Get Children

Get child work packages of a parent.

**Parameters:**
- `parent_id` (required): Parent work package ID
- `project_id` (optional): Filter by project
- `type_id` (optional): Filter by type
- `status` (optional): Filter by status
- `include_descendants` (optional): Include all descendants (default: `false`)

#### `get_work_package_hierarchy` - Get Hierarchy

Get the full hierarchy of a work package (ancestors and descendants).

**Parameters:**
- `work_package_id` (required): Work package ID
- `include_ancestors` (optional): Include ancestors (default: `true`)
- `include_descendants` (optional): Include descendants (default: `true`)

### Comments & Activities

#### `add_work_package_comment` - Add Comment

Add a comment to a work package.

**Parameters:**
- `work_package_id` (required): Work package ID
- `comment` (required): Comment text (supports markdown)
- `notify` (optional): Notify watchers (default: `true`)

#### `list_work_package_activities` - List Activities

List activities (comments and changes) for a work package.

**Parameters:**
- `work_package_id` (required): Work package ID
- `limit` (optional): Maximum results (default: 20)

### Watchers

#### `add_work_package_watcher` - Add Watcher

Add a watcher to a work package.

**Parameters:**
- `work_package_id` (required): Work package ID
- `user_id` (required): User ID to add as watcher

#### `list_work_package_watchers` - List Watchers

List all watchers of a work package.

**Parameters:**
- `work_package_id` (required): Work package ID

## Resources

Access server information as resources:

- `openproject://info` - Get information about the OpenProject MCP server

## Example Workflow

1. Test connection:
   ```
   test_connection()
   ```

2. List projects:
   ```
   list_projects(active_only=true)
   ```

3. Create a work package:
   ```
   create_work_package(project_id=1, subject="New Task", type_id=36)
   ```

4. Add an attachment:
   ```
   add_work_package_attachment(work_package_id=123, filename="doc.pdf", file_data="base64...")
   ```

5. Update work package status:
   ```
   update_work_package(work_package_id=123, status_id=72, percentage_done=50)
   ```

## Notes

- The server requires `OPENPROJECT_URL` and `OPENPROJECT_API_KEY` environment variables
- Work package IDs and project IDs can be provided as integers or strings
- Attachment content must be base64-encoded
- Filter syntax follows OpenProject API filter format
- Bulk operations support transaction-like behavior with `continue_on_error`
- Relations support various types: relates, duplicates, blocks, precedes, follows, etc.

