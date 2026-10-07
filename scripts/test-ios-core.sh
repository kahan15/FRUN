#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo 'Shared Apple framework tests require a Mac.'; exit 1; }
swift test --package-path ios
