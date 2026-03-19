#!/bin/bash
# Install MCP Skills Package for Claude Code
#
# Usage:
#   ./custom-skills/install.sh [--user|--machine] [--gateway-url URL]
#
# Modes:
#   --user     Install to ~/.claude/ (default, current user, all projects)
#   --machine  Install to /etc/claude-code/ (all users, requires root/sudo)
#
# Options:
#   --gateway-url URL  Set MCP gateway URL (default: https://mcp.baisoln.com)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="user"
GATEWAY_URL="https://mcp.baisoln.com"

# Parse arguments
while [ $# -gt 0 ]; do
    case "$1" in
        --user)     MODE="user"; shift ;;
        --machine)  MODE="machine"; shift ;;
        --gateway-url)
            GATEWAY_URL="${2:?--gateway-url requires a URL}"
            shift 2
            ;;
        -h|--help)
            head -12 "$0" | tail -10
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# Set target directory based on mode
if [ "$MODE" = "machine" ]; then
    TARGET_BASE="/etc/claude-code"
    CLAUDE_DIR="${TARGET_BASE}/.claude"
    SETTINGS_FILE="${TARGET_BASE}/managed-settings.json"
    GATEWAY_CONF="${TARGET_BASE}/mcp-gateway.conf"
    CLAUDE_MD="${TARGET_BASE}/CLAUDE.md"
    if [ "$(id -u)" -ne 0 ]; then
        echo "Machine mode requires root. Try: sudo $0 --machine"
        exit 1
    fi
else
    TARGET_BASE="${CLAUDE_CONFIG_DIR:-${HOME}/.claude}"
    CLAUDE_DIR="${TARGET_BASE}"
    SETTINGS_FILE="${TARGET_BASE}/settings.json"
    GATEWAY_CONF="${TARGET_BASE}/mcp-gateway.conf"
    CLAUDE_MD="${TARGET_BASE}/CLAUDE.md"
fi

SKILLS_DIR="${CLAUDE_DIR}/skills"
BIN_DIR="${CLAUDE_DIR}/bin"

echo "MCP Skills Package Installer"
echo "Mode: ${MODE}"
echo "Target: ${TARGET_BASE}"
echo "Gateway: ${GATEWAY_URL}"
echo ""

# ── Step 1: Create directories ─────────────────────────────────────────────

mkdir -p "$SKILLS_DIR" "$BIN_DIR"

# ── Step 2: Install mcp-rpc helper ─────────────────────────────────────────

cp "$SCRIPT_DIR/bin/mcp-rpc" "$BIN_DIR/mcp-rpc"
chmod +x "$BIN_DIR/mcp-rpc"
echo "  Installed: bin/mcp-rpc"

# ── Step 3: Install gateway config ─────────────────────────────────────────

cat > "$GATEWAY_CONF" << CONF
# MCP Gateway Configuration
# Used by mcp-rpc helper and Claude Code skills
# Override with MCP_GATEWAY_URL environment variable
GATEWAY_URL="${GATEWAY_URL}"
CONF
echo "  Installed: mcp-gateway.conf (${GATEWAY_URL})"

# ── Step 4: Install CLAUDE.md ──────────────────────────────────────────────

if [ -f "$CLAUDE_MD" ]; then
    cp "$CLAUDE_MD" "${CLAUDE_MD}.bak"
    echo "  Backed up: CLAUDE.md -> CLAUDE.md.bak"
fi

sed "s|{{GATEWAY_URL}}|${GATEWAY_URL}|g" "$SCRIPT_DIR/claude.md.template" > "$CLAUDE_MD"
echo "  Installed: CLAUDE.md"

# ── Step 5: Install all skills ─────────────────────────────────────────────

SKILL_COUNT=0

for skill_file in "$SCRIPT_DIR"/*.skill.md; do
    [ -f "$skill_file" ] || continue

    # Extract skill name from filename (e.g., db.skill.md -> db)
    skill_name="$(basename "$skill_file" .skill.md)"
    dest_dir="$SKILLS_DIR/$skill_name"

    mkdir -p "$dest_dir"
    cp "$skill_file" "$dest_dir/SKILL.md"
    SKILL_COUNT=$((SKILL_COUNT + 1))
done

echo "  Installed: ${SKILL_COUNT} skills"

# ── Step 6: Add mcp-rpc to permissions (user mode only) ───────────────────

if [ "$MODE" = "user" ] && [ -f "$SETTINGS_FILE" ]; then
    # Check if the specific wildcard mcp-rpc permission already exists
    if ! grep -q "Bash(${BIN_DIR}/mcp-rpc:" "$SETTINGS_FILE" 2>/dev/null; then
        # Use python3 to safely merge the permission
        python3 -c "
import json, sys
try:
    with open('$SETTINGS_FILE', 'r') as f:
        settings = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    settings = {}

perms = settings.setdefault('permissions', {})
allow = perms.setdefault('allow', [])
new_perm = 'Bash(${BIN_DIR}/mcp-rpc:*)'
if new_perm not in allow:
    allow.append(new_perm)
    with open('$SETTINGS_FILE', 'w') as f:
        json.dump(settings, f, indent=2)
    print('  Added: mcp-rpc permission to settings.json')
else:
    print('  Skipped: mcp-rpc permission already present')
" 2>/dev/null || echo "  Warning: Could not update settings.json permissions"
    fi
elif [ "$MODE" = "user" ] && [ ! -f "$SETTINGS_FILE" ]; then
    # Create settings file with just the permission
    python3 -c "
import json
settings = {
    'permissions': {
        'allow': ['Bash(${BIN_DIR}/mcp-rpc:*)']
    }
}
with open('$SETTINGS_FILE', 'w') as f:
    json.dump(settings, f, indent=2)
print('  Created: settings.json with mcp-rpc permission')
"
fi

# ── Step 7: Summary ────────────────────────────────────────────────────────

echo ""
echo "Installation complete!"
echo ""
echo "Skills installed (${SKILL_COUNT} total):"

# List installed skills with descriptions
for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    desc=$(grep '^description:' "$skill_dir/SKILL.md" 2>/dev/null | sed 's/^description: *//' | head -1)
    printf "  /%-16s %s\n" "$skill_name" "${desc:-(no description)}"
done

echo ""
echo "Quick start:"
echo "  1. Start Claude Code in any project directory"
echo "  2. Type /mcp servers to see available MCP servers"
echo "  3. Type /db to start working with PostgreSQL"
echo "  4. Type /data to get routed to the right data skill"
echo ""
echo "Helper script: ${BIN_DIR}/mcp-rpc"
echo "Gateway config: ${GATEWAY_CONF}"
echo "Capability catalog: ${CLAUDE_MD}"
