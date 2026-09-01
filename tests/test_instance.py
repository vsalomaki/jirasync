import pytest

from jirasync.errors import ConfigError
from jirasync.instance import InstanceConfig, load_instance_config
from jirasync.schema import load_canonical_schema


def test_example_config_loads_against_the_example_schema(instance_path, schema_path):
    config = load_instance_config(instance_path, load_canonical_schema(schema_path))
    assert config.instance.id == "beta"
    assert config.skew.total_seconds() == 120


def test_round_trips_through_json(instance_path):
    config = load_instance_config(instance_path)
    assert InstanceConfig.model_validate_json(config.model_dump_json(by_alias=True)) == config


@pytest.mark.parametrize(
    "jql",
    [
        "project = PF AND updated >= -1d",
        'project = PF AND "updated" >= "2026-01-01"',
        "project = PF AND UPDATED >= x",
        "project = PF AND created >= -30d",
        'project = PF AND created >= "-30d"',
        "project = PF AND created >= startOfDay()",
        "project = PF AND created >= StartOfDay()",
        "project = PF AND created >= endOfMonth()",
        "project = PF AND created >= now()",
        "project = PF AND created >= NOW()",
        "project = PF AND reporter = currentUser()",
        "project = PF AND reporter = CurrentUser()",
        "project = PF AND reporter = currentLogin()",
        # Multiword operators: missing one stops the field being checked at all.
        'project = PF AND updated NOT IN ("2026-01-01")',
        'project = PF AND "updated" NOT IN ("x")',
        "project = PF AND updated IS NOT EMPTY",
        'project = PF AND updated WAS NOT IN ("x")',
        "project = PF AND updated CHANGED",
    ],
)
def test_scope_jql_must_be_deterministic(mutate, instance_path, jql):
    """JQL keywords are case insensitive, so the checks have to be too.

    A scope that moves on its own is invisible until someone notices issues
    have silently entered or left it.
    """
    path = mutate(instance_path, "instance.yaml", lambda d: d["scope"]["platform"].update(jql=jql))
    with pytest.raises(ConfigError, match="scope JQL"):
        load_instance_config(path)


@pytest.mark.parametrize(
    "jql",
    [
        "project = PF AND labels = airgap-sync",
        'project = PF AND "Sync?" = Yes',
        'project = PF AND "last updated by" = jdoe',
        'project = PF AND summary ~ "updated"',
        'project = PF AND description ~ "currentUser()"',
        'project = PF AND summary ~ "fix-30d"',
        "project = PF AND status NOT IN (Done, Closed)",
        "project = PF AND assignee IS NOT EMPTY",
        'project = PF AND summary ~ "order by updated"',
    ],
)
def test_deterministic_scope_jql_is_accepted(mutate, instance_path, jql):
    """Rejecting legitimate JQL pushes operators toward broader scopes."""
    path = mutate(instance_path, "instance.yaml", lambda d: d["scope"]["platform"].update(jql=jql))
    load_instance_config(path)


def test_field_that_can_travel_must_be_in_the_schema(mutate, instance_path, schema_path):
    path = mutate(
        instance_path,
        "instance.yaml",
        lambda d: d["fields"].update(mystery={"local": "customfield_1", "export": True}),
    )
    with pytest.raises(ConfigError, match=r"'mystery'.*not declared in the canonical schema"):
        load_instance_config(path, load_canonical_schema(schema_path))


def test_local_only_field_need_not_be_in_the_schema(instance_path, schema_path):
    """internal_notes never leaves, so it is a documented exclusion, not vocabulary."""
    config = load_instance_config(instance_path, load_canonical_schema(schema_path))
    assert config.fields["internal_notes"].travels is False


def test_canonical_field_must_be_mapped_or_skipped(mutate, instance_path, schema_path):
    path = mutate(instance_path, "instance.yaml", lambda d: d["fields"].pop("severity"))
    with pytest.raises(ConfigError, match="'severity' has no local mapping"):
        load_instance_config(path, load_canonical_schema(schema_path))


def test_skip_satisfies_the_mapping_requirement(mutate, instance_path, schema_path):
    path = mutate(
        instance_path,
        "instance.yaml",
        lambda d: d["fields"].update(severity={"skip": True, "export": False, "import": False}),
    )
    config = load_instance_config(path, load_canonical_schema(schema_path))
    assert config.fields["severity"].skip is True


def test_value_map_must_use_declared_canonical_values(mutate, instance_path, schema_path):
    path = mutate(
        instance_path,
        "instance.yaml",
        lambda d: d["fields"]["severity"]["values"].update(Critical="catastrophic"),
    )
    with pytest.raises(ConfigError, match="catastrophic"):
        load_instance_config(path, load_canonical_schema(schema_path))


