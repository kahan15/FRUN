#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ "$(uname -s)" == Darwin ]] || { echo 'Shared Apple framework checks require a Mac.'; exit 1; }
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
flags=(-D CORE_CHECKS)
# Optional local compiler-workaround overlay; never changes the installed Apple toolchain.
if [[ -n "${TERRITORY_SWIFT_VFS_OVERLAY:-}" ]]; then
  flags+=(-vfsoverlay "$TERRITORY_SWIFT_VFS_OVERLAY")
fi
swiftc -parse-as-library -swift-version 5 -module-cache-path "$build_dir/cache" "${flags[@]}" \
  ios/TerritoryRun/Models/*.swift \
  ios/TerritoryRun/Services/{LocalFiles,TrackingJournal,APIClient,Keychain,AccountDeletion}.swift \
  ios/CoreChecks/*.swift -o "$build_dir/core-checks"
"$build_dir/core-checks"
