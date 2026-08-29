import pytest

from jirasync.config import load_top_level_config
from jirasync.errors import ConfigError
from jirasync.instance import load_instance_config
from jirasync.schema import load_canonical_schema
from jirasync.users import load_user_map

LOADERS = [load_canonical_schema, load_instance_config, load_top_level_config, load_user_map]


@pytest.mark.parametrize("loader", LOADERS)
def test_missing_file_names_the_path(loader, tmp_path):
    missing = tmp_path / "absent.yaml"
    with pytest.raises(ConfigError, match="not found") as caught:
        loader(missing)
    assert "absent.yaml" in str(caught.value)


@pytest.mark.parametrize("loader", LOADERS)
def test_unparseable_yaml_names_the_path(loader, tmp_path):
    broken = tmp_path / "broken.yaml"
    broken.write_text("key: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML") as caught:
        loader(broken)
    assert "broken.yaml" in str(caught.value)


@pytest.mark.parametrize("loader", LOADERS)
def test_a_yaml_list_is_not_a_config(loader, tmp_path):
    listy = tmp_path / "list.yaml"
    listy.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="expected a mapping"):
        loader(listy)
