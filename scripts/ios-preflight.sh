#!/usr/bin/env bash
set -euo pipefail
[[ "$(uname -s)" == Darwin ]] || { echo 'A Mac with full Xcode is required.'; exit 1; }
if ! xcodebuild -version; then
  echo 'Install full Xcode 26 or later, open it once, and select it under Xcode → Settings → Locations → Command Line Tools.'
  exit 1
fi
sdk_version=$(xcrun --sdk iphoneos --show-sdk-version)
if [[ ${sdk_version%%.*} -lt 26 ]]; then
  echo 'Select Xcode with an iOS 26 or later SDK before an App Store upload.'
  exit 1
fi
echo "iOS SDK $sdk_version selected. Available simulator runtimes:"
xcrun simctl list runtimes
