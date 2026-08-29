"""Top-level configuration: which instances this deployment loads, and how
bundles move between them.

The shape is validated against the mode, which is what keeps a split deployment
from holding the far end's credentials. See ADR-018 and ADR-019.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError, RoleError
from .instance import InstanceConfig, load_instance_config
from .schema import CanonicalSchema, load_canonical_schema

Role = Literal["source", "destination"]

SOURCE_COMMANDS = frozenset({"export", "normalize"})
DESTINATION_COMMANDS = frozenset({"plan", "resolve", "apply", "adopt"})
ROLE_FREE_COMMANDS = frozenset({"doctor"})


class Transport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["file", "https"] = "file"
    outbox: str = Field(min_length=1)
    inbox: str = Field(min_length=1)

    @model_validator(mode="after")
    def _https_not_built(self) -> Transport:
        if self.kind == "https":
            raise ValueError("the https transport is not implemented (ADR-015)")
        return self


class TopLevelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["split", "direct"]
    source: str | None = None
    destination: str | None = None
    canonical_schema: str = Field(min_length=1)
    transport: Transport

    @model_validator(mode="after")
    def _shape_matches_mode(self) -> TopLevelConfig:
        named = [k for k, v in (("source", self.source), ("destination", self.destination)) if v]
        if self.mode == "split":
            if len(named) != 1:
                raise ValueError(
                    "mode: split names exactly one of source or destination, "
                    f"but names {named or 'neither'}; a split deployment has no place "
                    f"to put the far end's credentials"
                )
        elif len(named) != 2:
            raise ValueError(
                f"mode: direct names both source and destination, but names {named or 'neither'}"
            )
        if self.source and self.destination and self.source == self.destination:
            raise ValueError("source and destination name the same instance file")
        return self

    @property
    def roles(self) -> frozenset[Role]:
        held: set[Role] = set()
        if self.source:
            held.add("source")
        if self.destination:
            held.add("destination")
        return frozenset(held)

    def permits(self, command: str) -> bool:
        if command in ROLE_FREE_COMMANDS:
            return True
        if command in SOURCE_COMMANDS:
            return "source" in self.roles
        if command in DESTINATION_COMMANDS:
            return "destination" in self.roles
        raise ValueError(f"unknown command {command!r}")

    def require(self, command: str) -> None:
        if not self.permits(command):
            held = ", ".join(sorted(self.roles))
            raise RoleError(
                f"this deployment is {held} only and cannot run {command!r}; "
                f"{command!r} belongs to the other end of the flow"
            )


class Deployment(BaseModel):
    """A fully resolved configuration: the top-level file plus what it names."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    config: TopLevelConfig
    schema_: CanonicalSchema = Field(alias="schema")
    source: InstanceConfig | None = None
    destination: InstanceConfig | None = None

    @property
    def roles(self) -> frozenset[Role]:
        return self.config.roles

    def require(self, command: str) -> None:
        self.config.require(command)


def load_top_level_config(path: str | Path) -> TopLevelConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError("config not found", path=path) from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {exc}", path=path) from None
    if not isinstance(raw, dict):
        raise ConfigError("expected a mapping at the top level", path=path)
    try:
        return TopLevelConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc), path=path) from None


def load_deployment(path: str | Path, *, root: str | Path | None = None) -> Deployment:
    """Load the top-level config and everything it names.

    Paths inside the config are resolved against `root`, defaulting to the
    current directory, so a config can be read from anywhere while its relative
    paths keep meaning what they meant when it was written.
    """
    config = load_top_level_config(path)
    base = Path(root) if root is not None else Path.cwd()
    schema = load_canonical_schema(base / config.canonical_schema)
    instances: dict[str, InstanceConfig | None] = {"source": None, "destination": None}
    for role in ("source", "destination"):
        named = getattr(config, role)
        if named:
            instances[role] = load_instance_config(base / named, schema)

    ids = {r: i.instance.id for r, i in instances.items() if i is not None}
    if len(set(ids.values())) != len(ids):
        raise ConfigError(
            f"source and destination declare the same instance id {next(iter(ids.values()))!r}",
            path=path,
        )
    return Deployment(
        config=config,
        schema=schema,
        source=instances["source"],
        destination=instances["destination"],
    )
