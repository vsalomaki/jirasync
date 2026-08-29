import pytest

from jirasync.config import Deployment, TopLevelConfig, load_deployment, load_top_level_config
from jirasync.errors import ConfigError, RoleError

REPO_RELATIVE = {"root": "."}


def test_example_loads_as_a_source_only_split(top_level_path):
    config = load_top_level_config(top_level_path)
    assert config.mode == "split"
    assert config.roles == frozenset({"source"})


def test_round_trips_through_json(top_level_path):
    config = load_top_level_config(top_level_path)
    assert TopLevelConfig.model_validate_json(config.model_dump_json()) == config


def _top(**over):
    base = {
        "mode": "split",
        "source": "./config/instance.example.yaml",
        "canonical_schema": "./canonical-schema.example.yaml",
        "transport": {"kind": "file", "outbox": "./out", "inbox": "./in"},
    }
    base.update(over)
    return base


def test_split_naming_both_ends_is_rejected(write_yaml):
    """This is the check that keeps a split deployment off the far end's credentials."""
    path = write_yaml("jirasync.yaml", _top(destination="./config/other.yaml"))
    with pytest.raises(ConfigError, match="names exactly one of source or destination"):
        load_top_level_config(path)


def test_split_naming_neither_end_is_rejected(write_yaml):
    data = _top()
    del data["source"]
    path = write_yaml("jirasync.yaml", data)
    with pytest.raises(ConfigError, match="names exactly one"):
        load_top_level_config(path)


def test_direct_naming_one_end_is_rejected(write_yaml):
    path = write_yaml("jirasync.yaml", _top(mode="direct"))
    with pytest.raises(ConfigError, match="names both source and destination"):
        load_top_level_config(path)


def test_same_file_as_both_ends_is_rejected(write_yaml):
    path = write_yaml(
        "jirasync.yaml",
        _top(mode="direct", destination="./config/instance.example.yaml"),
    )
    with pytest.raises(ConfigError, match="same instance file"):
        load_top_level_config(path)


def test_https_transport_is_not_implemented(write_yaml):
    path = write_yaml(
        "jirasync.yaml", _top(transport={"kind": "https", "outbox": "o", "inbox": "i"})
    )
    with pytest.raises(ConfigError, match="not implemented"):
        load_top_level_config(path)


@pytest.mark.parametrize("command", ["export", "normalize"])
def test_source_may_run_source_commands(write_yaml, command):
    config = load_top_level_config(write_yaml("jirasync.yaml", _top()))
    config.require(command)


@pytest.mark.parametrize("command", ["plan", "resolve", "apply", "adopt"])
def test_source_refuses_destination_commands(write_yaml, command):
    config = load_top_level_config(write_yaml("jirasync.yaml", _top()))
    with pytest.raises(RoleError, match=f"cannot run '{command}'"):
        config.require(command)


@pytest.mark.parametrize("command", ["export", "normalize"])
def test_destination_refuses_source_commands(write_yaml, command):
    data = _top()
    del data["source"]
    data["destination"] = "./config/instance.example.yaml"
    config = load_top_level_config(write_yaml("jirasync.yaml", data))
    with pytest.raises(RoleError, match=f"cannot run '{command}'"):
        config.require(command)


def test_doctor_runs_in_either_role(write_yaml):
    config = load_top_level_config(write_yaml("jirasync.yaml", _top()))
    config.require("doctor")


def test_unknown_command_is_a_programming_error(write_yaml):
    config = load_top_level_config(write_yaml("jirasync.yaml", _top()))
    with pytest.raises(ValueError, match="unknown command"):
        config.permits("frobnicate")


def test_deployment_resolves_everything_the_config_names(write_yaml, tmp_path):
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    path = write_yaml("jirasync.yaml", _top())
    deployment = load_deployment(path, root=repo)
    assert deployment.source is not None
    assert deployment.destination is None
    assert deployment.schema_.schema_version >= 1
    deployment.require("export")


def test_direct_deployment_rejects_two_configs_with_the_same_instance_id(write_yaml, tmp_path):
    from pathlib import Path

    import yaml

    repo = Path(__file__).resolve().parent.parent
    original = yaml.safe_load((repo / "config" / "instance.example.yaml").read_text())
    twin = tmp_path / "twin.yaml"
    twin.write_text(yaml.safe_dump(original, allow_unicode=True), encoding="utf-8")

    path = write_yaml(
        "jirasync.yaml",
        _top(mode="direct", destination=str(twin)),
    )
    with pytest.raises(ConfigError, match="same instance id"):
        load_deployment(path, root=repo)


def test_deployment_round_trips_through_its_own_json(write_yaml):
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    deployment = load_deployment(write_yaml("jirasync.yaml", _top()), root=repo)
    restored = Deployment.model_validate_json(deployment.model_dump_json())
    assert restored == deployment
