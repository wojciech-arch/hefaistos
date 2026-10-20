import pytest

from hefaistos.__main__ import parse_config
from hefaistos.serve import librespot_cmd


def cfg(**targets):
    return {"heos_host": "192.0.2.10", "targets": targets}


def test_target_name_is_what_spotify_shows():
    _, targets = parse_config(cfg(**{"no-kid": {"name": "No Kid", "leader": 1, "members": [2]}}))
    assert librespot_cmd(targets["no-kid"])[-2:] == ["--name", "No Kid"]


def test_name_defaults_to_target_id():
    _, targets = parse_config(cfg(all={"leader": 1, "members": [2, 3]}))
    assert targets["all"].label == "all"


def test_duplicate_names_are_rejected():
    with pytest.raises(SystemExit, match="unique"):
        parse_config(cfg(a={"name": "All", "leader": 1, "members": []}, b={"name": "All", "leader": 2, "members": []}))
