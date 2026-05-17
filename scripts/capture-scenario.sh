#!/bin/bash
# Captures frames from an eval scenario
# Usage: ./scripts/capture-scenario.sh e1_state_leak
set -e

SCENARIO=$1
if [ -z "$SCENARIO" ]; then
    echo "Usage: $0 <scenario_name>"
    echo "Available: e1_state_leak e2_nan_propagation e3_index_buffer_obo ..."
    exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOCKET_PATH="${BHDR_SOCKET_PATH:-/tmp/bhdr_eval.sock}"
SHM_NAME="${BHDR_SHM_NAME:-/bhdr_eval}"

# Scenarios live under nested taxonomy packages (tests/eval/<cat>/<fw>/<slug>/);
# resolve the package via the source layout rather than assuming a flat package.
SRC_DIR=$(find "${REPO_ROOT}/tests/eval" -mindepth 2 -type d -name "${SCENARIO}" -print -quit)
if [ -z "$SRC_DIR" ]; then
    echo "ERROR: scenario directory not found under tests/eval for '${SCENARIO}'"
    exit 1
fi
PKG_REL="${SRC_DIR#${REPO_ROOT}/}"
BINARY="${REPO_ROOT}/bazel-bin/${PKG_REL}/${SCENARIO}"

if [ ! -f "$BINARY" ]; then
    echo "Building ${SCENARIO}..."
    bazel build "//${PKG_REL}:${SCENARIO}"
fi

echo "Running ${SCENARIO} under Beholder capture..."
LD_PRELOAD="${REPO_ROOT}/bazel-bin/src/shims/gl/libbhdr_gl.so" \
    BHDR_SOCKET_PATH="${SOCKET_PATH}" \
    BHDR_SHM_NAME="${SHM_NAME}" \
    "${BINARY}"

echo "Done. Frame captured. Query via REST API or MCP tools."
