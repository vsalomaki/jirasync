"""Local user identity to canonical identity.

Each side maintains its own file; the canonical id is the shared handle. The
peer's usernames never appear here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical: str = Field(min_length=1)
    display: str = Field(min_length=1)


class User(Identity):
    local_key: str | None = None
    local_name: str | None = None


class UnmappedUser(Identity):
    """A canonical identity referenced by inbound bundles with no local counterpart.

    The display name still renders mentions as readable text.
    """


class UserMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key_on: Literal["key", "name"] = "key"
    users: tuple[User, ...] = ()
    unmapped: tuple[UnmappedUser, ...] = ()

    def _local_of(self, user: User) -> str | None:
        return user.local_key if self.key_on == "key" else user.local_name

    @model_validator(mode="after")
    def _check(self) -> UserMap:
        needed = "local_key" if self.key_on == "key" else "local_name"
        for user in self.users:
            if self._local_of(user) is None:
                raise ValueError(
                    f"user {user.canonical!r} has no {needed}, which key_on: {self.key_on} requires"
                )

        seen: set[str] = set()
        for entry in self.identities():
            if entry.canonical in seen:
                raise ValueError(f"canonical id {entry.canonical!r} appears more than once")
            seen.add(entry.canonical)

        locals_seen: set[str] = set()
        for user in self.users:
            local = self._local_of(user)
            if local in locals_seen:
                raise ValueError(f"local user {local!r} is mapped to more than one canonical id")
            if local is not None:
                locals_seen.add(local)
        return self

    def identities(self) -> tuple[Identity, ...]:
        return (*self.users, *self.unmapped)

    def to_canonical(self, local: str) -> str | None:
        for user in self.users:
            if self._local_of(user) == local:
                return user.canonical
        return None

    def to_local(self, canonical: str) -> str | None:
        for user in self.users:
            if user.canonical == canonical:
                return self._local_of(user)
        return None

    def display_name(self, canonical: str) -> str | None:
        for entry in self.identities():
            if entry.canonical == canonical:
                return entry.display
        return None


def load_user_map(path: str | Path) -> UserMap:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError("user map not found", path=path) from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {exc}", path=path) from None
    if not isinstance(raw, dict):
        raise ConfigError("expected a mapping at the top level", path=path)
    try:
        return UserMap.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc), path=path) from None
