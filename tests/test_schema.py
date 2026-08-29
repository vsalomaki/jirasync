import pytest

from jirasync.errors import ConfigError
from jirasync.schema import CanonicalSchema, load_canonical_schema


def test_example_schema_loads(schema_path):
    schema = load_canonical_schema(schema_path)
    assert schema.schema_version >= 1
    assert "summary" in schema.fields


def test_round_trips_through_json(schema_path):
    schema = load_canonical_schema(schema_path)
    assert CanonicalSchema.model_validate_json(schema.model_dump_json()) == schema


def _minimal(**over):
    base = {
        "schema_version": 1,
        "projects": ["platform"],
        "issue_types": ["bug"],
        "statuses": ["open"],
        "fields": {"summary": {"type": "text"}},
    }
    base.update(over)
    return base


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_minimal(fields={"severity": {"type": "enum"}}), "must declare its values"),
        (
            _minimal(fields={"summary": {"type": "text", "values": ["a"]}}),
            "only meaningful for an enum",
        ),
        (_minimal(projects=["a", "a"]), "duplicate entry in projects"),
        (_minimal(fields={}), "at least one field"),
        (_minimal(field_groups=[["summary", "nope"]]), "not a declared field"),
        (_minimal(field_groups=[["summary"]]), "at least two fields"),
        (_minimal(field_groups=[["summary", "summary"]]), "repeats a field"),
        (_minimal(schema_version=0), "greater than or equal to 1"),
    ],
)
def test_rejects_with_a_clear_message(write_yaml, data, message):
    path = write_yaml("canonical-schema.yaml", data)
    with pytest.raises(ConfigError, match=message):
        load_canonical_schema(path)


def test_status_cannot_be_grouped(write_yaml):
    """`status` is a top-level issue property, not a field, so it cannot be grouped."""
    path = write_yaml("canonical-schema.yaml", _minimal(field_groups=[["status", "summary"]]))
    with pytest.raises(ConfigError, match=r"'status'.*not a declared field"):
        load_canonical_schema(path)


def test_missing_file_names_the_path(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_canonical_schema(tmp_path / "absent.yaml")
