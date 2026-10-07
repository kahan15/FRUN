from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Register(StrictModel):
    email: EmailStr
    username: str = Field(pattern=r"^[a-zA-Z0-9_]{3,24}$")
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=60)
    sex: Literal["M", "F", "X"] = "X"

    @field_validator("username", "email")
    @classmethod
    def lowercase(cls, v: str) -> str:
        return v.lower()


class Login(StrictModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Refresh(StrictModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class RecoveryRequest(StrictModel):
    email: EmailStr


class RecoveryComplete(StrictModel):
    token: str = Field(min_length=64, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    password: str = Field(min_length=10, max_length=128)


class FriendAction(StrictModel):
    user_id: UUID


class Fix(StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timestamp: AwareDatetime
    accuracy: float = Field(ge=0)
    segment: int = Field(default=0, ge=0)


class RunUpload(StrictModel):
    client_run_id: UUID
    started_at: AwareDatetime
    ended_at: AwareDatetime
    step_count: int | None = Field(default=None, ge=0)
    points: list[Fix] = Field(max_length=60000)


class AccountDeletionRequest(StrictModel):
    request_id: UUID
    password: str = Field(min_length=1, max_length=128)


class AccountDeletionLookup(StrictModel):
    request_id: UUID


class AccountDeletionStatus(BaseModel):
    completed: bool


class DeviceRegistration(StrictModel):
    apns_token: str = Field(pattern=r"^[0-9a-fA-F]{64,200}$")
    platform: Literal["ios"] = "ios"
    app_version: str = Field(max_length=30)


class UserPublic(BaseModel):
    id: UUID
    username: str
    display_name: str


class AuthResult(BaseModel):
    access_token: str
    refresh_token: str
    user: UserPublic


class Steal(BaseModel):
    victim_username: str
    area_m2: float


class RunResult(BaseModel):
    id: UUID
    client_run_id: UUID
    status: str
    reasons: list[str]
    fragment_count: int
    new_area_m2: float
    refreshed_area_m2: float
    blocked_area_m2: float
    stolen_area_m2: float
    steals: list[Steal]
    distance_m: float
    duration_s: float
    was_duplicate: bool = False
    created_at: datetime


class TerritoryGeometry(BaseModel):
    type: Literal["MultiPolygon"] = "MultiPolygon"
    coordinates: list[list[list[list[float]]]]


class TerritoryProperties(BaseModel):
    owner_id: UUID
    username: str
    area_m2: float
    claimed_at: datetime
    expires_at: datetime
    contested_geometry: TerritoryGeometry | None = None


class TerritoryFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: TerritoryGeometry
    properties: TerritoryProperties


class TerritoryCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[TerritoryFeature]
