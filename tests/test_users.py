import pytest

from jirasync.errors import ConfigError
from jirasync.users import UserMap, load_user_map


def test_example_loads(users_path):
    users = load_user_map(users_path)
    assert users.key_on == "key"
    assert users.to_canonical("JIRAUSER10412") == "u_jdoe"
    assert users.to_local("u_jdoe") == "JIRAUSER10412"


def test_round_trips_through_json(users_path):
    users = load_user_map(users_path)
    assert UserMap.model_validate_json(users.model_dump_json()) == users


def test_unmapped_identities_still_render_a_display_name(users_path):
    users = load_user_map(users_path)
    assert users.display_name("u_rlaine") == "Riku Laine"
    assert users.to_local("u_rlaine") is None


def test_unknown_local_user_is_not_invented(users_path):
    assert load_user_map(users_path).to_canonical("JIRAUSER99999") is None


def test_key_on_key_requires_local_key(write_yaml):
    path = write_yaml(
        "users.yaml",
        {"key_on": "key", "users": [{"canonical": "u_a", "local_name": "a", "display": "A"}]},
    )
    with pytest.raises(ConfigError, match="has no local_key"):
        load_user_map(path)


def test_key_on_name_requires_local_name(write_yaml):
    path = write_yaml(
        "users.yaml",
        {"key_on": "name", "users": [{"canonical": "u_a", "local_key": "K1", "display": "A"}]},
    )
    with pytest.raises(ConfigError, match="has no local_name"):
        load_user_map(path)


def test_duplicate_canonical_id_is_rejected(write_yaml):
    path = write_yaml(
        "users.yaml",
        {
            "key_on": "key",
            "users": [
                {"canonical": "u_a", "local_key": "K1", "display": "A"},
                {"canonical": "u_a", "local_key": "K2", "display": "A again"},
            ],
        },
    )
    with pytest.raises(ConfigError, match="appears more than once"):
        load_user_map(path)


def test_canonical_id_cannot_be_both_mapped_and_unmapped(write_yaml):
    path = write_yaml(
        "users.yaml",
        {
            "key_on": "key",
            "users": [{"canonical": "u_a", "local_key": "K1", "display": "A"}],
            "unmapped": [{"canonical": "u_a", "display": "A"}],
        },
    )
    with pytest.raises(ConfigError, match="appears more than once"):
        load_user_map(path)


def test_two_canonical_ids_cannot_share_a_local_user(write_yaml):
    path = write_yaml(
        "users.yaml",
        {
            "key_on": "key",
            "users": [
                {"canonical": "u_a", "local_key": "K1", "display": "A"},
                {"canonical": "u_b", "local_key": "K1", "display": "B"},
            ],
        },
    )
    with pytest.raises(ConfigError, match="more than one canonical id"):
        load_user_map(path)
