import secrets

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import DUMMY_HASH, HASHER, access_token, digest, password_matches
from app.repositories.users import Users


def public(user):
    return {k: user[k] for k in ("id", "username", "display_name")}


class Auth:
    def __init__(self, repository: Users):
        self.repo = repository

    def issue(self, user):
        token = secrets.token_urlsafe(48)
        session = self.repo.create_session(user["id"], digest(token), settings().refresh_days)
        return {
            "access_token": access_token(user["id"], session["id"]),
            "refresh_token": token,
            "user": public(user),
        }

    def register(self, data, ip):
        if not settings().registration_enabled:
            raise AppError("registration_closed", "Registration is currently closed.", 403)
        if self.repo.throttle(digest("register:" + ip)) > 20:
            raise AppError("rate_limited", "Try registering again in 15 minutes.", 429)
        if self.repo.by_login(data.username) or self.repo.by_login(data.email):
            raise AppError("account_exists", "That username or email is already registered.", 409)
        return self.issue(self.repo.insert(data, HASHER.hash(data.password)))

    def login(self, data, ip):
        # Bound expensive password hashing even when an attacker cycles usernames.
        if self.repo.throttle(digest("login-ip:" + ip)) > settings().login_ip_attempts_per_window:
            raise AppError("rate_limited", "Too many attempts. Try again in 15 minutes.", 429)
        if self.repo.throttle(digest("login:" + ip + ":" + data.username.lower())) > 15:
            raise AppError("rate_limited", "Too many attempts. Try again in 15 minutes.", 429)
        # Serialize successful login with password reset, preventing an old-password
        # login from minting a valid session after recovery has revoked sessions.
        user = self.repo.by_login(data.username, lock=True)
        valid = password_matches(user["password_hash"] if user else DUMMY_HASH, data.password)
        if not user or not valid or not user["is_active"]:
            raise AppError("invalid_credentials", "Incorrect username or password.", 401)
        return self.issue(user)

    def refresh(self, token):
        session = self.repo.refresh_session(digest(token))
        if not session or session["revoked_at"] or session["expires_at"] <= self.repo.now():
            raise AppError("unauthorized", "Please sign in again.", 401)
        user = self.repo.by_id(session["user_id"])
        if not user:
            raise AppError("unauthorized", "Please sign in again.", 401)
        replacement = secrets.token_urlsafe(48)
        self.repo.rotate(session["id"], digest(replacement))
        return {
            "access_token": access_token(user["id"], session["id"]),
            "refresh_token": replacement,
            "user": public(user),
        }
