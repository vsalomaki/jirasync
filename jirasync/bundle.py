"""Transport formats.

The raw dump never leaves the originating side; only the bundle travels to the
peer. Identity is the source key, so no jirasync-invented identifier appears
anywhere here (ADR-021).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMAT_VERSION = 1


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance: str = Field(min_length=1)
    key: str = Field(min_length=1)


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Any = None
    changed_at: datetime
    changed_by: str | None = None
    # True when changed_at fell back to issue.created because the field never
    # appeared in the changelog. Excluded from `take newer` by default.
    inferred: bool = False


class Comment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    body: str
    author: str | None = None
    created: datetime
    updated: datetime


class Attachment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    author: str | None = None
    created: datetime


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: str = Field(min_length=1)
    # Plain key text, never rewritten to a destination key and never a URL.
    target_text: str = Field(min_length=1)


class CanonicalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceRef
    source_external_id: str | None = None
    issue_type: str = Field(min_length=1)
    project: str = Field(min_length=1)
    scope_exit: bool = False
    fields: dict[str, FieldValue] = Field(default_factory=dict)
    status: str | None = None
    comments: tuple[Comment, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    links: tuple[Link, ...] = ()

    @model_validator(mode="after")
    def _comment_ids_unique(self) -> CanonicalIssue:
        ids = [c.source_id for c in self.comments]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate comment source_id")
        return self


class BundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["bundle"] = "bundle"
    schema_version: int = Field(ge=1)
    format_version: int = FORMAT_VERSION
    instance: str = Field(min_length=1)
    exported_at: datetime
    server_time: datetime
    watermark_from: datetime | None = None
    watermark_to: datetime
    projects: tuple[str, ...]
    issue_count: int = Field(ge=0)
    # Monotonic per source instance. The destination refuses a bundle at or
    # below the last applied sequence, and one that skips ahead. See ADR-022.
    seq: int = Field(ge=0)

    @model_validator(mode="after")
    def _window_ordered(self) -> BundleManifest:
        if self.watermark_from and self.watermark_from > self.watermark_to:
            raise ValueError("watermark_from is later than watermark_to")
        return self


class BackendInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    api_version: str = Field(min_length=1)
    jira_version: str = Field(min_length=1)


class RawManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["raw"] = "raw"
    instance: str = Field(min_length=1)
    backend: BackendInfo
    exported_at: datetime
    server_time: datetime
    watermark_from: datetime | None = None
    watermark_to: datetime
    scope_hash: str = Field(min_length=1)
    issue_count: int = Field(ge=0)
