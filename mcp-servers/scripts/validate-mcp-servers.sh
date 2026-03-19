#!/usr/bin/env bash
# =============================================================================
# MCP Server Validator
# Validates all MCP servers and their tenant connectivity in the K8s cluster.
#
# Usage:
#   ./validate-mcp-servers.sh [server-name|all] [--tenant <id>] [--verbose]
#
# Examples:
#   ./validate-mcp-servers.sh              # Validate all servers, tenant "base"
#   ./validate-mcp-servers.sh postgres     # Validate only postgres
#   ./validate-mcp-servers.sh all --verbose # Validate all with full output
#   ./validate-mcp-servers.sh minio --tenant prod  # Validate minio tenant "prod"
# =============================================================================

set -uo pipefail

NAMESPACE="mcp"
TENANT="base"
VERBOSE=false
TARGET="all"
CURL_IMAGE="curlimages/curl"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Counters
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0
TOTAL_COUNT=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant)
            TENANT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            head -14 "$0" | tail -12
            exit 0
            ;;
        *)
            TARGET="$1"
            shift
            ;;
    esac
done

# =============================================================================
# Server registry
# Format: name|service|port|stateless|tenant_model|test_tool|test_args
#
# stateless: yes = FASTMCP_STATELESS_HTTP, no = needs session ID
# tenant_model: multi = TenantManager, single = env vars only, none = no tenants
# test_tool: tools_list_only = skip tenant test, just verify tools/list
# =============================================================================
declare -a SERVERS=(
    "postgres|mcp-postgres-server|8001|no|multi|pg_execute_query|{\"tenant_id\":\"TENANT\",\"query\":\"SELECT current_database()\"}"
    "minio|mcp-minio-server|8002|no|multi|minio_list_buckets|{\"tenant_id\":\"TENANT\"}"
    "redis|mcp-redis-server|8010|no|multi|redis_info|{\"tenant_id\":\"TENANT\"}"
    "meilisearch|mcp-meilisearch-server|8007|no|multi|ms_list_indexes|{\"tenant_id\":\"TENANT\"}"
    "letta|mcp-letta-server|8012|no|multi|lt_list_tenants|{}"
    "langfuse|mcp-langfuse-server|8011|yes|multi|lf_create_trace|{\"tenant_id\":\"TENANT\",\"name\":\"validation-test\",\"tags\":[\"validation\"]}"
    "genImage|mcp-genimage-server|8008|no|multi|gi_generate_image|{\"tenant_id\":\"TENANT\",\"prompt\":\"red dot\",\"width\":128,\"height\":128,\"steps\":4}"
    "mail|mcp-mail-server|8005|no|multi|tools_list_only|{}"
    "openproject|mcp-openproject-server|8006|yes|single|test_connection|{}"
    "ai-mcp-server|mcp-ai-mcp-server|8009|yes|multi|tools_list_only|{}"
    "calculator|mcp-calculator-server|8000|yes|none|calc_add|{\"a\":2,\"b\":3}"
    "pdf-generator|mcp-pdf-generator-server|8003|no|none|tools_list_only|{}"
    "ffmpeg|mcp-ffmpeg-server|8004|yes|none|tools_list_only|{}"
)

# =============================================================================
# Utility functions
# =============================================================================

log_info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_pass()  { echo -e "${GREEN}[PASS]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }
log_bold()  { echo -e "${BOLD}$*${NC}"; }

# Generate unique pod name (lowercase, no special chars, max 63 chars)
pod_name() {
    local server="$1"
    local phase="$2"
    local rand
    rand=$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 6)
    local name="val-${server}-${phase}-${rand}"
    echo "${name,,}" | tr -cd 'a-z0-9-' | head -c 63
}

