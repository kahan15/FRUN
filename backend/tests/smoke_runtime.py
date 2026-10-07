"""Run via scripts/smoke-test.sh inside a disposable runtime container.

This uses real HTTP and committed requests, without emitting credentials or routes.
"""

import json
import os
import urllib.error
import urllib.request
from uuid import uuid4

# Fail closed if someone tries to run this against their application database.
if os.environ.get("DATABASE_URL") != (
    "postgresql+psycopg://territory:disposable-test-password@test-db:5432/territory_test"
):
    raise SystemExit("This check requires the isolated smoke-test database.")
assert os.geteuid() != 0, "The runtime must run as an unprivileged user."


def request(method, path, payload=None, token=None, status=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request("http://127.0.0.1:8000" + path, data, headers, method=method)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == status, f"{method} {path}: HTTP {response.status}"
        return json.load(response)


assert request("GET", "/health/live") == {"status": "ok"}
ready = request("GET", "/health/ready")
assert ready["status"] == "ok" and "3.5" in ready["postgis"]
print("PASS: unprivileged runtime, real HTTP readiness, PostGIS 3.5")
name = "smoke" + uuid4().hex[:12]
password = "synthetic-smoke-password-123"
auth = request(
    "POST",
    "/api/v1/auth/register",
    {
        "email": name + "@example.com",
        "username": name,
        "display_name": "Synthetic smoke test",
        "sex": "X",
        "password": password,
    },
    status=201,
)
token = auth["access_token"]
assert request("GET", "/api/v1/auth/me", token=token)["username"] == name
assert request("GET", "/api/v1/territories", token=token)["features"] == []
second = request("POST", "/api/v1/auth/login", {"username": name, "password": password})
print("PASS: migrations, registration, persisted login, empty private map")
lookup = {"request_id": str(uuid4())}
request("DELETE", "/api/v1/auth/account", dict(lookup, password="wrong"), token, status=403)
assert request("GET", "/api/v1/auth/me", token=token)["username"] == name
assert request("DELETE", "/api/v1/auth/account", dict(lookup, password=password), token) == {
    "completed": True
}
assert request("POST", "/api/v1/auth/account-deletion/status", lookup) == {"completed": True}
for access in (token, second["access_token"]):
    request("GET", "/api/v1/auth/me", token=access, status=401)
request("POST", "/api/v1/auth/refresh", {"refresh_token": second["refresh_token"]}, status=401)
print("PASS: password guard, committed deletion receipt, all sessions revoked")
print("Runtime HTTP smoke checks passed.")
