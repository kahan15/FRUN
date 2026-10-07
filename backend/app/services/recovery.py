"""Password recovery with durable encrypted fake delivery; no external transport."""

import json
import secrets
from datetime import timedelta

from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import HASHER, digest
from app.repositories.users import Users

ACKNOWLEDGEMENT = "If an eligible account uses that email, a recovery link will be sent."


class Recovery:
    def __init__(self, repo: Users):
        self.repo = repo

    def request(self, email: str, ip: str):
        cfg = settings()
        if cfg.recovery_delivery != "local_fake" or cfg.environment == "production":
            raise AppError("recovery_unavailable", "Password recovery is not available yet.", 503)
        # No account-specific result, including throttle/cooldown/inactive-account paths.
        ip_attempts = self.repo.throttle(digest("recovery-ip:" + ip))
        if ip_attempts > 20:
            return {"message": ACKNOWLEDGEMENT}
        email_attempts = self.repo.throttle(digest("recovery-email:" + email.lower()))
        if email_attempts > 3:
            return {"message": ACKNOWLEDGEMENT}
        # Perform the same token/encryption work for unknown addresses. Neither tokens
        # nor email addresses are returned through a client-facing inbox endpoint.
        token = secrets.token_urlsafe(48)
        payload = json.dumps(
            {"to": email.lower(), "link": cfg.recovery_base_url + "/password-reset#" + token}
        )
        ciphertext = Fernet(cfg.recovery_encryption_key.encode()).encrypt(payload.encode()).decode()
        user = self.repo.one(
            "SELECT id FROM users WHERE email=:email AND is_active FOR UPDATE", email=email.lower()
        )
        if user:
            now = self.repo.now()
            self.repo.execute(
                """INSERT INTO password_recoveries(user_id,token_hash,expires_at,delivery_ciphertext)
                VALUES (:uid,:hash,:expires,:ciphertext) ON CONFLICT (user_id) DO UPDATE
                SET token_hash=excluded.token_hash, expires_at=excluded.expires_at,
                    delivery_ciphertext=excluded.delivery_ciphertext, created_at=clock_timestamp()
                WHERE password_recoveries.created_at < clock_timestamp()-interval '60 seconds'""",
                uid=user["id"],
                hash=digest(token),
                expires=now + timedelta(minutes=cfg.recovery_minutes),
                ciphertext=ciphertext,
            )
        return {"message": ACKNOWLEDGEMENT}

    def complete(self, token: str, password: str, ip: str):
        if self.repo.throttle(digest("reset-ip:" + ip)) > 20:
            raise AppError("rate_limited", "Too many attempts. Try again in 15 minutes.", 429)
        invalid = AppError(
            "invalid_recovery",
            "This link has expired or was already used. Request another link.",
            400,
        )
        recovery = self.repo.one(
            "SELECT user_id FROM password_recoveries WHERE token_hash=:hash", hash=digest(token)
        )
        if not recovery:
            raise invalid
        # Always acquire the account lock before consuming the token. Login uses the
        # same lock; concurrent reset submissions can have only one winner.
        user = self.repo.one(
            "SELECT id FROM users WHERE id=:id AND is_active FOR UPDATE", id=recovery["user_id"]
        )
        if not user:
            raise invalid
        consumed = self.repo.one(
            """DELETE FROM password_recoveries WHERE user_id=:uid AND token_hash=:hash
            AND expires_at>clock_timestamp() RETURNING user_id""",
            uid=user["id"],
            hash=digest(token),
        )
        if not consumed:
            raise invalid
        encoded = HASHER.hash(password)
        self.repo.execute(
            "UPDATE users SET password_hash=:hash,updated_at=clock_timestamp() WHERE id=:uid",
            hash=encoded,
            uid=user["id"],
        )
        self.repo.execute(
            "UPDATE sessions SET revoked_at=clock_timestamp() WHERE user_id=:uid AND revoked_at IS NULL",
            uid=user["id"],
        )
        return {"ok": True}
