---
name: comms
description: Communications hub — routes to /email (Mail) or /pdf (PDF Generator) for notifications and documents.
allowed-tools: Bash, TodoWrite
argument-hint: "<description of what you need>"
---

# Communications & Documents

This is a routing skill. Based on what you need, invoke the appropriate specialized skill:

## Available Communication Skills

| Skill | Server | When to Use |
|-------|--------|-------------|
| `/email` | Mail | Send emails (plain text, HTML, attachments, bulk) |
| `/pdf` | PDF Generator | Generate PDFs from HTML content |

## Routing Guide

Analyze `$ARGUMENTS` and invoke the matching skill:

- **Send email, notification, mail, SMTP** → Invoke `/email`
- **Generate PDF, report, document, HTML to PDF** → Invoke `/pdf`
- **Both** (e.g., "generate a report and email it") → Use `/pdf` first to generate, then `/email` to send

Both servers are multi-tenant. Default tenant: `base`.
