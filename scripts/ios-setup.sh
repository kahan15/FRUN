#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../ios"
[[ "$(uname -s)" == Darwin ]] || { echo 'The native iOS build requires a Mac with Xcode.'; exit 1; }
command -v xcodegen >/dev/null || { echo 'Install XcodeGen first: brew install xcodegen'; exit 1; }
xcodegen generate
open TerritoryRun.xcodeproj
echo 'In Xcode: select your Apple team, select your iPhone or simulator, and Run.'
