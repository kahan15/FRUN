from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import decode_access
from app.db.session import get_session
from app.repositories.users import Users

DB = Annotated[Session, Depends(get_session, scope="function")]
bearer = HTTPBearer(auto_error=False)


def current_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    if not credentials:
        raise AppError("unauthorized", "Please sign in.", 401)
    claims = decode_access(credentials.credentials)
    user = Users(db).session_user(claims["sub"], claims["sid"])
    if not user:
        raise AppError("unauthorized", "Please sign in again.", 401)
    user["session_id"] = claims["sid"]
    return user


CurrentUser = Annotated[dict, Depends(current_user)]
