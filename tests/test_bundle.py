from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jirasync.bundle import (
    Attachment,
    BundleManifest,
    CanonicalIssue,
    Comment,
    FieldValue,
    Link,
    RawManifest,
)

NOW = datetime(2026, 8, 27, 10, 30, tzinfo=UTC)
SHA = "9f2c" + "0" * 60


def an_issue(**over):
    base = {
        "source": {"instance": "alpha", "key": "PF-45"},
        "issue_type": "bug",
        "project": "platform",
        "fields": {"summary": FieldValue(value="Retry drops the last attempt", changed_at=NOW)},
        "status": "in_progress",
        "comments": (Comment(source_id="10432", body="Reproduced", created=NOW, updated=NOW),),
        "attachments": (Attachment(filename="trace.log", sha256=SHA, size=88213, created=NOW),),
        "links": (Link(type="blocks", target_text="PF-12"),),
    }
    base.update(over)
    return CanonicalIssue.model_validate(base)


@pytest.mark.parametrize(
    "model",
    [
        an_issue(),
        FieldValue(value="x", changed_at=NOW, inferred=True),
        Comment(source_id="1", body="b", created=NOW, updated=NOW),
        Attachment(filename="f", sha256=SHA, size=0, created=NOW),
        Link(type="blocks", target_text="PF-1"),
        BundleManifest(
            schema_version=1,
            instance="alpha",
            exported_at=NOW,
            server_time=NOW,
            watermark_to=NOW,
            projects=("platform",),
            issue_count=1,
            seq=47,
        ),
        RawManifest(
            instance="alpha",
            backend={"id": "dc", "api_version": "2", "jira_version": "9.12.4"},
            exported_at=NOW,
            server_time=NOW,
            watermark_to=NOW,
            scope_hash="sha256:abc",
            issue_count=1,
        ),
    ],
)
def test_every_model_round_trips_through_json(model):
    assert type(model).model_validate_json(model.model_dump_json()) == model


def test_identity_is_the_source_key_with_no_invented_id():
    """There is no sync_id; an extra identifier must be refused, not ignored."""
    with pytest.raises(ValidationError, match="sync_id"):
        an_issue(sync_id="8f3c1e2a")


def test_source_external_id_defaults_to_absent():
    assert an_issue().source_external_id is None


def test_duplicate_comment_ids_are_rejected():
    with pytest.raises(ValidationError, match="duplicate comment source_id"):
        an_issue(
            comments=(
                Comment(source_id="1", body="a", created=NOW, updated=NOW),
                Comment(source_id="1", body="b", created=NOW, updated=NOW),
            )
        )


def test_attachment_hash_must_be_a_sha256():
    with pytest.raises(ValidationError):
        Attachment(filename="f", sha256="not-a-hash", size=1, created=NOW)


def test_manifest_window_must_be_ordered():
    with pytest.raises(ValidationError, match="later than watermark_to"):
        BundleManifest(
            schema_version=1,
            instance="alpha",
            exported_at=NOW,
            server_time=NOW,
            watermark_from=datetime(2026, 9, 1, tzinfo=UTC),
            watermark_to=NOW,
            projects=("platform",),
            issue_count=0,
            seq=1,
        )


def test_sequence_is_required_so_ordering_can_be_enforced():
    with pytest.raises(ValidationError, match="seq"):
        BundleManifest(
            schema_version=1,
            instance="alpha",
            exported_at=NOW,
            server_time=NOW,
            watermark_to=NOW,
            projects=("platform",),
            issue_count=0,
        )
