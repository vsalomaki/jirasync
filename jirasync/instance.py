"""Configuration for one Jira instance.

Describes how one Jira stores canonical things. Never references another
instance, in either mode (ADR-018).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .errors import ConfigError
from .schema import CanonicalSchema

OnConflict = Literal["interactive", "newest_wins", "prefer_local", "prefer_remote", "manual_only"]

# The exporter appends `AND updated >= <watermark>` itself, so a scope that moves
# on its own makes the result set non-deterministic between runs. See ADR-011.
#
# JQL keywords and function names are case insensitive, so every pattern here is
# too. Missing one is the expensive direction: a scope that drifts is invisible
# until someone notices issues have silently entered or left it.
_JQL_FUNCTION = re.compile(
    r"\b(?:now|currentLogin|lastLogin|currentUser|(?:start|end)Of\w*)\s*\(",
    re.IGNORECASE,
)
_JQL_RELATIVE_LITERAL = re.compile(r"(?<![\w.])[-+]\s*\d+[smhdwMy]\b")
_JQL_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
# A field sits at the start of a clause and is followed by an operator. Matching
# on position is what separates the `updated` field from the word `updated`
# appearing inside a field name or a text search value. The operator list has to
# be complete, including the multiword forms: miss one and the field it guards
# stops being checked at all.
_JQL_OPERATOR = r"""
    [<>]=? | !?[=~]
  | \b(?: not \s+ in
        | is (?:\s+ not)?
        | in
        | was (?:\s+ not)? (?:\s+ in)?
        | changed
        ) \b
