"""Pseudonymous completion receipts for recoverable account deletion."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""CREATE TABLE account_deletions (
        request_hash text PRIMARY KEY, subject_hash text NOT NULL,
        completed_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )""")


def downgrade():
    op.execute("DROP TABLE account_deletions")
