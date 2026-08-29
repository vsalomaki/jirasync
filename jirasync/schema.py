"""The canonical schema: the vocabulary a bundle may use.

Byte-identical on both sides and agreed out of band. It says nothing about how
any instance stores anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .errors import ConfigError

FieldType = Literal["text", "wiki", "enum", "user", "date", "list<text>"]

Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class CanonicalField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: FieldType
    values: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _values_only_for_enum(self) -> CanonicalField:
        if self.type == "enum" and not self.values:
            raise ValueError("an enum field must declare its values")
        if self.type != "enum" and self.values is not None:
            raise ValueError(f"values are only meaningful for an enum, not {self.type}")
        if self.values and len(set(self.values)) != len(self.values):
            raise ValueError("duplicate value in enum")
        return self


class CanonicalSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    projects: tuple[Name, ...]
    issue_types: tuple[Name, ...]
    statuses: tuple[Name, ...]
    fields: dict[Name, CanonicalField]
    field_groups: tuple[tuple[Name, ...], ...] = ()
    link_types: tuple[Name, ...] = ()

    @model_validator(mode="after")
    def _check(self) -> CanonicalSchema:
        for label, values in (
            ("projects", self.projects),
            ("issue_types", self.issue_types),
            ("statuses", self.statuses),
            ("link_types", self.link_types),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate entry in {label}")
        if not self.fields:
            raise ValueError("at least one field must be declared")

        # A group names fields that resolve as a unit, so every name must be a
        # declared field. `status` is a top-level issue property and cannot be
        # grouped.
        for group in self.field_groups:
            if len(group) < 2:
                raise ValueError(f"field group {list(group)} needs at least two fields")
            if len(set(group)) != len(group):
                raise ValueError(f"field group {list(group)} repeats a field")
            for name in group:
                if name not in self.fields:
                    raise ValueError(
                        f"field group {list(group)} names {name!r}, which is not a declared field"
                    )
        return self


def load_canonical_schema(path: str | Path) -> CanonicalSchema:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError("canonical schema not found", path=path) from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {exc}", path=path) from None
    if not isinstance(raw, dict):
        raise ConfigError("expected a mapping at the top level", path=path)
    try:
        return CanonicalSchema.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc), path=path) from None
