#!/bin/bash
# Starts Xvfb, Beholder engine, and captures frames from eval scenarios
set -e

DISPLAY_NUM=${BHDR_DISPLAY:-99}
PORT=${BHDR_PORT:-18080}
TOKEN=${BHDR_TOKEN:-$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")}
SOCKET_PATH="/tmp/bhdr_eval.sock"
SHM_NAME="/bhdr_eval"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Start Xvfb if not running
if ! pgrep -f "Xvfb :${DISPLAY_NUM}" > /dev/null; then
    echo "Starting Xvfb on :${DISPLAY_NUM}..."
    Xvfb :${DISPLAY_NUM} -screen 0 800x600x24 &
    sleep 1
fi
export DISPLAY=:${DISPLAY_NUM}

# Start Beholder engine + API
echo "Starting Beholder engine..."
PYTHONPATH="${REPO_ROOT}/src/python:${REPO_ROOT}/bazel-bin/src/bindings" \
    python3 -m bhdr.launcher \
    --socket "${SOCKET_PATH}" \
    --shm "${SHM_NAME}" \
    --port "${PORT}" \
    --token "${TOKEN}" &
BHDR_PID=$!
sleep 2

echo ""
echo "========================================="
echo "Beholder Eval Server Running"
echo "========================================="
echo "API:    http://127.0.0.1:${PORT}"
echo "Token:  ${TOKEN}"
echo "Socket: ${SOCKET_PATH}"
echo "SHM:    ${SHM_NAME}"
echo ""
echo "To capture an eval scenario:"
echo "  ./scripts/capture-scenario.sh e1_state_leak"
echo ""
echo "MCP server config written to .mcp.json"
echo "========================================="

# Write .mcp.json for Claude Code
# The MCP server uses stdio, so we point to the Python MCP server
cat > "${REPO_ROOT}/.mcp.json" << MCPEOF
{
  "mcpServers": {
    "gpa": {
      "command": "python3",
      "args": ["-m", "bhdr.mcp.server"],
      "env": {
        "PYTHONPATH": "${REPO_ROOT}/src/python:${REPO_ROOT}/bazel-bin/src/bindings",
        "BHDR_BASE_URL": "http://127.0.0.1:${PORT}",
        "BHDR_TOKEN": "${TOKEN}"
      }
    }
  }
}
MCPEOF

# Wait for Beholder engine
wait $BHDR_PID
