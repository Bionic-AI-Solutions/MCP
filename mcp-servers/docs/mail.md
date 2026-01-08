# Mail MCP Server - Usage Guide

## Overview

The Mail MCP server provides email sending operations with multi-tenant support. Each tenant connects to their own mail service API.

## Connection

### Remote (HTTPS)
If using Cursor or another MCP client, add this to your MCP configuration:

```json
{
  "mcpServers": {
    "mail-mcp-remote": {
      "url": "https://mcp.bionicaisolutions.com/mail/mcp",
      "description": "Mail Service MCP Server - External access via HTTPS"
    }
  }
}
```

### Local Development
```bash
# Using docker-compose
docker compose up -d mcp-mail-server

# Server will be available at http://localhost:8005
```

## Getting Started

### Step 1: Register a Tenant

Before using the server, register a tenant with your mail service API credentials:

**Tool:** `mail_register_tenant`

**Parameters:**
- `tenant_id` (required): Unique identifier (e.g., "my-tenant", "user-123")
- `api_key` (required): JWT token or API key for mail service authentication
- `mail_api_url` (optional): Mail service API URL (default: from config)
- `default_from_email` (optional): Default sender email address
- `default_from_name` (optional): Default sender name

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "api_key": "your-jwt-token-here",
  "mail_api_url": "http://mail-service.mail:8000",
  "default_from_email": "noreply@example.com",
  "default_from_name": "My App"
}
```

### Step 2: Use the Tools

Once registered, you can use the following tools:

## Available Tools

### 1. `mail_send_email` - Send Single Email

Send a single email via the mail service API.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `to` (required): List of recipient email addresses
- `subject` (required): Email subject
- `body` (required): Email body content
- `cc` (optional): List of CC recipient email addresses
- `bcc` (optional): List of BCC recipient email addresses
- `body_type` (optional): Body type - `"text"` or `"html"` (default: `"text"`)
- `from_email` (optional): Sender email address (uses default if not provided)
- `from_name` (optional): Sender name (uses default if not provided)
- `reply_to` (optional): Reply-to email address

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "to": ["recipient@example.com"],
  "subject": "Test Email",
  "body": "This is a test email from the Mail MCP server.",
  "body_type": "text"
}
```

**Response:**
```json
{
  "success": true,
  "message_id": "msg-123456",
  "recipients_count": 1,
  "error": null
}
```

### 2. `mail_send_email_with_attachments` - Send Email with Attachments

Send an email with file attachments via the mail service API.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `to` (required): List of recipient email addresses
- `subject` (required): Email subject
- `body` (required): Email body content
- `attachments` (required): List of attachment objects, each with:
  - `filename` (required): Name of the attachment file
  - `content` (required): File content as base64-encoded string
  - `content_type` (optional): MIME type of the file (default: `"application/octet-stream"`)
- `cc` (optional): List of CC recipient email addresses
- `bcc` (optional): List of BCC recipient email addresses
- `body_type` (optional): Body type - `"text"` or `"html"` (default: `"text"`)
- `from_email` (optional): Sender email address
- `from_name` (optional): Sender name
- `reply_to` (optional): Reply-to email address

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "to": ["recipient@example.com"],
  "subject": "Email with Attachment",
  "body": "Please find the attached file.",
  "attachments": [
    {
      "filename": "document.pdf",
      "content": "base64-encoded-pdf-content...",
      "content_type": "application/pdf"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message_id": "msg-123457",
  "recipients_count": 1,
  "error": null
}
```

### 3. `mail_send_bulk_emails` - Send Bulk Emails

Send multiple emails concurrently via the mail service API.

**Parameters:**
- `tenant_id` (required): Your registered tenant ID
- `emails` (required): List of email objects, each with:
  - `to` (required): List of recipient email addresses
  - `subject` (required): Email subject
  - `body` (required): Email body content
  - `body_type` (optional): Body type - `"text"` or `"html"`
  - `cc` (optional): List of CC recipients
  - `bcc` (optional): List of BCC recipients
  - `from_email` (optional): Sender email
  - `from_name` (optional): Sender name
  - `reply_to` (optional): Reply-to email

**Example:**
```json
{
  "tenant_id": "my-tenant",
  "emails": [
    {
      "to": ["user1@example.com"],
      "subject": "Welcome User 1",
      "body": "Welcome to our service!"
    },
    {
      "to": ["user2@example.com"],
      "subject": "Welcome User 2",
      "body": "Welcome to our service!"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "total_emails": 2,
  "successful": 2,
  "failed": 0,
  "results": [
    {
      "success": true,
      "message_id": "msg-123458",
      "recipients_count": 1
    },
    {
      "success": true,
      "message_id": "msg-123459",
      "recipients_count": 1
    }
  ]
}
```

## Configuration via Environment Variables

You can also pre-configure tenants using environment variables:

```bash
# Format: MAIL_TENANT_{TENANT_ID}_API_KEY
export MAIL_TENANT_1_API_KEY="your-jwt-token"
export MAIL_TENANT_1_MAIL_API_URL="http://mail-service.mail:8000"
export MAIL_TENANT_1_DEFAULT_FROM_EMAIL="noreply@example.com"
export MAIL_TENANT_1_DEFAULT_FROM_NAME="My App"
```

## Features

- **Multi-tenant**: Each tenant connects to their own mail service API
- **HTML and text emails**: Support for both plain text and HTML email bodies
- **Attachments**: Send emails with file attachments (base64-encoded)
- **Bulk sending**: Send multiple emails concurrently
- **Default sender**: Configure default from email and name per tenant
- **Redis persistence**: Tenant configurations persist across restarts

## Resources

Access tenant information as resources:

- `mail://{tenant_id}/info` - Get tenant-specific information
- `mail://info` - Get information about the Mail MCP server

## Example Workflow

1. Register your tenant:
   ```
   mail_register_tenant(tenant_id="my-tenant", api_key="your-token", mail_api_url="http://mail-service:8000")
   ```

2. Send a simple email:
   ```
   mail_send_email(tenant_id="my-tenant", to=["user@example.com"], subject="Hello", body="Hello, World!")
   ```

3. Send an email with attachment:
   ```
   mail_send_email_with_attachments(
     tenant_id="my-tenant",
     to=["user@example.com"],
     subject="Document",
     body="See attachment",
     attachments=[{"filename": "doc.pdf", "content": "base64...", "content_type": "application/pdf"}]
   )
   ```

4. Send bulk emails:
   ```
   mail_send_bulk_emails(tenant_id="my-tenant", emails=[{...}, {...}])
   ```

## Notes

- Tenant configurations are stored in Redis (DB 4)
- Attachment content must be base64-encoded
- HTML emails are supported via `body_type="html"`
- Default sender information can be set per tenant
- Bulk emails are sent concurrently for better performance
- The server requires a mail service API endpoint

