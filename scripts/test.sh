#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# A unique project avoids stopping or deleting resources from another test run.
# There is no app .env, published port, host data mount or persistent game database.
test_project="territory-run-tests-$(date +%s)-$$"
compose=(docker compose --project-name "$test_project" -f compose.test.yaml)
cleanup() {
  "${compose[@]}" down --volumes >/dev/null
}
trap cleanup EXIT
"${compose[@]}" up --build --abort-on-container-exit --exit-code-from test
