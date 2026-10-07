from typing import Literal

from fastapi import APIRouter, Query, Request

from app.core.deps import DB, CurrentUser
from app.core.errors import AppError
from app.repositories.game import Game
from app.repositories.privacy import Privacy
from app.repositories.users import Users
from app.schemas.contracts import (
    AccountDeletionLookup,
    AccountDeletionRequest,
    AccountDeletionStatus,
    AuthResult,
    DeviceRegistration,
    FriendAction,
    Login,
    RecoveryComplete,
    RecoveryRequest,
    Refresh,
    Register,
    RunResult,
    RunUpload,
    TerritoryCollection,
    UserPublic,
)
from app.services.auth import Auth, public
from app.services.claims import Claims
from app.services.friends import Friends
from app.services.privacy import AccountPrivacy
from app.services.recovery import Recovery

router = APIRouter()


@router.post("/auth/password-recovery", status_code=202)
def recovery_request(data: RecoveryRequest, request: Request, db: DB):
    return Recovery(Users(db)).request(
        str(data.email), request.client.host if request.client else "local"
    )


@router.post("/auth/password-recovery/complete")
def recovery_complete(data: RecoveryComplete, request: Request, db: DB):
    return Recovery(Users(db)).complete(
        data.token, data.password, request.client.host if request.client else "local"
    )


@router.post("/auth/register", response_model=AuthResult, status_code=201)
def register(data: Register, request: Request, db: DB):
    return Auth(Users(db)).register(data, request.client.host if request.client else "local")


@router.post("/auth/login", response_model=AuthResult)
def login(data: Login, request: Request, db: DB):
    return Auth(Users(db)).login(data, request.client.host if request.client else "local")


@router.post("/auth/refresh", response_model=AuthResult)
def refresh(data: Refresh, db: DB):
    return Auth(Users(db)).refresh(data.refresh_token)


@router.post("/auth/logout")
def logout(user: CurrentUser, db: DB):
    Users(db).logout(user["session_id"])
    return {"ok": True}


@router.delete("/auth/account", response_model=AccountDeletionStatus)
def delete_account(data: AccountDeletionRequest, user: CurrentUser, db: DB):
    return AccountPrivacy(Privacy(db)).delete(user, data)


@router.post("/auth/account-deletion/status", response_model=AccountDeletionStatus)
def deletion_status(data: AccountDeletionLookup, db: DB):
    return AccountPrivacy(Privacy(db)).status(data.request_id)


@router.get("/auth/me", response_model=UserPublic)
def me(user: CurrentUser):
    return public(user)


@router.get("/friends")
def friends(user: CurrentUser, db: DB):
    return Users(db).friends(user["id"])


@router.get("/friends/search")
def search(user: CurrentUser, db: DB, q: str = Query(min_length=2, max_length=24)):
    return Users(db).search(q, user["id"])


@router.get("/friends/blocked", response_model=list[UserPublic])
def blocked(user: CurrentUser, db: DB):
    return Users(db).blocks(user["id"])


@router.post("/friends/{action}")
def friendship(
    action: Literal["request", "accept", "remove", "block", "unblock"],
    data: FriendAction,
    user: CurrentUser,
    db: DB,
):
    Friends(Users(db)).change(action, user["id"], data.user_id)
    return {"ok": True}


@router.post("/runs", response_model=RunResult)
def upload(data: RunUpload, user: CurrentUser, db: DB):
    return Claims(Game(db), Users(db)).upload(user, data)


@router.get("/runs", response_model=list[RunResult])
def runs(
    user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    return Game(db).history(user["id"], limit, offset)


@router.get("/territories", response_model=TerritoryCollection)
def territories(user: CurrentUser, db: DB, state: Literal["current", "past"] = "current"):
    return Game(db).territories(user["id"], state)


@router.get("/territories/stats")
def stats(user: CurrentUser, db: DB):
    return Game(db).stats(user["id"])


@router.get("/leaderboard")
def leaderboard(user: CurrentUser, db: DB):
    return Game(db).leaderboard(user["id"])


@router.get("/notifications")
def notifications(
    user: CurrentUser, db: DB, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    return Game(db).notifications(user["id"], limit, offset)


@router.get("/notifications/unread-count")
def unread(user: CurrentUser, db: DB):
    return {"count": Game(db).unread(user["id"])}


@router.post("/notifications/read-all")
def read_all(user: CurrentUser, db: DB):
    Game(db).read_all(user["id"])
    return {"ok": True}


@router.post("/devices")
def device(data: DeviceRegistration, user: CurrentUser, db: DB):
    Game(db).register_device(user["id"], data)
    return {"ok": True}


@router.delete("/devices/{token}")
def remove_device(token: str, user: CurrentUser, db: DB):
    Game(db).unregister_device(user["id"], token)
    return {"ok": True}


health = APIRouter()


@health.get("/health/live")
def live():
    return {"status": "ok"}


@health.get("/health/ready")
def ready(db: DB):
    try:
        return {"status": "ok", "postgis": Game(db).health()}
    except Exception:
        raise AppError("not_ready", "Database is not ready.", 503) from None
