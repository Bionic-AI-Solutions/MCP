---
name: email
description: Send emails, bulk emails, and emails with attachments via the Mail MCP server.
allowed-tools: Bash, TodoWrite
argument-hint: "<send|bulk> <to> <subject> [--tenant <id>]"
---

# Mail MCP Server

Server: `mail` at `mail/mcp` (stateful transport)
Alternate domain: `mcp.bionicaisolutions.com`
Multi-tenant. Default tenant: `base`.

## Tool Inventory

| Tool | Parameters | Description |
|------|-----------|-------------|
| `mail_send_email` | `tenant_id, to, subject, body, html_body?, cc?, bcc?, reply_to?` | Send a single email |
| `mail_send_email_with_attachments` | `tenant_id, to, subject, body, attachments (list of dicts), html_body?, cc?, bcc?` | Send email with attachments |
| `mail_send_bulk_emails` | `tenant_id, recipients (list), subject, body, html_body?` | Send bulk emails to multiple recipients |
| `mail_register_tenant` | `tenant_id, smtp_host, smtp_port, username, password, from_email, use_tls?, use_ssl?` | Register an SMTP connection |

## Usage Examples

Send a plain text email:
```bash
~/.claude/bin/mcp-rpc call mail mail_send_email '{"tenant_id": "base", "to": "user@example.com", "subject": "Hello", "body": "This is a test email."}'
```

Send an HTML email with CC:
```bash
~/.claude/bin/mcp-rpc call mail mail_send_email '{"tenant_id": "base", "to": "user@example.com", "subject": "Report Ready", "body": "See attached.", "html_body": "<h1>Report</h1><p>Your report is ready.</p>", "cc": "manager@example.com"}'
```

Send bulk emails:
```bash
~/.claude/bin/mcp-rpc call mail mail_send_bulk_emails '{"tenant_id": "base", "recipients": ["a@example.com", "b@example.com"], "subject": "Newsletter", "body": "Monthly update.", "html_body": "<h1>Newsletter</h1>"}'
```

## Tenant Handling

- All tools require `tenant_id`. Use `"base"` for the default SMTP connection.
- Register additional tenants with `mail_register_tenant` or via K8s secret `mcp-mail-tenants`.
- Attachments are passed as a list of dicts with keys: `filename`, `content` (base64), `content_type`.
- The `from_email` is configured per tenant at registration time, not per send call.
