from app.core.security import digest
from app.repositories.base import Repository


class Privacy(Repository):
    def receipt(self, request_id):
        return self.one(
            "SELECT subject_hash FROM account_deletions WHERE request_hash=:key",
            key=digest(str(request_id)),
        )

    def erase_account(self, user, request_id):
        uid = user["id"]
        # Preserve other runners' earned land and totals, removing identifying references.
        self.execute(
            """UPDATE runs SET result=jsonb_set(result,'{steals}',(
            SELECT coalesce(jsonb_agg(CASE WHEN entry->>'victim_username'=:name
                THEN jsonb_set(entry,'{victim_username}','"Deleted runner"'::jsonb)
                ELSE entry END),'[]'::jsonb)
            FROM jsonb_array_elements(coalesce(result->'steals','[]'::jsonb)) entry
        )) WHERE user_id<>:uid AND EXISTS (
            SELECT 1 FROM jsonb_array_elements(coalesce(result->'steals','[]'::jsonb)) entry
            WHERE entry->>'victim_username'=:name)""",
            uid=uid,
            name=user["username"],
        )
        affected_notes = """SELECT id FROM notifications WHERE user_id=:uid
            OR payload->>'run_id' IN (SELECT id::text FROM runs WHERE user_id=:uid)"""
        self.execute(
            f"""DELETE FROM push_deliveries WHERE notification_id IN ({affected_notes})
            OR device_id IN (SELECT id FROM devices WHERE user_id=:uid)""",
            uid=uid,
        )
        self.execute(f"DELETE FROM notifications WHERE id IN ({affected_notes})", uid=uid)
        self.execute("DELETE FROM devices WHERE user_id=:uid", uid=uid)
        self.execute("DELETE FROM contests WHERE owner_a=:uid OR owner_b=:uid", uid=uid)
        self.execute(
            "DELETE FROM friendships WHERE requester_id=:uid OR addressee_id=:uid", uid=uid
        )
        self.execute("UPDATE territories SET lost_to_id=NULL WHERE lost_to_id=:uid", uid=uid)
        self.execute(
            "UPDATE territories SET stolen_from_id=NULL WHERE stolen_from_id=:uid", uid=uid
        )
        self.execute("DELETE FROM territories WHERE owner_id=:uid", uid=uid)
        self.execute("DELETE FROM runs WHERE user_id=:uid", uid=uid)
        self.execute("DELETE FROM sessions WHERE user_id=:uid", uid=uid)
        self.execute("DELETE FROM users WHERE id=:uid", uid=uid)
        self.execute(
            """INSERT INTO account_deletions(request_hash,subject_hash)
            VALUES (:request,:subject)""",
            request=digest(str(request_id)),
            subject=digest("deletion-subject:" + str(uid)),
        )
