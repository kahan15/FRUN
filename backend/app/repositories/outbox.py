from app.repositories.base import Repository


class Outbox(Repository):
    def pending(self):
        return self.one("""SELECT * FROM notifications WHERE delivered_at IS NULL AND next_attempt_at<=now()
          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1""")

    def devices(self, notification):
        return self.all(
            """SELECT d.* FROM devices d WHERE d.user_id=:uid AND d.is_active
          AND NOT EXISTS(SELECT 1 FROM push_deliveries p WHERE p.device_id=d.id AND p.notification_id=:nid)""",
            uid=notification["user_id"],
            nid=notification["id"],
        )

    def delivered(self, notification_id, device_id):
        self.execute(
            "INSERT INTO push_deliveries(notification_id,device_id) VALUES (:n,:d) ON CONFLICT DO NOTHING",
            n=notification_id,
            d=device_id,
        )

    def deactivate(self, device_id):
        self.execute("UPDATE devices SET is_active=false WHERE id=:id", id=device_id)

    def finish(self, notification_id):
        self.execute(
            "UPDATE notifications SET delivered_at=now(),last_error=NULL WHERE id=:id",
            id=notification_id,
        )

    def retry(self, notification_id, attempts, error):
        delay = min(86400, 30 * 2 ** min(attempts, 12))
        self.execute(
            """UPDATE notifications SET attempts=attempts+1,last_error=:error,
          next_attempt_at=now()+make_interval(secs => :delay) WHERE id=:id""",
            error=error[:200],
            delay=delay,
            id=notification_id,
        )

    def cleanup_attempts(self):
        self.execute("DELETE FROM login_attempts WHERE window_start < now()-interval '1 day'")
