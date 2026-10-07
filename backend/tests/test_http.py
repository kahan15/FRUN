from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.core.security import HASHER, access_token, decode_access, password_matches
from app.main import create_app


def test_liveness_has_no_db_dependency():
    client = TestClient(create_app())
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


def test_error_vocabulary_and_no_password_echo():
    client = TestClient(create_app())
    response = client.post("/api/v1/auth/register", json={"password": "do-not-echo-me"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "do-not-echo-me" not in response.text
    response = client.get("/missing")
    assert response.status_code == 404
    assert "error" in response.json()


def test_auth_required_without_connecting_to_db():
    client = TestClient(create_app())
    assert client.get("/api/v1/territories").status_code == 401


def test_access_token_and_hashing():
    user_id, session_id = uuid4(), uuid4()
    token = access_token(user_id, session_id)
    assert decode_access(token)["sub"] == str(user_id)
    with pytest.raises(AppError):
        decode_access(token + "garbage")
    hashed = HASHER.hash("long-test-password")
    assert password_matches(hashed, "long-test-password")
    assert not password_matches(hashed, "wrong")


def test_body_size_limit(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings(), "max_body_bytes", 100)
    client = TestClient(create_app())
    response = client.post("/api/v1/auth/login", content="x" * 101)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_deletion_auth_and_validation_never_echo_password():
    client = TestClient(create_app())
    response = client.request(
        "DELETE", "/api/v1/auth/account", json={"request_id": str(uuid4()), "password": "secret"}
    )
    assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/account-deletion/status",
        json={"request_id": "bad", "password": "do-not-echo"},
    )
    assert response.status_code == 422
    assert "do-not-echo" not in response.text


def test_request_logging_uses_templates_and_omits_private_url_data(capsys):
    client = TestClient(create_app())
    token = "abc123-private-device-token"
    query = "private-search-term"
    client.delete("/api/v1/devices/" + token)
    client.get("/api/v1/friends/search?q=" + query)
    client.get("/missing/" + token)
    logged = capsys.readouterr().out
    assert "http_request" in logged
    assert token not in logged and query not in logged
    assert "/devices/{token}" in logged


@pytest.mark.parametrize("failure_kind, expected_status", [("integrity", 409), ("unexpected", 500)])
def test_error_logging_omits_private_url_and_exception_data(capsys, failure_kind, expected_status):
    from sqlalchemy.exc import IntegrityError

    app = create_app()
    private_value = "synthetic-private-device-token"
    private_detail = "synthetic-private-database-detail"

    @app.get("/failure/{token}")
    def failure(token: str):
        if failure_kind == "integrity":
            raise IntegrityError("statement", {"token": token}, Exception(private_detail))
        raise RuntimeError(private_detail)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/failure/" + private_value + "?q=synthetic-private-search")
    assert response.status_code == expected_status
    logged = capsys.readouterr().out
    assert "/failure/{token}" in logged
    for private in (private_value, private_detail, "synthetic-private-search"):
        assert private not in logged
        assert private not in response.text
