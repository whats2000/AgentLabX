from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class AuthError(Exception):
    """Authentication failed (wrong credentials, revoked, expired)."""


@dataclass(frozen=True)
class Identity:
    id: str
    auther_name: str
    display_name: str
    capabilities: frozenset[str]


@runtime_checkable
class Auther(Protocol):
    name: str

    def authenticate(self, credentials: dict[str, str]) -> Identity: ...