def test_regex_matching_requires_a_named_id_group(mutate, instance_path):
    path = mutate(instance_path, "instance.yaml", lambda d: d["identity"].update(match="regex"))
    with pytest.raises(ConfigError, match="requires match_regex"):
        load_instance_config(path)

    path = mutate(
        instance_path,
        "instance2.yaml",
        lambda d: d["identity"].update(match="regex", match_regex=r"[A-Z]+-\d+"),
    )
    with pytest.raises(ConfigError, match=r"named group"):
        load_instance_config(path)


def test_park_requires_a_target(mutate, instance_path):
    path = mutate(instance_path, "instance.yaml", lambda d: d.update(unmapped_field="park"))
    with pytest.raises(ConfigError, match="requires park_into"):
        load_instance_config(path)


def test_scrub_enabled_without_patterns_is_rejected(mutate, instance_path):
    path = mutate(
        instance_path, "instance.yaml", lambda d: d["scrub"].update(forbidden_patterns=[])
    )
    with pytest.raises(ConfigError, match="no forbidden patterns"):
        load_instance_config(path)


def test_unknown_key_is_rejected(mutate, instance_path):
    path = mutate(instance_path, "instance.yaml", lambda d: d.update(typo_here=1))
    with pytest.raises(ConfigError, match="typo_here"):
        load_instance_config(path)


def test_cloud_backend_is_not_implemented(mutate, instance_path):
    path = mutate(instance_path, "instance.yaml", lambda d: d["instance"].update(api="cloud"))
    with pytest.raises(ConfigError, match="not implemented"):
        load_instance_config(path)


def test_imported_enum_must_reach_every_canonical_value(mutate, instance_path, schema_path):
    """Importing denormalises canonical to local, so an unmapped canonical value
    cannot be applied. Catch it here, not against a bundle that already crossed."""
    path = mutate(
        instance_path, "instance.yaml", lambda d: d["fields"]["severity"]["values"].pop("Low")
    )
    with pytest.raises(ConfigError, match=r"canonical value\(s\) \['low'\] have no local value"):
        load_instance_config(path, load_canonical_schema(schema_path))


def test_export_only_enum_need_not_cover_every_canonical_value(mutate, instance_path, schema_path):
    def strip(d):
        d["fields"]["severity"]["values"].pop("Low")
        d["fields"]["severity"]["import"] = False

    path = mutate(instance_path, "instance.yaml", strip)
    load_instance_config(path, load_canonical_schema(schema_path))


@pytest.mark.parametrize(
    ("key", "canonical", "collide"),
    [("statuses", "done", "To Do"), ("issue_types", "task", "Bug")],
)
def test_two_canonical_names_cannot_share_one_local(
    mutate, instance_path, schema_path, key, canonical, collide
):
    """Export normalises local to canonical, so a shared local has no single meaning."""
    path = mutate(instance_path, "instance.yaml", lambda d: d[key].update({canonical: collide}))
    with pytest.raises(ConfigError, match="mapped from more than one canonical name"):
        load_instance_config(path, load_canonical_schema(schema_path))


@pytest.mark.parametrize(
    "jql",
    [
        "project = PF ORDER BY created",
        "project = PF ORDER BY updated DESC",
        "project = PF order by created, updated",
    ],
)
def test_scope_jql_may_not_sort(mutate, instance_path, jql):
    """The watermark is appended after the scope, so it would land after the sort
    clause and produce JQL Jira rejects."""
    path = mutate(instance_path, "instance.yaml", lambda d: d["scope"]["platform"].update(jql=jql))
    with pytest.raises(ConfigError, match="may not contain ORDER BY"):
        load_instance_config(path)


def test_toggle_accepts_the_field_name_as_well_as_the_alias():
    """FieldMapping accepts import_, so the toggles must too or the alias is a trap."""
    from jirasync.instance import Attachments, Toggle

    assert Toggle(import_=False).import_ is False
    assert Attachments(import_=False).import_ is False
    assert Toggle.model_validate({"import": False}).import_ is False


@pytest.mark.parametrize(
    ("unset_value", "external_id", "issue_key", "expected"),
    [
        # Blank always means unpaired, whichever sentinel is configured.
        ("blank", None, "TOOL-88", True),
        ("blank", "", "TOOL-88", True),
        ("blank", "   ", "TOOL-88", True),
        ("self_key", None, "TOOL-88", True),
        # A real pairing is never unset.
        ("blank", "PF-45", "TOOL-88", False),
        ("self_key", "PF-45", "TOOL-88", False),
        # The observed default: an unpaired issue pointing at itself.
        ("self_key", "TOOL-88", "TOOL-88", True),
        ("self_key", " TOOL-88 ", "TOOL-88", True),
        # The same value is a genuine pairing when the sentinel is not in use.
        ("blank", "TOOL-88", "TOOL-88", False),
    ],
)
def test_unset_external_id_depends_on_the_configured_sentinel(
    mutate, instance_path, unset_value, external_id, issue_key, expected
):
    from jirasync.instance import is_unset_external_id

    path = mutate(
        instance_path, "instance.yaml", lambda d: d["identity"].update(unset_value=unset_value)
    )
    config = load_instance_config(path)
    assert is_unset_external_id(config, external_id, issue_key) is expected
