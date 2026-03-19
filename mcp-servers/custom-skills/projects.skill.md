---
name: projects
description: Manage OpenProject projects, work packages, time entries, users, and attachments.
allowed-tools: Bash, TodoWrite
argument-hint: "<list-projects|create-wp|update-status|log-time|...> [args]"
---

# OpenProject MCP Server

Server: `openproject` at `openproject/mcp` (stateless transport)
Single-tenant (no `tenant_id` needed). 44 tools organized by category.

## Tool Inventory

### Projects (5 tools)
`list_projects`, `get_project`, `create_project`, `update_project`, `delete_project`
-- Full CRUD for project management.

### Work Packages (9 tools)
`list_work_packages`, `create_work_package`, `get_work_package`, `update_work_package`, `delete_work_package`, `bulk_create_work_packages`, `bulk_update_work_packages`, `query_work_packages`, `search_work_packages`
-- Create, read, update, delete work packages. Bulk operations for batch changes. Query and search for filtering.

### Status & Progress (5 tools)
`update_work_package_status`, `list_statuses`, `list_priorities`, `list_types`, `get_work_package_schema`
-- Manage work package lifecycle: update status, list available statuses/priorities/types, get field schema.

### Hierarchy (4 tools)
`set_work_package_parent`, `remove_work_package_parent`, `get_work_package_children`, `get_work_package_hierarchy`
-- Parent-child relationships between work packages.

### Relations (3 tools)
`create_work_package_relation`, `list_work_package_relations`, `delete_work_package_relation`
-- Link work packages with relation types (blocks, follows, relates, etc.).

### Comments & Activity (2 tools)
`add_work_package_comment`, `list_work_package_activities`
-- Add comments to work packages and view activity history.

### Watchers (3 tools)
`add_work_package_watcher`, `remove_work_package_watcher`, `list_work_package_watchers`
-- Subscribe/unsubscribe users to work package notifications.

### Assignment (2 tools)
`assign_work_package`, `get_available_assignees`
-- Assign work packages to users. List users who can be assigned.

### Users (2 tools)
`list_users`, `get_user`
-- List and retrieve user details.

### Time (3 tools)
`log_time`, `list_time_entries`, `list_time_entry_activities`
-- Log time against work packages and list time entries.

### Attachments (3 tools)
`list_work_package_attachments`, `add_work_package_attachment`, `delete_attachment`
-- Upload, list, and delete file attachments on work packages.

### Custom Fields (2 tools)
`list_custom_fields`, `update_work_package_custom_fields`
-- List available custom fields and update their values on work packages.

### System (1 tool)
`test_connection`
-- Verify connectivity to the OpenProject instance.

## Usage Examples

List all projects:
```bash
~/.claude/bin/mcp-rpc call openproject list_projects '{}'
```

Create a work package (task) in a project:
```bash
~/.claude/bin/mcp-rpc call openproject create_work_package '{"project_id": 1, "subject": "Implement login page", "type": "Task", "priority": "High", "description": "Build the user login form with email/password authentication."}'
```

Log time against a work package:
```bash
~/.claude/bin/mcp-rpc call openproject log_time '{"work_package_id": 42, "hours": 2.5, "comment": "Frontend implementation", "activity": "Development"}'
```

## Notes

- This server is single-tenant. No `tenant_id` parameter is needed on any tool.
- Use `list_statuses`, `list_priorities`, and `list_types` to discover valid values before creating work packages.
- `query_work_packages` supports filter syntax for advanced queries (status, assignee, dates, etc.).
- `search_work_packages` does full-text search across work package subjects and descriptions.
- `bulk_create_work_packages` and `bulk_update_work_packages` accept arrays for batch operations.
- Use `test_connection` to verify the server can reach the OpenProject API.
