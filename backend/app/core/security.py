import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import settings
from app.core.errors import AppError

HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def password_matches(encoded: str, plain: str) -> bool:
    try:
        return HASHER.verify(encoded, plain)
    except VerificationError:
        return False


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def access_token(user_id, session_id) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings().access_minutes),
            "iss": "territory-run",
            "aud": "territory-run-ios",
            "type": "access",
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def decode_access(token: str) -> dict:
    try:
        result = jwt.decode(
            token,
            settings().jwt_secret,
            algorithms=["HS256"],
            issuer="territory-run",
            audience="territory-run-ios",
            options={"require": ["exp", "sub", "sid", "type"]},
        )
        if result["type"] != "access":
            raise ValueError()
        from uuid import UUID

        UUID(result["sub"])
        UUID(result["sid"])
        return result
    except (jwt.PyJWTError, ValueError):
        raise AppError("unauthorized", "Please sign in again.", 401) from None
