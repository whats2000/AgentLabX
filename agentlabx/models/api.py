from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):  # type: ignore[explicit-any]
    display_name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=320)
    passphrase: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):  # type: ignore[explicit-any]
    email: str
    passphrase: str


class IdentityResponse(BaseModel):  # type: ignore[explicit-any]
    id: str
    display_name: str
    email: str
    auther_name: str
    capabilities: list[str]


class CredentialSlotResponse(BaseModel):  # type: ignore[explicit-any]
    slot: str
    updated_at: str


class StoreCredentialRequest(BaseModel):  # type: ignore[explicit-any]
    value: str = Field(min_length=1, max_length=4096)


class AdminUserResponse(BaseModel):  # type: ignore[explicit-any]
    id: str
    display_name: str
    email: str
    auther_name: str
    capabilities: list[str]


class GrantCapabilityRequest(BaseModel):  # type: ignore[explicit-any]
    capability: str


class UpdateDisplayNameRequest(BaseModel):  # type: ignore[explicit-any]
    display_name: str = Field(min_length=1, max_length=128)


class UpdateEmailRequest(BaseModel):  # type: ignore[explicit-any]
    new_email: str = Field(min_length=3, max_length=320)
    passphrase: str = Field(min_length=1, max_length=256)


class UpdatePassphraseRequest(BaseModel):  # type: ignore[explicit-any]
    old_passphrase: str = Field(min_length=1, max_length=256)
    new_passphrase: str = Field(min_length=8, max_length=256)


class RunsListResponse(BaseModel):  # type: ignore[explicit-any]
    runs: list[str]  # placeholder — no runs in A1


class EventResponse(BaseModel):  # type: ignore[explicit-any]
    kind: str
    at: str
    payload: dict[str, str | int | float | bool | None]
