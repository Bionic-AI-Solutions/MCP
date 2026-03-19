# MCP Skills Package for Claude Code

A deployable package that gives Claude Code on-demand access to 13 MCP servers (217 tools) without bloating conversation context. Skills load lazily — only when invoked via `/skill-name`.

## Quick Install

```bash
# Install for current user (all projects)
./custom-skills/install.sh

# Install with custom gateway URL
./custom-skills/install.sh --gateway-url https://your-mcp-gateway.example.com

# Install machine-wide (all users, requires root)
sudo ./custom-skills/install.sh --machine
```

## What Gets Installed

```
~/.claude/
├── CLAUDE.md                      # Capability catalog (always loaded, ~60 lines)
├── bin/mcp-rpc                    # JSON-RPC helper script
├── mcp-gateway.conf               # Gateway URL config
└── skills/
    ├── calc/SKILL.md              # /calc → Calculator (7 tools)
    ├── db/SKILL.md                # /db → PostgreSQL (7 tools)
    ├── cache/SKILL.md             # /cache → Redis (55 tools)
    ├── search/SKILL.md            # /search → MeiliSearch (9 tools)
    ├── storage/SKILL.md           # /storage → MinIO (9 tools)
    ├── email/SKILL.md             # /email → Mail (4 tools)
    ├── pdf/SKILL.md               # /pdf → PDF Generator (3 tools)
    ├── media/SKILL.md             # /media → FFmpeg (8 tools)
    ├── images/SKILL.md            # /images → GenImage (4 tools)
    ├── ai/SKILL.md                # /ai → AI Server (31 tools)
    ├── observe/SKILL.md           # /observe → Langfuse (8 tools)
    ├── agents/SKILL.md            # /agents → Letta (18 tools)
    ├── projects/SKILL.md          # /projects → OpenProject (44 tools)
    ├── data/SKILL.md              # /data → Routes to /db, /cache, /search
    ├── creative/SKILL.md          # /creative → Routes to /images, /media, /ai
    ├── comms/SKILL.md             # /comms → Routes to /email, /pdf
    ├── devops/SKILL.md            # /devops → Routes to /observe, /projects, /storage
    ├── mcp/SKILL.md               # /mcp → Universal gateway & discovery
    ├── validate-mcp/SKILL.md      # /validate-mcp → Health checking
    └── manage-tenants/SKILL.md    # /manage-tenants → Tenant CRUD
```

## Usage

After installation, start Claude Code in any project directory:

```
# Direct access — when you know what you need
/db SELECT * FROM users WHERE active = true
/cache get my-key
/ai chat completion: "Summarize this document"

# Domain groups — when you're thinking about outcomes
/data                    → Routes to the right data skill
/creative                → Routes to image/media/AI skills

# Universal gateway — for discovery and ad-hoc calls
/mcp servers             → List all 13 MCP servers
/mcp health all          → Health check everything
/mcp tools postgres      → See what tools postgres has
/mcp call redis redis_ping '{"tenant_id":"base"}'

# Operations
/validate-mcp all        → Full infrastructure validation
/manage-tenants create myapp --servers postgres,redis,minio
```

## Architecture

**Why skills instead of native MCP server config?**

Claude Code loads MCP server tool schemas into context *always* when configured. With 217 tools, that's massive context bloat in every conversation. Skills load *lazily* — zero context cost until invoked. The `CLAUDE.md` catalog (~60 lines) is the only always-present context, serving as an index.

**How it works:**
1. `CLAUDE.md` lists available skills with routing hints
2. User invokes `/skill-name` → skill loads with tool inventory and instructions
3. Skill uses `~/.claude/bin/mcp-rpc` to make JSON-RPC calls to MCP servers over HTTPS
4. `mcp-rpc` handles session management, SSE parsing, and server routing

## mcp-rpc Helper

Standalone bash script for MCP-over-HTTP protocol:

```bash
mcp-rpc servers                              # List all servers
mcp-rpc health [server|all]                  # Quick health check
mcp-rpc tools <server>                       # List tools (live query)
mcp-rpc call <server> <tool> '{"args":...}'  # Call a tool
mcp-rpc init <server>                        # Initialize session
mcp-rpc discover [server|all]                # Live discovery
```

## Customization

Before installing, update these values if your infrastructure differs:

| Setting | Default | Where to Change |
|---------|---------|----------------|
| Gateway URL | `https://mcp.baisoln.com` | `--gateway-url` flag on install |
| Alt gateway | `https://mcp.bionicaisolutions.com` | `bin/mcp-rpc` ALT_DOMAIN_SERVERS |
| Default tenant | `base` | Each skill's tenant handling section |

## Project-Specific Skills

These skills stay project-level (not installed globally):

- `mcp-builder.skill.md` — Build and deploy new MCP servers (tightly coupled to this repo)
