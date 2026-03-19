---
name: devops
description: DevOps hub — routes to /observe (Langfuse), /projects (OpenProject), or /storage (MinIO) for ops tasks.
allowed-tools: Bash, TodoWrite
argument-hint: "<description of what you need>"
---

# DevOps & Operations

This is a routing skill. Based on what you need, invoke the appropriate specialized skill:

## Available DevOps Skills

| Skill | Server | When to Use |
|-------|--------|-------------|
| `/observe` | Langfuse | LLM observability — traces, spans, generations, scores |
| `/projects` | OpenProject | Project management — work packages, tasks, time tracking |
| `/storage` | MinIO | S3-compatible object storage — buckets, file upload/download |

## Routing Guide

Analyze `$ARGUMENTS` and invoke the matching skill:

- **Trace, span, observability, logging, Langfuse, LLM monitoring** → Invoke `/observe`
- **Work package, project, task, sprint, time tracking, OpenProject** → Invoke `/projects`
- **Upload, download, bucket, S3, object storage, file** → Invoke `/storage`

Note: `/observe` and `/storage` are multi-tenant (default: `base`). `/projects` is single-tenant.
