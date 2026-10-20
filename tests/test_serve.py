import pytest

from hefaistos.__main__ import parse_config
from hefaistos.serve import MAX_RESTARTS, librespot_cmd, too_many_restarts, zeroconf_ports


def cfg(**targets):
    return {"heos_host": "192.0.2.10", "targets": targets}


def test_target_name_is_what_spotify_shows():
    _, targets = parse_config(cfg(**{"no-kid": {"name": "No Kid", "leader": 1, "members": [2]}}))
    assert librespot_cmd(targets["no-kid"], 50100)[-2:] == ["--name", "No Kid"]


def test_name_defaults_to_target_id():
    _, targets = parse_config(cfg(all={"leader": 1, "members": [2, 3]}))
    assert targets["all"].label == "all"


def test_duplicate_names_are_rejected():
    with pytest.raises(SystemExit, match="unique"):
        parse_config(cfg(a={"name": "All", "leader": 1, "members": []}, b={"name": "All", "leader": 2, "members": []}))


def test_each_target_keeps_a_fixed_port_in_config_order():
    _, targets = parse_config(cfg(all={"leader": 1, "members": [2]}, quiet={"leader": 2, "members": []}))
    assert zeroconf_ports(targets) == {"all": 50100, "quiet": 50101}


def test_released_endpoints_restart_until_they_flap():
    history: list[float] = []
    assert not any(too_many_restarts(history, float(i)) for i in range(MAX_RESTARTS))
    assert too_many_restarts(history, float(MAX_RESTARTS))


def test_old_restarts_fall_out_of_the_window():
    history = [0.0] * MAX_RESTARTS
    assert not too_many_restarts(history, 1000.0)
