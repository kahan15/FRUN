import asyncio
import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.middleware import RequestMiddleware
from app.core.security import digest
from app.main import create_app
from app.schemas.contracts import Login
from app.services.auth import Auth


def test_production_refuses_weak_secret_wildcard_and_unknown_environment():
    strong = "oG8TQydFRwA9U_LzeSbYNvj5kiHD40nMo76EcVPl2Zx3r1sWtCqKaBhX"
    for values in [
        {"environment": "prod", "jwt_secret": strong},
        {"environment": "production", "jwt_secret": strong},
        {"environment": "production", "jwt_secret": "x" * 64, "allowed_hosts": ["api.example.com"]},
        {
            "environment": "production",
            "jwt_secret": strong,
            "allowed_hosts": ["https://api.example.com"],
        },
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **values)
    cfg = Settings(
        _env_file=None,
        environment="production",
        jwt_secret=strong,
        allowed_hosts=["api.example.com", "localhost"],
    )
    assert cfg.environment == "production"


def test_production_host_filter_and_private_docs(monkeypatch):
    monkeypatch.setattr(settings(), "environment", "production")
    monkeypatch.setattr(settings(), "allowed_hosts", ["api.example.com"])
    client = TestClient(create_app(), base_url="https://api.example.com")
    assert client.get("/health/live").status_code == 200
    for path in ["/docs", "/redoc", "/openapi.json"]:
        assert client.get(path).status_code == 404
    rejected = client.get("/health/live", headers={"Host": "unapproved.example"})
    assert rejected.status_code == 400
    assert rejected.headers["cache-control"] == "no-store"


def test_settings_errors_and_repr_do_not_print_credentials():
    secret = "synthetic-private-signing-secret-123456789"
    database = "postgresql+psycopg://runner:synthetic-private-db-password@localhost/territory"
    cfg = Settings(_env_file=None, jwt_secret=secret, database_url=database)
    assert secret not in repr(cfg) and "synthetic-private-db-password" not in repr(cfg)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, jwt_secret=secret, database_url=database, environment="production")
    assert secret not in str(error.value) and "synthetic-private-db-password" not in str(
        error.value
    )


@pytest.mark.parametrize("path", ["/health/live", "/api/v1/territories", "/missing"])
def test_responses_are_not_cacheable(path):
    response = TestClient(create_app()).get(path)
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-request-id"]


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("private sql", {}, Exception("private password")),
        PoolTimeoutError("private detail"),
    ],
)
def test_database_failure_is_retryable_and_private(error, capsys):
    app = create_app()

    @app.get("/busy")
    def busy():
        raise error

    response = TestClient(app).get("/busy")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "private" not in response.text + capsys.readouterr().out


def test_unexpected_exception_never_escapes_to_server_traceback(capsys):
    app = create_app()

    @app.get("/crash")
    def crash():
        raise RuntimeError("synthetic-private-gps-and-password")

    # TestClient normally rethrows an unhandled exception even after a 500 response.
    # A normal custom Starlette 500 handler alone would fail this regression.
    response = TestClient(app, raise_server_exceptions=True).get("/crash")
    assert response.status_code == 500
    assert response.headers["x-request-id"]
    assert "synthetic-private" not in response.text + capsys.readouterr().out


def test_login_username_spray_shares_ip_budget(monkeypatch):
    class Repository:
        attempts = Counter()
        lookups = 0

        def throttle(self, key):
            self.attempts[key] += 1
            return self.attempts[key]

        def by_login(self, value, *, lock=False):
            self.lookups += 1
            return None

    repo = Repository()
    monkeypatch.setattr(settings(), "login_ip_attempts_per_window", 3)
    monkeypatch.setattr("app.services.auth.password_matches", lambda *_: False)
    for index in range(3):
        with pytest.raises(AppError) as error:
            Auth(repo).login(Login(username=f"different{index}", password="wrong"), "192.0.2.1")
        assert error.value.code == "invalid_credentials"
    with pytest.raises(AppError) as error:
        Auth(repo).login(Login(username="another", password="wrong"), "192.0.2.1")
    assert error.value.status == 429
    assert repo.lookups == 3  # No expensive password work after the shared budget is exhausted.
    assert repo.attempts[digest("login-ip:192.0.2.1")] == 4


def exercise_body(headers, chunks, *, delay=0, deadline=1):
    async def exercise():
        events = []
        called = False
        iterator = iter(chunks)

        async def receive():
            if delay:
                await asyncio.sleep(delay)
            return next(iterator)

        async def send(message):
            events.append(message)

        async def downstream(scope, receive, send):
            nonlocal called
            called = True

        scope = {"type": "http", "method": "POST", "headers": headers, "path": "/upload"}
        await RequestMiddleware(downstream, 100, deadline)(scope, receive, send)
        return called, events

    return asyncio.run(exercise())


def test_oversize_header_rejected_without_reading_body():
    called, events = exercise_body([(b"content-length", b"101")], [])
    assert not called and events[0]["status"] == 413
    assert dict(events[0]["headers"])[b"cache-control"] == b"no-store"


def test_chunked_limit_cannot_be_bypassed():
    called, events = exercise_body(
        [],
        [
            {"type": "http.request", "body": b"x" * 60, "more_body": True},
            {"type": "http.request", "body": b"x" * 41, "more_body": False},
        ],
    )
    assert not called and events[0]["status"] == 413


@pytest.mark.parametrize("value", [b"-1", b"NaN", b"9" * 200])
def test_malformed_lengths_are_rejected(value):
    called, events = exercise_body([(b"content-length", value)], [])
    assert not called and events[0]["status"] == 400


def test_upload_deadline_is_total_not_per_chunk():
    called, events = exercise_body(
        [],
        [{"type": "http.request", "body": b"x", "more_body": True} for _ in range(100)],
        delay=0.01,
        deadline=0.03,
    )
    assert not called and events[0]["status"] == 408
    assert json.loads(events[1]["body"])["error"]["code"] == "request_timeout"


def test_disconnect_never_dispatches_partial_request():
    called, events = exercise_body([], [{"type": "http.disconnect"}])
    assert not called and events == []
