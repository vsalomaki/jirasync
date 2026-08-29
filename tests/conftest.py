from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def schema_path() -> Path:
    return REPO / "canonical-schema.example.yaml"


@pytest.fixture
def instance_path() -> Path:
    return REPO / "config" / "instance.example.yaml"


@pytest.fixture
def top_level_path() -> Path:
    return REPO / "config" / "jirasync.example.yaml"


@pytest.fixture
def users_path() -> Path:
    return REPO / "config" / "users.example.yaml"


@pytest.fixture
def write_yaml(tmp_path: Path):
    """Write a dict to a temp YAML file and return its path."""

    def _write(name: str, data: object) -> Path:
        path = tmp_path / name
        path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def mutate(write_yaml):
    """Load a YAML file, apply a mutation, and write it back out to tmp."""

    def _mutate(source: Path, name: str, change):
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
        change(data)
        return write_yaml(name, data)

    return _mutate
