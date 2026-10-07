from sqlalchemy import text
from sqlalchemy.orm import Session


class Repository:
    def __init__(self, session: Session):
        self.session = session

    def execute(self, sql: str, **params):
        return self.session.execute(text(sql), params)

    def one(self, sql: str, **params):
        row = self.execute(sql, **params).mappings().first()
        return dict(row) if row else None

    def all(self, sql: str, **params):
        return [dict(r) for r in self.execute(sql, **params).mappings()]

    def game_lock(self):
        # One lock is intentionally conservative for the laptop phase; row locks miss new land.
        self.execute("SELECT pg_advisory_xact_lock(724019833)")

    def now(self):
        return self.execute("SELECT clock_timestamp()").scalar_one()