# Run a curl command inside the cluster via a temporary pod.
# Captures only stdout; kubectl stderr (pod lifecycle messages) is discarded.
cluster_curl() {
    local name="$1"
    local timeout="${2:-30}"
    shift 2
    kubectl run "$name" --rm -i --restart=Never \
        --image="$CURL_IMAGE" \
        --namespace="$NAMESPACE" \
        --pod-running-timeout="${timeout}s" \
        -- -s -m "$timeout" "$@" 2>/dev/null || true
}

# Run a curl command with verbose output (for extracting headers).
# Merges stderr into stdout so we can parse response headers.
cluster_curl_verbose() {
    local name="$1"
    local timeout="${2:-30}"
    shift 2
    kubectl run "$name" --rm -i --restart=Never \
        --image="$CURL_IMAGE" \
        --namespace="$NAMESPACE" \
        --pod-running-timeout="${timeout}s" \
        -- -s -v -m "$timeout" "$@" 2>&1 || true
}

# Extract the JSON body from a response that may be:
# - plain JSON (stateless HTTP)
# - SSE format with "event: message\ndata: {...}" (stateful HTTP)
# For SSE, there may be notification events before the actual result.
# We look for the data line containing "result" or "error" (the response to our request).
extract_json() {
    local response="$1"
    # Try SSE data lines — find the one that has our actual result (not notifications)
    local sse_result
    sse_result=$(echo "$response" | sed -n 's/^data: //p' | grep -E '"result"|"error"' | tail -1)
    if [[ -n "$sse_result" ]]; then
        echo "$sse_result"
        return
    fi
    # Try any SSE data line as fallback
    local sse_any
    sse_any=$(echo "$response" | sed -n 's/^data: //p' | tail -1)
    if [[ -n "$sse_any" ]]; then
        echo "$sse_any"
        return
    fi
    # Fall back to finding JSON object in the response (skip kubectl noise)
    # Prefer lines with "result" or "error" (actual response vs notifications)
    local json_result
    json_result=$(echo "$response" | grep -E '^\{' | grep -E '"result"|"error"' | tail -1)
    if [[ -n "$json_result" ]]; then
        echo "$json_result"
        return
    fi
    echo "$response" | grep -E '^\{' | tail -1
}

# =============================================================================
# Validation phases
# =============================================================================

# Phase 1: Check pod health
check_pod_health() {
    local service="$1"
    local pod_info
    pod_info=$(kubectl get pods -n "$NAMESPACE" -l "app=$service" \
        -o 'custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount' \
        --no-headers 2>/dev/null || true)

    if [[ -z "$pod_info" ]]; then
        log_fail "$service: No pods found"
        return 1
    fi

    local ready status restarts
    ready=$(echo "$pod_info" | head -1 | awk '{print $2}')
    status=$(echo "$pod_info" | head -1 | awk '{print $3}')
    restarts=$(echo "$pod_info" | head -1 | awk '{print $4}')

    if [[ "$status" != "Running" ]]; then
        log_fail "$service: Pod status is $status (not Running)"
        return 1
    fi

    if [[ "$ready" != "true" ]]; then
        log_fail "$service: Pod not ready (ready=$ready)"
        return 1
    fi

    if [[ "${restarts:-0}" -gt 5 ]] 2>/dev/null; then
        log_warn "$service: High restart count ($restarts)"
    fi

    if $VERBOSE; then
        log_info "$service: Pod running, ready=$ready, restarts=${restarts:-0}"
    fi
    return 0
}

# Phase 2: Quick log check
check_logs() {
    local service="$1"
    local logs
    logs=$(kubectl logs "deployment/$service" -n "$NAMESPACE" --tail=10 2>/dev/null || true)

    if [[ -z "$logs" ]]; then
        return 0
    fi

    # Exclude false positives from log error detection
    local real_errors
    real_errors=$(echo "$logs" | grep -iE "error|critical|traceback|exception" \
        | grep -viE "failureThreshold|isError|error_handling|on_error|ErrorBoundary" || true)

    if [[ -n "$real_errors" ]]; then
        log_warn "$service: Potential errors in recent logs"
        if $VERBOSE; then
            echo "$real_errors" | head -3
        fi
    fi

    return 0
}