"""
_JQL_FIELD = re.compile(
    r"""(?:\A|[\s(,])
        (?: "(?P<dq>[^"]*)" | '(?P<sq>[^']*)' | (?P<bare>[A-Za-z][\w.]*) )
        \s*
        (?:"""
    + _JQL_OPERATOR
    + r""")
    """,
    re.VERBOSE | re.IGNORECASE,
)
_JQL_ORDER_BY = re.compile(r"\border\s+by\b", re.IGNORECASE)

_DURATION = re.compile(r"^(?P<n>\d+)(?P<unit>[smh])$")


def _parse_duration(value: str) -> timedelta:
    m = _DURATION.match(value.strip())
    if not m:
        raise ValueError(f"expected a duration like '2m' or '30s', got {value!r}")
    n = int(m.group("n"))
    return timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours"}[m.group("unit")]: n})


class Auth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["pat", "basic", "cloud_token"] = "pat"
    token_env: str = Field(min_length=1)


class Instance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    api: Literal["dc", "cloud"] = "dc"
    auth: Auth
    verify_tls: bool = True
    ca_bundle: str | None = None
    timeout_s: int = Field(default=30, gt=0)
    max_retries: int = Field(default=4, ge=0)

    @field_validator("api")
    @classmethod
    def _cloud_not_built(cls, v: str) -> str:
        if v == "cloud":
            raise ValueError("the cloud backend is not implemented (ADR-005)")
        return v


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    external_id_field: str = Field(min_length=1)
    holds: Literal["source_key", "shared_external_system"] = "source_key"
    match: Literal["exact", "regex"] = "exact"
    match_regex: str | None = None
    corroborate_with_summary: bool = True
    write_on_create: bool = True
    write_on_adopt: bool = False
    state_db: str = Field(min_length=1)

    @model_validator(mode="after")
    def _regex_present_and_valid(self) -> Identity:
        if self.match == "regex":
            if not self.match_regex:
                raise ValueError("match: regex requires match_regex")
            try:
                compiled = re.compile(self.match_regex)
            except re.error as exc:
                raise ValueError(f"match_regex is not a valid regex: {exc}") from None
            if "id" not in compiled.groupindex:
                raise ValueError("match_regex must contain a named group (?P<id>...)")
        elif self.match_regex:
            raise ValueError("match_regex is only used when match: regex")
        return self


class ScopeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_key: str = Field(min_length=1)
    jql: str = Field(min_length=1)

    @field_validator("jql")
    @classmethod
    def _deterministic(cls, v: str) -> str:
        fields = {
            (m.group("dq") or m.group("sq") or m.group("bare") or "").strip().lower()
            for m in _JQL_FIELD.finditer(v)
        }
        if "updated" in fields:
            raise ValueError(
                "scope JQL may not filter on `updated`; the exporter appends the watermark itself"
            )
        # The watermark is appended as `<scope> AND updated >= ...`, which lands
        # after an ORDER BY and produces JQL Jira will reject. Sorting a scope
        # also does nothing useful: the exporter pages the whole result set.
        if _JQL_ORDER_BY.search(_JQL_QUOTED.sub(" ", v)):
            raise ValueError(
                "scope JQL may not contain ORDER BY; the exporter appends the watermark "
                "after the scope, which would land after the sort clause"
            )
        # A function is only a function unquoted. Quoted, it is a string literal
        # and Jira would reject it for a date field anyway, so checking outside
        # quotes keeps a text search for the literal text usable.
        if _JQL_FUNCTION.search(_JQL_QUOTED.sub(" ", v)):
            raise ValueError(
                "scope JQL may not use now(), currentUser() or startOf/endOf functions; "
                "the result set must be the same on every run"
            )
        # A relative date is valid JQL quoted or bare, so this one sees everything.
        if _JQL_RELATIVE_LITERAL.search(v):
            raise ValueError(
                "scope JQL may not use a relative date such as -30d; "
                "the result set must be the same on every run"
            )
        return v


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    local: str | None = None
    export: bool = True
    # `import` is a keyword, so the attribute is import_ and the YAML key is aliased.
    import_: bool = Field(default=True, alias="import")
    on_conflict: OnConflict = "interactive"
    values: dict[str, str] | None = None
    skip: bool = False

    @model_validator(mode="after")
    def _local_unless_skipped(self) -> FieldMapping:
        if self.skip:
            if self.local is not None:
                raise ValueError("a skipped field must not name a local field")
            if self.export or self.import_:
                raise ValueError("a skipped field cannot be exported or imported")
        elif not self.local:
            raise ValueError("a mapped field must name a local field, or set skip: true")
        if self.values and len(set(self.values.values())) != len(self.values):
            raise ValueError("two local values map to the same canonical value")
        return self

    @property
    def travels(self) -> bool:
        return self.export or self.import_


class Scrub(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    forbidden_patterns: tuple[str, ...] = ()
    # Angle quotation marks, not < >, so the placeholder cannot be mistaken for
    # markup by anything downstream that renders the field.
    bare_url_placeholder: str = "‹link removed›"  # noqa: RUF001
    keep_anchor_text: bool = True
    remote_links: Literal["title_only", "drop"] = "title_only"

    @model_validator(mode="after")
    def _patterns_compile(self) -> Scrub:
        for pattern in self.forbidden_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"forbidden pattern {pattern!r} is not a valid regex: {exc}"
                ) from None
        if self.enabled and not self.forbidden_patterns:
            raise ValueError("scrub is enabled but declares no forbidden patterns")
        return self


class Matching(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fallback: Literal["summary", "none"] = "summary"
    normalize: tuple[str, ...] = ()
    require_same_issuetype: bool = True
    created_within_days: int = Field(default=30, ge=0)
    fuzzy_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    auto_bind: Literal["none", "exact"] = "none"

    @field_validator("normalize")
    @classmethod
    def _known_steps(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        known = {"lowercase", "collapse_ws", "strip_punct", "strip_key_prefix"}
        for step in v:
            if step not in known:
                raise ValueError(f"unknown normalise step {step!r}; known: {sorted(known)}")
        return v


class Users(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file: str = Field(min_length=1)
    missing_user: Literal["unassign_and_note", "fail", "park"] = "unassign_and_note"


class Toggle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    export: bool = True
    import_: bool = Field(default=True, alias="import")


class Attachments(Toggle):
    max_size_mb: int = Field(default=25, gt=0)


class Deletions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sync: bool = False


class InstanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    instance: Instance
    identity: Identity
    scope: dict[str, ScopeEntry]
    enforce_on_import: Literal["quarantine", "reject"] = "quarantine"
    quarantine_dir: str = "./quarantine"
    fields: dict[str, FieldMapping]
    statuses: dict[str, str]
    issue_types: dict[str, str]
    unmapped_field: Literal["warn", "skip", "park"] = "warn"
    park_into: str | None = None
    skew_tolerance: str = "2m"
    no_base_policy: Literal["seed_from_source", "interactive", "seed_from_destination"] = (
        "seed_from_source"
    )
    comments: Toggle = Toggle()
    attachments: Attachments = Attachments()
    deletions: Deletions = Deletions()
    scrub: Scrub
    matching: Matching = Matching()
    users: Users

    @model_validator(mode="after")
    def _check(self) -> InstanceConfig:
        if self.unmapped_field == "park" and not self.park_into:
            raise ValueError("unmapped_field: park requires park_into")
        if self.park_into and self.unmapped_field != "park":
            raise ValueError("park_into is only used when unmapped_field: park")
        if not self.scope:
            raise ValueError("at least one scope entry is required")
        _parse_duration(self.skew_tolerance)
        return self

    @property
    def skew(self) -> timedelta:
        return _parse_duration(self.skew_tolerance)


def validate_against_schema(
    config: InstanceConfig, schema: CanonicalSchema, *, path: Any = None
) -> None:
    """Cross-check an instance config against the shared canonical schema.

    A field that neither leaves nor enters this instance is a documented local
    exclusion and need not exist in the shared vocabulary. Anything that can
    travel must.
    """
    for name, mapping in config.fields.items():
        if mapping.travels and name not in schema.fields:
            raise ConfigError(
                f"field {name!r} is mapped and may travel, but is not declared in the "
                f"canonical schema; declare it there or set export and import to false",
                path=path,
            )
        canonical_field = schema.fields.get(name)
        if canonical_field and canonical_field.type == "enum" and mapping.values:
            declared_values = set(canonical_field.values or ())
            unknown_values = set(mapping.values.values()) - declared_values
            if unknown_values:
                raise ConfigError(
                    f"field {name!r} maps to canonical value(s) "
                    f"{sorted(unknown_values)} that the schema does not declare",
                    path=path,
                )
            # Importing denormalises canonical to local, so a canonical value with
            # no local counterpart cannot be applied. Catch it here rather than
            # against a bundle that has already crossed.
            if mapping.import_:
                unreachable = declared_values - set(mapping.values.values())
                if unreachable:
                    raise ConfigError(
                        f"field {name!r} is imported but canonical value(s) "
                        f"{sorted(unreachable)} have no local value to map to",
                        path=path,
                    )

    for declared_name in schema.fields:
        if declared_name not in config.fields:
            raise ConfigError(
                f"canonical field {declared_name!r} has no local mapping; map it or add "
                f"`{declared_name}: {{skip: true}}`",
                path=path,
            )

    for canonical_map, declared_names, label in (
        (config.statuses, schema.statuses, "status"),
        (config.issue_types, schema.issue_types, "issue type"),
    ):
        unknown = set(canonical_map) - set(declared_names)
        if unknown:
            raise ConfigError(
                f"{label} mapping names {sorted(unknown)}, which the canonical schema "
                f"does not declare",
                path=path,
            )
        missing = set(declared_names) - set(canonical_map)
        if missing:
            raise ConfigError(f"no local {label} mapped for {sorted(missing)}", path=path)
        # Export normalises local to canonical, so two canonical names sharing a
        # local one leaves that local value with no single canonical meaning.
        collisions = [local for local, n in Counter(canonical_map.values()).items() if n > 1]
        if collisions:
            raise ConfigError(
                f"local {label}(s) {sorted(collisions)} are mapped from more than one "
                f"canonical name, so they cannot be normalised back",
                path=path,
            )

    unknown_projects = set(config.scope) - set(schema.projects)
    if unknown_projects:
        raise ConfigError(
            f"scope names project(s) {sorted(unknown_projects)}, which the canonical "
            f"schema does not declare",
            path=path,
        )


def load_instance_config(path: str | Path, schema: CanonicalSchema | None = None) -> InstanceConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError("instance config not found", path=path) from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {exc}", path=path) from None
    if not isinstance(raw, dict):
        raise ConfigError("expected a mapping at the top level", path=path)
    try:
        config = InstanceConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc), path=path) from None
    if schema is not None:
        validate_against_schema(config, schema, path=path)
    return config
