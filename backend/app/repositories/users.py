from datetime import timedelta
from uuid import uuid4

from app.repositories.base import Repository


class Users(Repository):
    def by_login(self, login: str, *, lock=False):
        return self.one(
            "SELECT * FROM users WHERE username=:v OR email=:v" + (" FOR UPDATE" if lock else ""),
            v=login.lower(),
        )

    def by_id(self, user_id):
        return self.one("SELECT * FROM users WHERE id=:id AND is_active", id=user_id)

    def insert(self, data, password_hash: str):
        return self.one(
            """INSERT INTO users(id,email,username,display_name,password_hash,sex)
            VALUES (:id,:email,:username,:name,:hash,:sex) RETURNING *""",
            id=uuid4(),
            email=data.email,
            username=data.username,
            name=data.display_name,
            hash=password_hash,
            sex=data.sex,
        )

    def create_session(self, user_id, token_hash: str, days: int):
        return self.one(
            """INSERT INTO sessions(id,user_id,token_hash,expires_at)
            VALUES (:id,:uid,:hash,:expires) RETURNING *""",
            id=uuid4(),
            uid=user_id,
            hash=token_hash,
            expires=self.now() + timedelta(days=days),
        )

    def refresh_session(self, token_hash: str):
        return self.one("SELECT * FROM sessions WHERE token_hash=:hash FOR UPDATE", hash=token_hash)

    def rotate(self, session_id, token_hash: str):
        self.execute(
            "UPDATE sessions SET token_hash=:hash WHERE id=:id", hash=token_hash, id=session_id
        )

    def session_user(self, user_id, session_id):
        return self.one(
            """SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id
            WHERE u.id=:uid AND s.id=:sid AND u.is_active AND s.revoked_at IS NULL
              AND s.expires_at > now()""",
            uid=user_id,
            sid=session_id,
        )

    def logout(self, session_id):
        self.execute("UPDATE sessions SET revoked_at=now() WHERE id=:id", id=session_id)

    def throttle(self, key: str):
        # A tiny independent transaction retains failed attempts when auth itself rolls back.
        from sqlalchemy import text

        from app.db.session import engine

        with engine().begin() as connection:
            return connection.execute(
                text("""INSERT INTO login_attempts VALUES (:key,1,now())
              ON CONFLICT (key_hash) DO UPDATE SET
                attempts=CASE WHEN login_attempts.window_start < now()-interval '15 minutes'
                         THEN 1 ELSE login_attempts.attempts+1 END,
                window_start=CASE WHEN login_attempts.window_start < now()-interval '15 minutes'
                             THEN now() ELSE login_attempts.window_start END
              RETURNING attempts"""),
                {"key": key},
            ).scalar_one()

    def friend_ids(self, user_id) -> set:
        rows = self.all(
            """SELECT CASE WHEN requester_id=:id THEN addressee_id ELSE requester_id END id
             FROM accepted_friendships WHERE status='accepted' AND (requester_id=:id OR addressee_id=:id)""",
            id=user_id,
        )
        return {r["id"] for r in rows}

    def friends(self, user_id):
        return self.all(
            """SELECT u.id,u.username,u.display_name,f.status,
            (f.addressee_id=:id) incoming FROM friendships f JOIN users u
            ON u.id=CASE WHEN f.requester_id=:id THEN f.addressee_id ELSE f.requester_id END
            WHERE (f.requester_id=:id OR f.addressee_id=:id) AND f.status <> 'blocked'
            AND NOT EXISTS (SELECT 1 FROM user_blocks b
              WHERE (b.blocker_id=:id AND b.blocked_id=u.id)
                 OR (b.blocked_id=:id AND b.blocker_id=u.id))
            ORDER BY u.username""",
            id=user_id,
        )

    def search(self, query: str, user_id):
        return self.all(
            """SELECT id,username,display_name FROM users WHERE is_active AND id<>:id
          AND NOT EXISTS (SELECT 1 FROM user_blocks b
            WHERE (b.blocker_id=:id AND b.blocked_id=users.id)
               OR (b.blocked_id=:id AND b.blocker_id=users.id))
          AND username LIKE :q ESCAPE '\\' ORDER BY username LIMIT 20""",
            id=user_id,
            q=query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
        )

    def friendship(self, a, b):
        return self.one(
            """SELECT * FROM friendships WHERE least(requester_id,addressee_id)=least(CAST(:a AS uuid),CAST(:b AS uuid))
              AND greatest(requester_id,addressee_id)=greatest(CAST(:a AS uuid),CAST(:b AS uuid)) FOR UPDATE""",
            a=a,
            b=b,
        )

    def blocked(self, a, b):
        return (
            self.one(
                """SELECT 1 FROM user_blocks WHERE
            (blocker_id=:a AND blocked_id=:b) OR (blocker_id=:b AND blocked_id=:a)""",
                a=a,
                b=b,
            )
            is not None
        )

    def blocks(self, user_id):
        return self.all(
            """SELECT u.id,u.username,u.display_name FROM users u JOIN user_blocks b
            ON u.id=b.blocked_id WHERE b.blocker_id=:id ORDER BY u.username""",
            id=user_id,
        )

    def block(self, a, b):
        self.remove(a, b)
        self.execute(
            "INSERT INTO user_blocks(blocker_id,blocked_id) VALUES (:a,:b) ON CONFLICT DO NOTHING",
            a=a,
            b=b,
        )

    def unblock(self, a, b):
        self.execute("DELETE FROM user_blocks WHERE blocker_id=:a AND blocked_id=:b", a=a, b=b)

    def request(self, a, b):
        self.execute(
            "INSERT INTO friendships(requester_id,addressee_id,status) VALUES (:a,:b,'pending')",
            a=a,
            b=b,
        )

    def accept(self, a, b):
        self.execute(
            "UPDATE friendships SET status='accepted',accepted_at=clock_timestamp() WHERE requester_id=:b AND addressee_id=:a",
            a=a,
            b=b,
        )

    def remove(self, a, b):
        self.execute(
            "DELETE FROM contests WHERE owner_a=least(CAST(:a AS uuid),CAST(:b AS uuid)) AND owner_b=greatest(CAST(:a AS uuid),CAST(:b AS uuid))",
            a=a,
            b=b,
        )
        self.execute(
            "DELETE FROM friendships WHERE (requester_id=:a AND addressee_id=:b) OR (requester_id=:b AND addressee_id=:a)",
            a=a,
            b=b,
        )