# Phase 3a: MCP Initialize
# Strategy: always try stateless first (simple curl, no header parsing).
# If the server requires a session, the tools/call step will get an error
# containing "Missing session ID", and we retry with the verbose init.
mcp_initialize() {
    local service="$1"
    local port="$2"
    local stateless="$3"  # hint from registry, but we verify dynamically
    local url="http://${service}.${NAMESPACE}.svc.cluster.local:${port}/mcp"
    local pname

    local init_payload='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"validator","version":"1.0"}}}'

    # Step 1: Try simple stateless init (works for all servers)
    pname=$(pod_name "$service" "init")
    local response
    response=$(cluster_curl "$pname" 30 \
        -X POST "$url" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "$init_payload")

    # Check if init succeeded (response contains protocolVersion)
    local json_body
    json_body=$(extract_json "$response")

    if [[ -n "$json_body" ]] && echo "$json_body" | grep -q '"protocolVersion"'; then
        # Init succeeded. Now we need to determine if we need a session ID.
        # Try a quick tools/list without session to see if it works.
        pname=$(pod_name "$service" "probe")
        local probe_response
        probe_response=$(cluster_curl "$pname" 15 \
            -X POST "$url" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json, text/event-stream" \
            -d '{"jsonrpc":"2.0","id":99,"method":"tools/list","params":{}}')

        local probe_json
        probe_json=$(extract_json "$probe_response")

        # If tools/list works without session, server is stateless
        if [[ -n "$probe_json" ]] && echo "$probe_json" | grep -qE '"tools"'; then
            echo "__STATELESS__"
            return 0
        fi

        # If we get "Missing session ID", we need to get one via verbose init
        if echo "$probe_response" | grep -qi "session"; then
            pname=$(pod_name "$service" "sess")
            local sess_response
            sess_response=$(cluster_curl_verbose "$pname" 30 \
                -X POST "$url" \
                -H "Content-Type: application/json" \
                -H "Accept: application/json, text/event-stream" \
                -d "$init_payload")

            local session_id
            session_id=$(echo "$sess_response" | grep -i 'mcp-session-id' | grep -oE '[0-9a-f]{16,}' | head -1)

            if [[ -n "$session_id" ]]; then
                echo "$session_id"
                return 0
            fi
        fi

        # Fallback: assume stateless (init worked, probe might have just timed out)
        echo "__STATELESS__"
        return 0
    fi

    log_fail "$service: MCP initialize failed" >&2
    if $VERBOSE; then echo "$response" >&2; fi
    return 1
}

# Phase 3b: List tools
mcp_list_tools() {
    local service="$1"
    local port="$2"
    local session_id="$3"
    local url="http://${service}.${NAMESPACE}.svc.cluster.local:${port}/mcp"
    local pname
    pname=$(pod_name "$service" "tools")

    local -a curl_args=(
        -X POST "$url"
        -H "Content-Type: application/json"
        -H "Accept: application/json, text/event-stream"
    )
    if [[ "$session_id" != "__STATELESS__" ]]; then
        curl_args+=(-H "Mcp-Session-Id: $session_id")
    fi
    curl_args+=(-d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}')

    local response
    response=$(cluster_curl "$pname" 30 "${curl_args[@]}")

    local json_response
    json_response=$(extract_json "$response")

    if [[ -z "$json_response" ]]; then
        log_fail "$service: Empty response from tools/list" >&2
        echo "0"
        return 1
    fi

    # Count tools by counting "name" keys within tools array
    local tool_count
    tool_count=$(echo "$json_response" | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | wc -l)

    if [[ "$tool_count" -gt 0 ]]; then
        if $VERBOSE; then
            log_info "$service: $tool_count tools available" >&2
            echo "$json_response" | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | \
                sed 's/"name"[[:space:]]*:[[:space:]]*"\([^"]*\)"/    - \1/' >&2
        fi
        echo "$tool_count"
        return 0
    else
        log_fail "$service: No tools returned from tools/list" >&2
        if $VERBOSE; then echo "$json_response" | head -3 >&2; fi
        echo "0"
        return 1
    fi
}

# Phase 3c: Tenant connectivity test
mcp_tenant_test() {
    local service="$1"
    local port="$2"
    local session_id="$3"
    local tool_name="$4"
    local tool_args="$5"
    local url="http://${service}.${NAMESPACE}.svc.cluster.local:${port}/mcp"

    # Skip if tools_list_only
    if [[ "$tool_name" == "tools_list_only" ]]; then
        echo "SKIPPED"
        return 0
    fi

    # Replace TENANT placeholder with actual tenant ID
    tool_args="${tool_args//TENANT/$TENANT}"

    local pname
    pname=$(pod_name "$service" "test")

    local payload="{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool_name\",\"arguments\":$tool_args}}"

    local call_timeout=30
    # genImage needs more time for actual image generation
    if [[ "$tool_name" == "gi_generate_image" ]]; then
        call_timeout=120
    fi

    local -a curl_args=(
        -X POST "$url"
        -H "Content-Type: application/json"
        -H "Accept: application/json, text/event-stream"
    )
    if [[ "$session_id" != "__STATELESS__" ]]; then
        curl_args+=(-H "Mcp-Session-Id: $session_id")
    fi
    curl_args+=(-d "$payload")

    local response
    response=$(cluster_curl "$pname" "$call_timeout" "${curl_args[@]}")

    local json_response
    json_response=$(extract_json "$response")

    if [[ -z "$json_response" ]]; then
        echo "ERROR: Empty response"
        return 1
    fi

    # Check for explicit error
    if echo "$json_response" | grep -qE '"isError"[[:space:]]*:[[:space:]]*true'; then
        local err_msg
        err_msg=$(echo "$json_response" | grep -oE '"text"[[:space:]]*:[[:space:]]*"[^"]{0,100}' | head -1 | sed 's/"text"[[:space:]]*:[[:space:]]*"//')
        echo "ERROR: ${err_msg:-unknown}"
        return 1
    fi

    # Check for JSON-RPC error
    if echo "$json_response" | grep -qE '"error"[[:space:]]*:[[:space:]]*\{'; then
        local err_msg
        err_msg=$(echo "$json_response" | grep -oE '"message"[[:space:]]*:[[:space:]]*"[^"]{0,100}' | head -1 | sed 's/"message"[[:space:]]*:[[:space:]]*"//')
        echo "ERROR: ${err_msg:-unknown}"
        return 1
    fi

    # Check for success in structured content or text content
    if echo "$json_response" | grep -qE '"success"[[:space:]]*:[[:space:]]*true'; then
        if $VERBOSE; then
            log_info "$service: Tenant test succeeded" >&2
            echo "$json_response" | sed 's/"image_data":"[^"]*"/"image_data":"<truncated>"/g' | head -3 >&2
        fi
        echo "OK"
        return 0
    fi

    # Check for result field (calculator style: {"result": {"result": 5}})
    if echo "$json_response" | grep -qE '"result"'; then
        if $VERBOSE; then
            log_info "$service: Tool returned result" >&2
        fi
        echo "OK"
        return 0
    fi

    echo "ERROR: Unexpected response"
    if $VERBOSE; then echo "$json_response" | head -3 >&2; fi
    return 1
}

# =============================================================================
# Main validation loop
# =============================================================================

echo ""
log_bold "====================================================================="
log_bold "  MCP Server Validator"
log_bold "  Namespace: $NAMESPACE | Tenant: $TENANT | Target: $TARGET"
log_bold "====================================================================="
echo ""

# Results array for final summary
declare -a RESULTS=()

for entry in "${SERVERS[@]}"; do
    IFS='|' read -r name service port stateless tenant_model tool_name tool_args <<< "$entry"

    # Filter by target
    if [[ "$TARGET" != "all" && "$TARGET" != "$name" ]]; then
        continue
    fi

    TOTAL_COUNT=$((TOTAL_COUNT + 1))

    log_bold "--- Validating: $name ($service:$port) ---"

    pod_status="?"
    init_status="?"
    tool_count="?"
    tenant_status="?"
    result="?"

    # Phase 1: Pod health
    if check_pod_health "$service"; then
        pod_status="Running"
    else
        pod_status="DOWN"
        RESULTS+=("$name|$pod_status|FAIL|0|SKIP|FAIL")
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log_fail "$name: Pod not healthy, skipping remaining checks"
        echo ""
        continue
    fi

    # Phase 2: Log check (non-blocking, informational only)
    check_logs "$service"

    # Phase 3a: MCP Initialize
    session_id=""
    if session_id=$(mcp_initialize "$service" "$port" "$stateless"); then
        init_status="OK"
    else
        init_status="FAIL"
        RESULTS+=("$name|$pod_status|$init_status|0|SKIP|FAIL")
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log_fail "$name: MCP initialization failed, skipping remaining checks"
        echo ""
        continue
    fi

    # Phase 3b: List tools
    tool_count=$(mcp_list_tools "$service" "$port" "$session_id")
    if [[ ! "$tool_count" =~ ^[0-9]+$ ]]; then
        tool_count="0"
    fi

    # Phase 3c: Tenant test
    tenant_status=$(mcp_tenant_test "$service" "$port" "$session_id" "$tool_name" "$tool_args")

    # Determine final result
    if [[ "$tenant_status" == "SKIPPED" ]]; then
        result="WARN"
        WARN_COUNT=$((WARN_COUNT + 1))
        log_warn "$name: Tenant test skipped (tools/list only)"
    elif [[ "$tenant_status" == "OK" ]]; then
        result="PASS"
        PASS_COUNT=$((PASS_COUNT + 1))
        log_pass "$name: All checks passed"
    else
        result="FAIL"
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log_fail "$name: Tenant test failed - $tenant_status"
    fi

    RESULTS+=("$name|$pod_status|$init_status|$tool_count|$tenant_status|$result")
    echo ""
done

# =============================================================================
# Summary table
# =============================================================================

echo ""
log_bold "====================================================================="
log_bold "  Validation Summary"
log_bold "====================================================================="
echo ""

printf "${BOLD}%-16s %-12s %-10s %-8s %-24s %-8s${NC}\n" \
    "Server" "Pod" "MCP Init" "Tools" "Tenant Test" "Result"
printf "%-16s %-12s %-10s %-8s %-24s %-8s\n" \
    "----------------" "------------" "----------" "--------" "------------------------" "--------"

for entry in "${RESULTS[@]}"; do
    IFS='|' read -r name pod_status init_status tool_count tenant_status result <<< "$entry"

    # Color the result
    result_color="$NC"
    case "$result" in
        PASS) result_color="$GREEN" ;;
        WARN) result_color="$YELLOW" ;;
        FAIL) result_color="$RED" ;;
    esac

    # Truncate tenant_status if too long
    if [[ ${#tenant_status} -gt 22 ]]; then
        tenant_status="${tenant_status:0:21}~"
    fi

    printf "%-16s %-12s %-10s %-8s %-24s ${result_color}%-8s${NC}\n" \
        "$name" "$pod_status" "$init_status" "$tool_count" "$tenant_status" "$result"
done

echo ""
echo -e "${GREEN}PASS: $PASS_COUNT${NC}  ${YELLOW}WARN: $WARN_COUNT${NC}  ${RED}FAIL: $FAIL_COUNT${NC}  Total: $TOTAL_COUNT"
echo ""

# Exit code: 0 if no failures, 1 if any failure
if [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
fi
exit 0
