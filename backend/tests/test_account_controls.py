import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

# Import the existing disposable-PostGIS fixtures, never the development database.
from test_integration import (
    befriend,
    delete_request,
    deletion_service,
    runner,
    upload,
)
from test_integration import (
    db as db,
)
from test_integration import (
    db_engine as db_engine,
)

from app.core.config import Settings, settings
from app.core.deps import get_session
from app.core.errors import AppError
from app.core.security import password_matches
from app.main import create_app
from app.repositories.game import Game
from app.repositories.users import Users
from app.services.auth import Auth
from app.services.friends import Friends
from app.services.recovery import Recovery


def test_fake_delivery_cannot_be_enabled_for_production_or_remote_origins():
    base = dict(
        jwt_secret="synthetic-only-secret-that-is-long-enough",
        recovery_delivery="local_fake",
        recovery_encryption_key=Fernet.generate_key().decode(),
    )
    for url in [
        "https://evil.example",
        "http://127.0.0.1.evil.example",
        "http://localhost/reset",
        "http://localhost#private",
        "http://user@localhost",
        "http://localhost:invalid",
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **base, recovery_base_url=url)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, **base, environment="production", allowed_hosts=["api.example.com"]
        )
    cfg = Settings(_env_file=None, **base)
    assert cfg.recovery_encryption_key not in repr(cfg)


def test_recovery_page_has_no_external_assets_or_token_query():
    client = TestClient(create_app())
    page = client.get("/password-reset")
    script = client.get("/password-reset.js")
    assert page.status_code == script.status_code == 200
    assert page.headers["referrer-policy"] == "no-referrer"
    assert page.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    assert "https://" not in page.text + script.text
    assert "window.location.hash" in script.text


def test_recovery_validation_redacts_credentials():
    response = TestClient(create_app()).post(
        "/api/v1/auth/password-recovery/complete",
        json={"token": "synthetic-private-token", "password": "private"},
    )
    assert response.status_code == 422
    assert "synthetic-private-token" not in response.text
    assert "private" not in response.text


def test_recovery_throttles_unknown_and_known_addresses_identically(monkeypatch):
    from app.services.recovery import ACKNOWLEDGEMENT, Recovery

    class Repo:
        calls = []

        def throttle(self, key):
            self.calls.append(key)
            return 21

    monkeypatch.setattr(settings(), "recovery_delivery", "local_fake")
    repo = Repo()
    response = Recovery(repo).request("synthetic@example.com", "192.0.2.200")
    assert response == {"message": ACKNOWLEDGEMENT}
    assert len(repo.calls) == 1


@pytest.fixture
def fake_delivery(monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setattr(settings(), "recovery_delivery", "local_fake")
    monkeypatch.setattr(settings(), "recovery_encryption_key", key.decode())
    monkeypatch.setattr(settings(), "recovery_base_url", "http://127.0.0.1:8000")
    return Fernet(key)


def issued_token(db, user, fake_delivery):
    row = Users(db).one("SELECT * FROM password_recoveries WHERE user_id=:uid", uid=user["id"])
    message = json.loads(fake_delivery.decrypt(row["delivery_ciphertext"].encode()))
    token = message["link"].split("#")[1]
    assert token not in str(row) and user["email"] not in str(row)
    assert message["to"] == user["email"]
    return token


@pytest.mark.integration
def test_block_removes_contest_and_both_directions_of_access_but_keeps_land(db):
    a, b = runner(db), runner(db)
    for user in (a, b):
        upload(db, user)
    befriend(db, a, b)
    repo = Users(db)
    service = Friends(repo)
    assert Game(db).territories(a["id"], "current")["features"][0]["properties"][
        "contested_geometry"
    ]
    service.change("block", a["id"], b["id"])
    service.change("block", a["id"], b["id"])  # Retry-safe.
    for user, other in [(a, b), (b, a)]:
        assert not repo.friend_ids(user["id"])
        assert not repo.friends(user["id"])
        assert not repo.search(other["username"], user["id"])
        features = Game(db).territories(user["id"], "current")["features"]
        assert {f["properties"]["owner_id"] for f in features} == {user["id"]}
        assert all(not f["properties"]["contested_geometry"] for f in features)
        assert Game(db).stats(user["id"])["area_m2"] == pytest.approx(10000, rel=0.01)
        for action in ("request", "accept"):
            with pytest.raises(AppError) as error:
                service.change(action, user["id"], other["id"])
            assert error.value.status == 404
    assert [u["id"] for u in repo.blocks(a["id"])] == [b["id"]]
    assert repo.blocks(b["id"]) == []
    outcome = upload(db, b, x=50)
    assert outcome["stolen_area_m2"] == outcome["blocked_area_m2"] == 0
    assert Game(db).stats(a["id"])["area_m2"] == pytest.approx(10000, rel=0.01)


@pytest.mark.integration
def test_mutual_blocks_unblock_only_own_direction_and_never_restore_friendship(db):
    a, b = runner(db), runner(db)
    service, repo = Friends(Users(db)), Users(db)
    service.change("request", a["id"], b["id"])
    for user, other in [(a, b), (b, a)]:
        service.change("block", user["id"], other["id"])
    service.change("unblock", b["id"], a["id"])
    assert repo.blocked(a["id"], b["id"])
    service.change("unblock", a["id"], b["id"])
    assert not repo.blocked(a["id"], b["id"])
    assert not repo.friendship(a["id"], b["id"])
    befriend(db, a, b)
    assert b["id"] in repo.friend_ids(a["id"])


@pytest.mark.integration
def test_recovery_generic_request_one_use_revokes_all_sessions_and_allows_new_login(
    db, fake_delivery
):
    user = runner(db)
    repo = Users(db)
    auth = Auth(repo)
    first, second = auth.issue(user), auth.issue(user)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    client = TestClient(app)
    known = client.post("/api/v1/auth/password-recovery", json={"email": user["email"]})
    unknown = client.post(
        "/api/v1/auth/password-recovery", json={"email": f"{uuid4().hex}@example.com"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    token = issued_token(db, user, fake_delivery)
    response = client.post(
        "/api/v1/auth/password-recovery/complete",
        json={"token": token, "password": "new-test-password-456"},
    )
    assert response.status_code == 200, response.text
    assert password_matches(repo.by_id(user["id"])["password_hash"], "new-test-password-456")
    assert repo.one("SELECT 1 FROM password_recoveries WHERE user_id=:uid", uid=user["id"]) is None
    assert (
        client.post(
            "/api/v1/auth/password-recovery/complete",
            json={"token": token, "password": "another-password"},
        ).status_code
        == 400
    )
    for session in (first, second):
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + session["access_token"]}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/refresh", json={"refresh_token": session["refresh_token"]}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": "test-password-123"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"username": user["username"], "password": "new-test-password-456"},
        ).status_code
        == 200
    )


