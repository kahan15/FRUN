#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test_project="territory-run-smoke-$(date +%s)-$$"
compose=(docker compose --project-name "$test_project" -f compose.test.yaml -f compose.smoke.yaml)
cleanup() { "${compose[@]}" down --volumes >/dev/null; }
trap cleanup EXIT
"${compose[@]}" up -d --build --wait --wait-timeout 120 api
"${compose[@]}" exec -T api python - < backend/tests/smoke_runtime.py
