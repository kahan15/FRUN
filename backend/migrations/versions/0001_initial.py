"""Local-first game schema and spatial invariants."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    schema = """
    CREATE TABLE users (
      id uuid PRIMARY KEY, email text UNIQUE NOT NULL, username text UNIQUE NOT NULL,
      display_name text NOT NULL, password_hash text NOT NULL,
      sex char(1) NOT NULL CHECK (sex IN ('M','F','X')),
      is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE sessions (
      id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
      token_hash text UNIQUE NOT NULL, expires_at timestamptz NOT NULL,
      revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX sessions_user ON sessions(user_id);
    CREATE TABLE friendships (
      requester_id uuid NOT NULL REFERENCES users(id), addressee_id uuid NOT NULL REFERENCES users(id),
      status text NOT NULL CHECK (status IN ('pending','accepted','blocked')),
      created_at timestamptz NOT NULL DEFAULT now(), CHECK (requester_id <> addressee_id)
    );
    CREATE UNIQUE INDEX friendship_pair ON friendships
      (least(requester_id, addressee_id), greatest(requester_id, addressee_id));
    CREATE INDEX friendship_addressee ON friendships(addressee_id, status);
    CREATE INDEX friendship_requester ON friendships(requester_id, status);
    CREATE TABLE runs (
      id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
      client_run_id uuid UNIQUE NOT NULL, started_at timestamptz NOT NULL,
      ended_at timestamptz NOT NULL, duration_s double precision NOT NULL DEFAULT 0,
      distance_m double precision NOT NULL DEFAULT 0, avg_speed_ms double precision NOT NULL DEFAULT 0,
      point_count integer NOT NULL DEFAULT 0, dropped_point_count integer NOT NULL DEFAULT 0,
      step_count integer, track geometry(MULTILINESTRING,4326),
      status text NOT NULL, review_notes text, cheat_report jsonb NOT NULL,
      raw_upload jsonb NOT NULL, result jsonb NOT NULL,
      fragment_count integer NOT NULL DEFAULT 0, claimed_area_m2 double precision NOT NULL DEFAULT 0,
      stolen_area_m2 double precision NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT clock_timestamp()
    );
    CREATE INDEX runs_user_created ON runs(user_id, created_at DESC);
    CREATE TABLE territories (
      id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id),
      run_id uuid NOT NULL REFERENCES runs(id), geom geometry(MULTIPOLYGON,4326) NOT NULL,
      area_m2 double precision NOT NULL CHECK(area_m2 >= 0), claimed_at timestamptz NOT NULL,
      expires_at timestamptz NOT NULL, active boolean NOT NULL DEFAULT true,
      stolen_from_id uuid REFERENCES users(id), lost_at timestamptz, lost_to_id uuid REFERENCES users(id),
      CHECK (ST_IsValid(geom)), CHECK (NOT ST_IsEmpty(geom) OR NOT active)
    );
    CREATE INDEX territories_active_geom ON territories USING gist(geom) WHERE active;
    CREATE INDEX territories_owner ON territories(owner_id, active);
    CREATE INDEX territories_expiry ON territories(expires_at, active);
    CREATE TABLE notifications (
      id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id),
      kind text NOT NULL, title text NOT NULL, body text NOT NULL,
      payload jsonb NOT NULL, read_at timestamptz, delivered_at timestamptz,
      attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(),
      last_error text, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX notifications_outbox ON notifications(next_attempt_at) WHERE delivered_at IS NULL;
    CREATE INDEX notifications_user ON notifications(user_id, created_at DESC);
    CREATE TABLE devices (
      id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id), apns_token text UNIQUE NOT NULL,
      platform text NOT NULL, app_version text NOT NULL, is_active boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE push_deliveries (
      notification_id uuid NOT NULL REFERENCES notifications(id),
      device_id uuid NOT NULL REFERENCES devices(id), delivered_at timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY(notification_id, device_id)
    );
    CREATE TABLE login_attempts (
      key_hash text PRIMARY KEY, attempts integer NOT NULL, window_start timestamptz NOT NULL
    );
    """
    for statement in schema.split(";"):
        if statement.strip():
            op.execute(statement)
    # A deferred guard sees the final carved state, not intermediate transaction geometry.
    op.execute("""
    CREATE FUNCTION assert_no_territory_overlap() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM territories a JOIN territories b ON a.id <> b.id
          AND a.geom && b.geom AND ST_Relate(a.geom, b.geom, '2********')
        WHERE a.id = NEW.id AND a.active AND b.active
      ) THEN RAISE EXCEPTION 'Active territories overlap' USING ERRCODE = '23514'; END IF;
      RETURN NULL;
    END $$;
    """)
    op.execute("""
    CREATE CONSTRAINT TRIGGER territory_overlap_guard
      AFTER INSERT OR UPDATE ON territories DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION assert_no_territory_overlap();
    """)


def downgrade():
    op.execute(
        "DROP TABLE login_attempts, push_deliveries, devices, notifications, territories, runs, friendships, sessions, users CASCADE"
    )
    op.execute("DROP FUNCTION assert_no_territory_overlap()")
    # PostGIS can be shared by another application; never drop it on downgrade.