@pytest.mark.integration
def test_recovery_cooldown_reissue_expiry_and_deletion_cleanup(db, fake_delivery):
    user, other = runner(db), runner(db)
    repo = Users(db)
    recovery = Recovery(repo)
    ip = str(uuid4())
    recovery.request(user["email"], ip)
    first = issued_token(db, user, fake_delivery)
    recovery.request(user["email"], ip)
    assert issued_token(db, user, fake_delivery) == first
    repo.execute(
        "UPDATE password_recoveries SET created_at=now()-interval '2 minutes' WHERE user_id=:uid",
        uid=user["id"],
    )
    recovery.request(user["email"], ip)
    second = issued_token(db, user, fake_delivery)
    assert second != first
    with pytest.raises(AppError):
        recovery.complete(first, "new-password-123", ip)
    repo.execute(
        "UPDATE password_recoveries SET expires_at=now()-interval '1 second' WHERE user_id=:uid",
        uid=user["id"],
    )
    with pytest.raises(AppError):
        recovery.complete(second, "new-password-123", ip)
    Friends(repo).change("block", user["id"], other["id"])
    deletion_service(db).delete(user, delete_request())
    assert not repo.blocks(other["id"])
    assert not repo.one(
        "SELECT 1 FROM user_blocks WHERE blocker_id=:uid OR blocked_id=:uid", uid=user["id"]
    )
    assert not repo.one("SELECT 1 FROM password_recoveries WHERE user_id=:uid", uid=user["id"])


@pytest.mark.integration
def test_simultaneous_reset_submissions_have_exactly_one_winner(db_engine, fake_delivery):
    with Session(db_engine) as session, session.begin():
        user = runner(session)
        Recovery(Users(session)).request(user["email"], str(uuid4()))
        token = issued_token(session, user, fake_delivery)
    barrier = Barrier(2)

    def submit(index):
        barrier.wait(timeout=5)
        try:
            with Session(db_engine) as session, session.begin():
                Recovery(Users(session)).complete(
                    token, f"replacement-password-{index}", str(uuid4())
                )
            return "ok", index
        except AppError as error:
            return error.code, index

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [1, 2]))
        assert sorted(result[0] for result in results) == ["invalid_recovery", "ok"]
        winner = next(index for outcome, index in results if outcome == "ok")
        with Session(db_engine) as session:
            assert password_matches(
                Users(session).by_id(user["id"])["password_hash"], f"replacement-password-{winner}"
            )
    finally:
        with Session(db_engine) as session, session.begin():
            Users(session).execute("DELETE FROM users WHERE id=:uid", uid=user["id"])


@pytest.mark.integration
def test_failed_reset_transaction_keeps_link_and_password_usable(db, fake_delivery, monkeypatch):
    from app.services import recovery as module

    user = runner(db)
    recovery = Recovery(Users(db))
    recovery.request(user["email"], str(uuid4()))
    token = issued_token(db, user, fake_delivery)

    def unavailable(_):
        raise RuntimeError("Synthetic hashing failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.HASHER, "hash", unavailable)
        with pytest.raises(RuntimeError, match="Synthetic hashing"), db.begin_nested():
            recovery.complete(token, "replacement-password-123", str(uuid4()))
    assert issued_token(db, user, fake_delivery) == token
    assert password_matches(Users(db).by_id(user["id"])["password_hash"], "test-password-123")
    assert recovery.complete(token, "replacement-password-123", str(uuid4())) == {"ok": True}


@pytest.mark.integration
def test_block_http_authentication_and_block_list_are_scoped_to_caller(db):
    a, b, c = runner(db), runner(db), runner(db)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    client = TestClient(app)
    credentials = {
        u["id"]: {"Authorization": "Bearer " + Auth(Users(db)).issue(u)["access_token"]}
        for u in (a, b, c)
    }
    assert client.post("/api/v1/friends/block", json={"user_id": str(b["id"])}).status_code == 401
    assert (
        client.post(
            "/api/v1/friends/block", headers=credentials[a["id"]], json={"user_id": str(b["id"])}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/friends/blocked", headers=credentials[a["id"]]).json()[0][
        "id"
    ] == str(b["id"])
    assert client.get("/api/v1/friends/blocked", headers=credentials[b["id"]]).json() == []
    assert client.get("/api/v1/friends/blocked", headers=credentials[c["id"]]).json() == []
    assert (
        client.post(
            "/api/v1/friends/unblock", headers=credentials[b["id"]], json={"user_id": str(a["id"])}
        ).status_code
        == 200
    )
    assert Users(db).blocked(a["id"], b["id"])
