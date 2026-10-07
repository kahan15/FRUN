"""Privilege checks use a new database and real logins, never SET ROLE as admin."""

import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_integration import delete_request, deletion_service, runner, upload

from app.core.config import settings
from app.db.privileges import RUNTIME_GUARD_SQL
from app.db.session import engine as application_engine
from app.repositories.game import Game
from app.repositories.users import Users
from app.services.auth import Auth
from app.services.friends import Friends

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def restricted_engine():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Disposable PostGIS is required")
    url = make_url(value)
    if url.database != "territory_test" or url.host not in {"test-db", "localhost", "127.0.0.1"}:
        pytest.fail("Role tests require the isolated local test database")
    name = "territory_roles_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    test_admin = create_engine(url.set(database=name), isolation_level="AUTOCOMMIT")
    migrator = create_engine(
        url.set(
            database=name, username="territory_migrator", password="synthetic-migration-secret"
        ),
        isolation_level="AUTOCOMMIT",
    )
    runtime_url = url.set(
        database=name, username="territory_runtime", password="synthetic-runtime-secret"
    )
    runtime = create_engine(runtime_url)
    roles_created = False
    cfg = settings()
    previous_url = cfg.database_url
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
        with test_admin.connect() as conn:
            conn.connection.driver_connection.execute((ROOT / "ops/provision-fresh.sql").read_text())
            roles_created = True
            with conn.connection.driver_connection.cursor() as cursor:
                for role, password in [
                    ("territory_migrator", "synthetic-migration-secret"),
                    ("territory_runtime", "synthetic-runtime-secret"),
                ]:
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                            sql.Identifier(role), sql.Literal(password)
                        )
                    )
        cfg.database_url = migrator.url.render_as_string(hide_password=False)
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        with migrator.connect() as conn:
            conn.connection.driver_connection.execute((ROOT / "ops/grant-runtime.sql").read_text())
        cfg.database_url = runtime_url.render_as_string(hide_password=False)
        application_engine.cache_clear()
        yield runtime
    finally:
        application_engine().dispose()
        application_engine.cache_clear()
        cfg.database_url = previous_url
        runtime.dispose()
        migrator.dispose()
        test_admin.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
            if roles_created:
                conn.exec_driver_sql("DROP ROLE territory_runtime; DROP ROLE territory_migrator")
        admin.dispose()


def test_real_runtime_login_can_run_game_account_and_deletion_flows(restricted_engine):
    with Session(restricted_engine) as db, db.begin():
        repo = Users(db)
        assert repo.execute("SELECT current_user").scalar_one() == "territory_runtime"
        assert repo.execute(RUNTIME_GUARD_SQL).scalar_one() is True
        a, b = runner(db), runner(db)
        Auth(repo).issue(a)
        upload(db, a)
        Friends(repo).change("request", a["id"], b["id"])
        Friends(repo).change("accept", b["id"], a["id"])
        assert len(Game(db).territories(b["id"], "current")["features"]) == 1
        Friends(repo).change("block", b["id"], a["id"])
        assert not Game(db).territories(b["id"], "current")["features"]
        assert repo.throttle("role-test-only-budget") == 1
        deletion_service(db).delete(a, delete_request())
        assert not repo.by_id(a["id"])


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE public.forbidden(id integer)",
        "CREATE TEMP TABLE forbidden(id integer)",
        "CREATE SCHEMA forbidden",
        "ALTER TABLE users ADD COLUMN forbidden text",
        "TRUNCATE users CASCADE",
        "UPDATE alembic_version SET version_num='forbidden'",
        "DELETE FROM spatial_ref_sys",
        "SET ROLE territory_migrator",
        "ALTER ROLE territory_runtime SUPERUSER",
        "CREATE ROLE forbidden",
        "GRANT territory_migrator TO territory_runtime",
    ],
)
def test_runtime_cannot_escalate_or_change_schema(restricted_engine, statement):
    with restricted_engine.connect() as conn:
        with pytest.raises(DBAPIError):
            conn.execute(text(statement))
        conn.rollback()
        assert conn.execute(text("SELECT current_user")).scalar_one() == "territory_runtime"


def test_production_connection_guard_accepts_runtime_and_rejects_admin(restricted_engine):
    cfg = settings()
    old_environment, old_url = cfg.environment, cfg.database_url
    try:
        cfg.environment = "production"
        application_engine().dispose()
        application_engine.cache_clear()
        with application_engine().connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
        application_engine().dispose()
        application_engine.cache_clear()
        cfg.database_url = os.environ["TEST_DATABASE_URL"]
        with pytest.raises(RuntimeError, match="runtime privileges are unsafe"):
            application_engine().connect()
    finally:
        application_engine().dispose()
        application_engine.cache_clear()
        cfg.environment, cfg.database_url = old_environment, old_url
