#!/usr/bin/env bash
# scripts/build-eval-dashboard.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src/python exec python3 -m gpa.eval.dashboard.build "$@"
