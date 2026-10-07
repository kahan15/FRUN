"""Run only against TEST_DATABASE_URL ending in /territory_test. Never a real user DB."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from shapely.geometry import LineString, Polygon, shape
from shapely.ops import transform
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from synthetic_routes import freeform_loop
from test_geometry import FWD, coordinates

from app.core.config import settings
from app.core.security import HASHER
from app.db.session import get_session
from app.main import create_app
from app.repositories.game import Game
from app.repositories.users import Users
from app.schemas.contracts import Fix, Register, RunUpload
from app.services.auth import Auth
from app.services.claims import Claims
from app.services.friends import Friends

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured; real PostGIS required")
    from sqlalchemy.engine import make_url

    if make_url(url).database != "territory_test":
        pytest.fail("Integration tests require the disposable territory_test database")
    cfg = settings()
    previous = cfg.database_url
    cfg.database_url = url
    from app.db.session import engine as application_engine

    application_engine.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    cfg.database_url = previous
    application_engine().dispose()
    application_engine.cache_clear()


@pytest.fixture
def db(db_engine):
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()


def runner(db, prefix="runner"):
    suffix = uuid4().hex[:10]
    return Users(db).insert(
        Register(
            email=f"{suffix}@example.com",
            username=prefix + suffix,
            password="test-password-123",
            display_name=prefix,
            sex="X",
        ),
        HASHER.hash("test-password-123"),
    )


def track(db, x=0, size=100, client_id=None):
    vertices = [(x, 0), (x + size, 0), (x + size, size), (x, size), (x, 0)]
    samples = []
    for a, b in zip(vertices, vertices[1:]):
        samples.extend(
            [(a[0] + (b[0] - a[0]) * i / 20, a[1] + (b[1] - a[1]) * i / 20) for i in range(20)]
        )
    samples.append(vertices[-1])
    start = Game(db).now() - timedelta(hours=1)
    fixes = [
        Fix(longitude=lon, latitude=lat, accuracy=5, timestamp=start + timedelta(seconds=i * 3))
        for i, (lon, lat) in enumerate(coordinates(samples))
    ]
    return RunUpload(
        client_run_id=client_id or uuid4(),
        started_at=start,
        ended_at=fixes[-1].timestamp,
        points=fixes,
    )


def upload(db, user, **kwargs):
    return Claims(Game(db), Users(db)).upload(user, track(db, **kwargs))


def befriend(db, a, b):
    service = Friends(Users(db))
    service.change("request", a["id"], b["id"])
    service.change("accept", b["id"], a["id"])


def unprotect(db):
    db.execute(text("UPDATE territories SET claimed_at=now()-interval '7 hours'"))


def assert_no_overlap(db):
    assert (
        db.execute(
            text("""SELECT count(*) FROM territories a JOIN territories b ON a.id<b.id
        AND a.geom && b.geom AND ST_Area(ST_Intersection(a.geom,b.geom)::geography)>0.0001
        WHERE a.active AND b.active AND a.owner_id=b.owner_id""")
        ).scalar_one()
        == 0
    )
    db.execute(text("SET CONSTRAINTS territory_overlap_guard IMMEDIATE"))


def test_stranger_independence_and_map_scope(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    assert Game(db).territories(b["id"], "current")["features"] == []
    result = upload(db, b, x=50)
    assert result["blocked_area_m2"] == 0
    assert result["new_area_m2"] == pytest.approx(10000, rel=0.01)
    assert result["stolen_area_m2"] == 0
    assert_no_overlap(db)


def test_friend_cooldown_then_partial_carve(db):
    a, b = runner(db), runner(db)
    befriend(db, a, b)
    upload(db, a)
    protected = upload(db, b, x=50)
    assert protected["stolen_area_m2"] == 0
    unprotect(db)
    result = upload(db, b, x=50)
    assert result["stolen_area_m2"] == pytest.approx(5000, rel=0.01)
    assert Game(db).stats(a["id"])["area_m2"] == pytest.approx(5000, rel=0.01)
    assert Game(db).unread(a["id"]) == 1
    assert_no_overlap(db)


def test_refresh_idempotency_and_cooldown_not_reset(db):
    a = runner(db)
    run = track(db)
    result = Claims(Game(db), Users(db)).upload(a, run)
    duplicate = Claims(Game(db), Users(db)).upload(a, run)
    assert duplicate["was_duplicate"] is True
    assert duplicate["id"] == str(result["id"])
    db.execute(
        text(
            "UPDATE territories SET claimed_at=now()-interval '7 hours',expires_at=now()+interval '1 day'"
        )
    )
    before = db.execute(
        text("SELECT claimed_at FROM territories WHERE active LIMIT 1")
    ).scalar_one()
    refreshed = upload(db, a)
    assert refreshed["new_area_m2"] == pytest.approx(0, abs=0.01)
    assert refreshed["refreshed_area_m2"] == pytest.approx(10000, rel=0.01)
    assert (
        db.execute(text("SELECT claimed_at FROM territories WHERE active LIMIT 1")).scalar_one()
        == before
    )
    assert_no_overlap(db)


def test_adjacent_and_expired_claims(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    adjacent = upload(db, b, x=100)
    assert adjacent["new_area_m2"] == pytest.approx(10000, rel=0.01)
    db.execute(
        text("UPDATE territories SET expires_at=now()-interval '1 minute' WHERE owner_id=:id"),
        {"id": a["id"]},
    )
    reclaimed = upload(db, b)
    assert reclaimed["new_area_m2"] == pytest.approx(10000, rel=0.01)
    assert_no_overlap(db)


def test_upload_http_and_private_profile(db):
    a = runner(db)
    auth = Auth(Users(db)).issue(a)
    app = create_app()

    def override():
        yield db

    app.dependency_overrides[get_session] = override
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + auth["access_token"]}
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert "sex" not in me.json() and "email" not in me.json()
    response = client.post("/api/v1/runs", headers=headers, json=track(db).model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert response.json()["new_area_m2"] > 9000
    map_response = client.get("/api/v1/territories", headers=headers)
    assert map_response.status_code == 200, map_response.text
    feature = map_response.json()["features"][0]
    assert feature["geometry"]["type"] == "MultiPolygon"
    assert feature["properties"]["owner_id"] == str(a["id"])
    assert feature["properties"]["contested_geometry"] is None
    assert_no_overlap(db)


def test_refresh_rotation_and_logout(db):
    auth = Auth(Users(db))
    issued = auth.issue(runner(db))
    replacement = auth.refresh(issued["refresh_token"])
    from app.core.errors import AppError

    with pytest.raises(AppError):
        auth.refresh(issued["refresh_token"])
    assert replacement["refresh_token"] != issued["refresh_token"]


def test_freeform_capture_survives_http_postgis_and_geojson(db):
    user = runner(db)
    auth = Auth(Users(db)).issue(user)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + auth["access_token"]}
    coords = coordinates(freeform_loop())
    start = Game(db).now() - timedelta(hours=1)
    points = [
        Fix(longitude=x, latitude=y, accuracy=5, timestamp=start + timedelta(seconds=i * 3))
        for i, (x, y) in enumerate(coords)
    ]
    run = RunUpload(
        client_run_id=uuid4(), started_at=start, ended_at=points[-1].timestamp, points=points
    )
    response = client.post("/api/v1/runs", headers=headers, json=run.model_dump(mode="json"))
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    map_response = client.get("/api/v1/territories", headers=headers)
    geometry = shape(map_response.json()["features"][0]["geometry"])
    captured = transform(FWD.transform, geometry)
    expected = transform(FWD.transform, Polygon(coords))
    assert len(captured.geoms) == 1 and len(captured.geoms[0].exterior.coords) > 8
    assert (
        captured.boundary.hausdorff_distance(transform(FWD.transform, LineString(coords))) <= 4.01
    )
    assert captured.area < expected.envelope.area * 0.8
    assert expected.convex_hull.difference(captured).area > expected.area * 0.05


def test_runtime_database_deadlines_and_pool_recovery(db_engine):
    from sqlalchemy.exc import OperationalError

    from app.db.session import engine

    with engine().connect() as connection:
        assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "15s"
        assert connection.execute(text("SHOW lock_timeout")).scalar_one() == "5s"
        assert (
            connection.execute(text("SHOW idle_in_transaction_session_timeout")).scalar_one()
            == "30s"
        )
    with pytest.raises(OperationalError):
        with engine().begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout='25ms'"))
            connection.execute(text("SELECT pg_sleep(0.1)"))
    with engine().connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_complexity_rejection_is_saved_without_awarding_land(db, monkeypatch):
    monkeypatch.setattr(settings(), "max_loop_vertices", 3)
    user = runner(db)
    result = upload(db, user)
    assert result["status"] == "rejected"
    assert result["reasons"] == ["route_too_complex"]
    assert result["new_area_m2"] == 0
    assert Game(db).territories(user["id"], "current")["features"] == []
    assert len(Game(db).history(user["id"], 50, 0)) == 1


def test_registration_login_logout_http(db, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    client = TestClient(app)
    name = "account" + uuid4().hex[:10]
    registration = {
        "email": name + "@example.com",
        "username": name,
        "password": "test-password-123",
        "display_name": "Test",
        "sex": "X",
    }
    response = client.post("/api/v1/auth/register", json=registration)
    assert response.status_code == 201, response.text
    login = client.post(
        "/api/v1/auth/login", json={"username": name, "password": registration["password"]}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_notification_failure_rolls_back_carving(db):
    a, b = runner(db), runner(db)
    befriend(db, a, b)
    upload(db, a)
    unprotect(db)
    before = Game(db).stats(a["id"])["area_m2"]
    with pytest.raises(RuntimeError), db.begin_nested():
        game = Game(db)

        def failed_notification(*args):
            raise RuntimeError("simulated outbox failure")

        game.notify = failed_notification
        Claims(game, Users(db)).upload(b, track(db, x=50))
    assert Game(db).stats(a["id"])["area_m2"] == before
    assert Game(db).unread(a["id"]) == 0
    assert_no_overlap(db)


def test_concurrent_new_claims_and_duplicate_uploads(db_engine):
    # This test needs independently committed transactions to exercise the absent-row race.
    ids = []
    try:
        with Session(db_engine) as db, db.begin():
            a, b = runner(db), runner(db)
            ids = [a["id"], b["id"]]
            run_a, run_b = track(db, x=5000), track(db, x=5000)

        def send(user, run):
            with Session(db_engine) as db, db.begin():
                return Claims(Game(db), Users(db)).upload(user, run)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(send, a, run_a)
            second = pool.submit(send, b, run_b)
            results = [first.result(timeout=20), second.result(timeout=20)]
        assert sum(r["new_area_m2"] for r in results) == pytest.approx(20000, rel=0.01)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(a, run_a), range(2)))
        assert all(r["was_duplicate"] for r in results)
        with Session(db_engine) as db:
            assert_no_overlap(db)
    finally:
        with db_engine.begin() as connection:
            for uid in ids:
                connection.execute(text("DELETE FROM territories WHERE owner_id=:id"), {"id": uid})
                connection.execute(text("DELETE FROM runs WHERE user_id=:id"), {"id": uid})
                connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})


def contest_area(db):
    return db.execute(
        text("SELECT coalesce(sum(ST_Area(geom::geography)),0) FROM contests")
    ).scalar_one()


def qualify_after_acceptance(db, user, **kwargs):
    # Shift acceptance before this newly recorded fixture, without using future timestamps.
    db.execute(text("UPDATE contests SET accepted_at=now()-interval '2 hours'"))
    return upload(db, user, **kwargs)


def test_acceptance_preserves_contest_then_first_capture_wins_only_slice(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    upload(db, b)
    befriend(db, a, b)
    assert contest_area(db) == pytest.approx(10000, rel=0.01)
    features = Game(db).territories(a["id"], "current")["features"]
    assert len(features) == 2
    assert all(f["properties"]["contested_geometry"] for f in features)
    result = qualify_after_acceptance(db, a, x=50)
    assert result["stolen_area_m2"] == pytest.approx(5000, rel=0.01)
    assert result["refreshed_area_m2"] == pytest.approx(5000, rel=0.01)
    assert result["new_area_m2"] == pytest.approx(5000, rel=0.01)
    assert contest_area(db) == pytest.approx(5000, rel=0.01)
    # Winner's new protection stops an immediate recapture of that same slice.
    second = upload(db, b, x=50)
    assert second["stolen_area_m2"] == pytest.approx(0, abs=0.01)
    assert second["blocked_area_m2"] == pytest.approx(10000, rel=0.01)
    assert_no_overlap(db)


def test_offline_run_before_acceptance_cannot_settle_even_without_protection(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    upload(db, b)
    older = track(db)
    befriend(db, a, b)
    unprotect(db)
    result = Claims(Game(db), Users(db)).upload(a, older)
    assert result["stolen_area_m2"] == 0
    assert contest_area(db) == pytest.approx(10000, rel=0.01)


def test_remove_reaccept_and_third_party_privacy(db):
    a, b, c = runner(db), runner(db), runner(db)
    upload(db, a)
    upload(db, b)
    befriend(db, a, b)
    befriend(db, a, c)
    features = Game(db).territories(c["id"], "current")["features"]
    assert {f["properties"]["owner_id"] for f in features} == {a["id"]}
    assert all(f["properties"]["contested_geometry"] is None for f in features)
    assert Game(db).contests(c["id"]) == []
    Friends(Users(db)).change("remove", a["id"], b["id"])
    assert contest_area(db) == 0
    qualify_after_acceptance(db, a)
    assert Game(db).stats(b["id"])["area_m2"] == pytest.approx(10000, rel=0.01)
    befriend(db, a, b)
    assert contest_area(db) == pytest.approx(10000, rel=0.01)
    assert_no_overlap(db)


def test_expiry_removes_contest_without_waiting_for_worker(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    upload(db, b)
    befriend(db, a, b)
    db.execute(
        text("UPDATE territories SET expires_at=now()-interval '1 minute' WHERE owner_id=:id"),
        {"id": b["id"]},
    )
    features = Game(db).territories(a["id"], "current")["features"]
    assert all(f["properties"]["contested_geometry"] is None for f in features)
    qualify_after_acceptance(db, a)
    assert contest_area(db) == 0


def test_renewal_extends_only_captured_own_portion(db):
    a = runner(db)
    upload(db, a)
    db.execute(text("UPDATE territories SET expires_at=now()+interval '1 day'"))
    before = Game(db).stats(a["id"])["expiring_area_m2"]
    result = upload(db, a, x=50)
    assert result["refreshed_area_m2"] == pytest.approx(5000, rel=0.01)
    assert Game(db).stats(a["id"])["expiring_area_m2"] == pytest.approx(before / 2, rel=0.01)
    assert_no_overlap(db)


def test_rejected_loop_cannot_settle_contest(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    upload(db, b)
    befriend(db, a, b)
    db.execute(text("UPDATE contests SET accepted_at=now()-interval '2 hours'"))
    bad = track(db)
    bad.points[2].timestamp = bad.points[0].timestamp
    result = Claims(Game(db), Users(db)).upload(a, bad)
    assert result["status"] == "rejected"
    assert result["stolen_area_m2"] == 0
    assert contest_area(db) == pytest.approx(10000, rel=0.01)


def test_concurrent_contest_has_one_winner(db_engine):
    ids = []
    try:
        with Session(db_engine) as db, db.begin():
            a, b = runner(db), runner(db)
            ids = [a["id"], b["id"]]
            upload(db, a, x=9000)
            upload(db, b, x=9000)
            befriend(db, a, b)
            db.execute(text("UPDATE contests SET accepted_at=now()-interval '2 hours'"))
            run_a, run_b = track(db, x=9000), track(db, x=9000)

        def send(user, run):
            with Session(db_engine) as db, db.begin():
                return Claims(Game(db), Users(db)).upload(user, run)

        with ThreadPoolExecutor(max_workers=2) as pool:
            fa, fb = pool.submit(send, a, run_a), pool.submit(send, b, run_b)
            results = [fa.result(timeout=20), fb.result(timeout=20)]
        assert sorted(round(r["stolen_area_m2"]) for r in results) == pytest.approx(
            [0, 10000], abs=20
        )
        with Session(db_engine) as db:
            assert contest_area(db) == 0
            assert_no_overlap(db)
    finally:
        with db_engine.begin() as db:
            for uid in ids:
                for table, condition in [
                    ("notifications", "user_id=:id"),
                    ("contests", "owner_a=:id OR owner_b=:id"),
                    ("friendships", "requester_id=:id OR addressee_id=:id"),
                    ("territories", "owner_id=:id"),
                    ("runs", "user_id=:id"),
                ]:
                    db.execute(text(f"DELETE FROM {table} WHERE {condition}"), {"id": uid})
            for uid in ids:
                db.execute(text("DELETE FROM users WHERE id=:id"), {"id": uid})


def test_pending_request_never_grants_visibility_or_capture(db):
    a, b = runner(db), runner(db)
    upload(db, a)
    Friends(Users(db)).change("request", a["id"], b["id"])
    assert Game(db).territories(b["id"], "current")["features"] == []
    result = upload(db, b)
    assert result["new_area_m2"] == pytest.approx(10000, rel=0.01)
    assert result["blocked_area_m2"] == result["stolen_area_m2"] == 0
    assert Game(db).unread(a["id"]) == 0
    assert_no_overlap(db)


def test_guard_rejects_real_same_owner_or_uncontested_friend_overlap(db):
    from sqlalchemy.exc import IntegrityError

    a, b = runner(db), runner(db)
    upload(db, a)
    befriend(db, a, b)
    # The precision tolerance must not weaken enforcement for meaningful overlapping area.
    for owner in (a["id"], b["id"]):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(
                text("""INSERT INTO territories(id,owner_id,run_id,geom,area_m2,claimed_at,expires_at)
                SELECT :id,:owner,run_id,geom,area_m2,claimed_at,expires_at
                FROM territories WHERE owner_id=:a AND active LIMIT 1"""),
                {"id": uuid4(), "owner": owner, "a": a["id"]},
            )
            db.execute(text("SET CONSTRAINTS territory_overlap_guard IMMEDIATE"))


def test_shared_friend_can_settle_contest_but_nonfriend_land_survives(db):
    a, b, c, hidden = runner(db), runner(db), runner(db), runner(db)
    for user in (a, b, hidden):
        upload(db, user)
    befriend(db, a, b)
    befriend(db, c, a)
    befriend(db, c, b)
    outcome = qualify_after_acceptance(db, c)
    assert outcome["stolen_area_m2"] == pytest.approx(10000, rel=0.01)
    assert sum(x["area_m2"] for x in outcome["steals"]) == pytest.approx(20000, rel=0.01)
    assert Game(db).stats(hidden["id"])["area_m2"] == pytest.approx(10000, rel=0.01)
    assert Game(db).unread(hidden["id"]) == 0
    assert contest_area(db) == pytest.approx(0, abs=0.0001)
    assert_no_overlap(db)


# Account deletion exercises the real FK graph, PostGIS guard and revoked sessions.
def deletion_service(db):
    from app.repositories.privacy import Privacy
    from app.services.privacy import AccountPrivacy

    return AccountPrivacy(Privacy(db))


def delete_request(request_id=None, password="test-password-123"):
    from app.schemas.contracts import AccountDeletionRequest

    return AccountDeletionRequest(request_id=request_id or uuid4(), password=password)


def test_delete_requires_password_and_revokes_every_session_with_recoverable_receipt(db):
    a = runner(db)
    auth = Auth(Users(db))
    first, second = auth.issue(a), auth.issue(a)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + first["access_token"]}
    request = delete_request()
    payload = request.model_dump(mode="json")
    lookup = {"request_id": str(request.request_id)}
    assert client.post("/api/v1/auth/account-deletion/status", json=lookup).json() == {
        "completed": False
    }
    bad = client.request(
        "DELETE", "/api/v1/auth/account", headers=headers, json=dict(payload, password="wrong")
    )
    assert bad.status_code == 403
    assert Users(db).by_id(a["id"])
    response = client.request("DELETE", "/api/v1/auth/account", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json() == {"completed": True}
    for issued in [first, second]:
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + issued["access_token"]}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/refresh", json={"refresh_token": issued["refresh_token"]}
            ).status_code
            == 401
        )
    # Simulates losing the DELETE response: status needs neither account nor session.
    status = client.post("/api/v1/auth/account-deletion/status", json=lookup)
    assert status.json() == {"completed": True}
    assert a["username"] not in status.text and str(a["id"]) not in status.text
    assert client.post(
        "/api/v1/auth/account-deletion/status", json={"request_id": str(uuid4())}
    ).json() == {"completed": False}


def test_delete_removes_personal_data_but_preserves_others_earned_territory(db):
    from app.schemas.contracts import DeviceRegistration

    a, b, c = runner(db), runner(db), runner(db)
    befriend(db, a, b)
    upload(db, a)
    unprotect(db)
    stolen = upload(db, b, x=50)
    assert stolen["steals"][0]["victim_username"] == a["username"]
    unprotect(db)
    upload(db, a, x=100)  # A's username appears in B's notification.
    upload(db, c, x=100)
    befriend(db, a, c)  # Also exercise contested land cleanup.
    assert contest_area(db) > 0
    game = Game(db)
    for user in [a, b]:
        game.register_device(
            user["id"],
            DeviceRegistration(apns_token=uuid4().hex * 2, platform="ios", app_version="test"),
        )
    db.execute(
        text(
            "INSERT INTO push_deliveries(notification_id,device_id) SELECT n.id,d.id FROM notifications n JOIN devices d ON d.user_id=n.user_id"
        )
    )
    before = {u["id"]: game.stats(u["id"])["area_m2"] for u in [b, c]}
    request = delete_request()
    deletion_service(db).delete(a, request)
    assert Users(db).by_id(a["id"]) is None
    for table, predicate in [
        ("runs", "user_id=:id"),
        ("territories", "owner_id=:id OR lost_to_id=:id OR stolen_from_id=:id"),
        ("friendships", "requester_id=:id OR addressee_id=:id"),
        ("contests", "owner_a=:id OR owner_b=:id"),
        ("notifications", "user_id=:id"),
        ("devices", "user_id=:id"),
        ("sessions", "user_id=:id"),
    ]:
        assert (
            db.execute(
                text(f"SELECT count(*) FROM {table} WHERE {predicate}"), {"id": a["id"]}
            ).scalar_one()
            == 0
        )
    for u in [b, c]:
        assert game.stats(u["id"])["area_m2"] == before[u["id"]]
    retained = str(db.execute(text("SELECT result FROM runs")).all())
    assert a["username"] not in retained
    assert "Deleted runner" in retained
    assert a["username"] not in str(
        db.execute(text("SELECT body,payload FROM notifications")).all()
    )
    assert_no_overlap(db)


def test_delete_failure_rolls_back_data_and_receipt(db, monkeypatch):
    a = runner(db)
    upload(db, a)
    request = delete_request()
    service = deletion_service(db)
    execute = service.repo.execute

    def fail_receipt(sql, **params):
        if "INSERT INTO account_deletions" in sql:
            raise RuntimeError("simulated disk failure")
        return execute(sql, **params)

    monkeypatch.setattr(service.repo, "execute", fail_receipt)
    with pytest.raises(RuntimeError), db.begin_nested():
        service.delete(a, request)
    assert Users(db).by_id(a["id"])
    assert Game(db).stats(a["id"])["run_count"] == 1
    assert deletion_service(db).status(request.request_id) == {"completed": False}
    assert_no_overlap(db)


def test_deleted_account_cannot_use_inflight_upload_or_friend_request(db):
    from app.core.errors import AppError

    a, b = runner(db), runner(db)
    run = track(db)
    deletion_service(db).delete(a, delete_request())
    with pytest.raises(AppError) as failure:
        Claims(Game(db), Users(db)).upload(a, run)
    assert failure.value.status == 401
    with pytest.raises(AppError) as failure:
        Friends(Users(db)).change("request", a["id"], b["id"])
    assert failure.value.status == 401


def test_deletion_receipt_cannot_delete_another_account(db):
    from app.core.errors import AppError

    a, b = runner(db), runner(db)
    request = delete_request()
    service = deletion_service(db)
    service.delete(a, request)
    with pytest.raises(AppError) as failure:
        service.delete(b, request)
    assert failure.value.status == 409
    assert Users(db).by_id(b["id"])


def test_deletion_password_attempts_are_limited(db):
    from app.core.errors import AppError

    a = runner(db)
    service = deletion_service(db)
    for attempt in range(6):
        with pytest.raises(AppError) as failure:
            service.delete(a, delete_request(password="incorrect"))
        assert failure.value.status == (403 if attempt < 5 else 429)
    assert Users(db).by_id(a["id"])
