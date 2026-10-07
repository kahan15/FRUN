"""Directional blocks and encrypted, local-only password recovery delivery."""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.execute("""CREATE TABLE user_blocks (
        blocker_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        blocked_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (blocker_id, blocked_id), CHECK (blocker_id <> blocked_id)
    );
    CREATE INDEX user_blocks_reverse ON user_blocks(blocked_id, blocker_id);
    CREATE TABLE password_recoveries (
        user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        token_hash text NOT NULL UNIQUE,
        expires_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        delivery_ciphertext text NOT NULL
    );
    CREATE INDEX password_recoveries_expiry ON password_recoveries(expires_at);
    CREATE VIEW accepted_friendships AS SELECT f.* FROM friendships f
      WHERE status='accepted' AND NOT EXISTS (
        SELECT 1 FROM user_blocks b
        WHERE (b.blocker_id=f.requester_id AND b.blocked_id=f.addressee_id)
           OR (b.blocker_id=f.addressee_id AND b.blocked_id=f.requester_id));
    """)


def downgrade():
    op.execute("DROP VIEW accepted_friendships; DROP TABLE password_recoveries; DROP TABLE user_blocks")
