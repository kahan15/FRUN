from app.repositories.base import Repository


class Admin(Repository):
    def audit_runs(self, limit):
        return self.all(
            """SELECT id,user_id,status,cheat_report,review_notes,created_at
          FROM runs WHERE status IN ('rejected','flagged') ORDER BY created_at DESC LIMIT :limit""",
            limit=limit,
        )

    def raw_run(self, run_id):
        return self.one(
            "SELECT r.raw_upload,u.sex FROM runs r JOIN users u ON u.id=r.user_id WHERE r.id=:id",
            id=run_id,
        )

    def review(self, run_id, notes):
        return self.execute(
            "UPDATE runs SET review_notes=:notes WHERE id=:id", notes=notes, id=run_id
        ).rowcount

    def password(self, user_id, encoded):
        self.execute("SELECT id FROM users WHERE id=:id FOR UPDATE", id=user_id)
        self.execute(
            "UPDATE users SET password_hash=:hash,updated_at=now() WHERE id=:id",
            hash=encoded,
            id=user_id,
        )
        self.execute("UPDATE sessions SET revoked_at=now() WHERE user_id=:id", id=user_id)
        self.execute("DELETE FROM password_recoveries WHERE user_id=:id", id=user_id)
