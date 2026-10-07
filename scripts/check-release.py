#!/usr/bin/env python3
"""Fail closed on missing release settings; does not deploy or contact any service."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
from urllib.parse import urlsplit


def public_https(value, root_only=False):
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        port = url.port  # Reject malformed ports, even though the URL is not fetched here.
        if url.scheme != "https" or not host or url.username or url.password or url.fragment:
            return False
        if port not in (None, 443) or (root_only and (url.path not in ("", "/") or url.query)):
            return False
        if any(host == suffix or host.endswith("." + suffix) for suffix in
               ("localhost", "local", "internal", "test", "invalid", "example", "example.com", "example.org", "example.net")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return "." in host and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                                       for label in host.split("."))
    except ValueError:
        return False


def validate(values, check_sdk=False):
    errors = []
    for key in ("API_BASE_URL", "PRIVACY_POLICY_URL", "SUPPORT_URL"):
        if not public_https(values.get(key, ""), root_only=key == "API_BASE_URL"):
            errors.append(key + " must be a real public HTTPS URL (no local or example address).")
    bundle = values.get("APP_BUNDLE_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+){2,}", bundle) or bundle in (
        "com.territoryrun.app", "com.territoryrun.local") or bundle.startswith("com.example."):
        errors.append("APP_BUNDLE_ID must be your registered, unique production identifier.")
    if not re.fullmatch(r"[A-Z0-9]{10}", values.get("APPLE_TEAM_ID", "")):
        errors.append("APPLE_TEAM_ID must be the 10-character team identifier from your Apple account.")
    if values.get("PUSH_ENABLED") != "NO":
        errors.append("Keep PUSH_ENABLED=NO until APNs signing, entitlements and delivery have been verified.")
    if check_sdk:
        sdk = values.get("SDK_VERSION", "0")
        try:
            valid = int(sdk.split(".")[0]) >= 26
        except ValueError:
            valid = False
        if not valid:
            errors.append("Use Xcode 26 or later with an iOS 26 or later SDK for App Store uploads.")
    return errors


def read_config(path):
    values = {}
    for line in path.read_text().splitlines():
        if line.strip().startswith("//") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.split("//", 1)[0].strip().replace("$()", "")
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", action="store_true", help="Validate expanded Xcode build settings.")
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "ios/Config/Release.xcconfig")
    args = parser.parse_args()
    errors = validate(dict(os.environ) if args.environment else read_config(args.config), args.environment)
    if errors:
        print("Release configuration is incomplete:")
        for message in errors:
            print("error: " + message)
        print("Debug laptop development remains available. See docs/production-roadmap.md.")
        return 1
    print("Release settings passed static checks. Device testing, public URL checks and release approval remain required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
