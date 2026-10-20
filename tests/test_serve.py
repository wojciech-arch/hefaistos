import pytest

from hefaistos.__main__ import parse_config
from hefaistos.groups import Group
from hefaistos.serve import MAX_RESTARTS, SWITCH_HIDE_S, switching, librespot_cmd, too_many_restarts, visible_targets, zeroconf_ports


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


TARGETS = parse_config(cfg(**{"all": {"leader": 1, "members": [2, 3]}, "no-kid": {"leader": 1, "members": [2]}}))[1]


def test_every_target_is_offered_without_groups():
    assert visible_targets(TARGETS, []) == {"all", "no-kid"}


def test_a_formed_target_is_hidden_and_the_others_stay():
    assert visible_targets(TARGETS, [Group("Living + Den", 1, (2,))]) == {"all"}


def test_reshaping_to_another_target_swaps_which_one_is_hidden():
    assert visible_targets(TARGETS, [Group("Living + Den + Kids", 1, (2, 3))]) == {"no-kid"}


def test_a_hand_made_group_with_the_same_speakers_also_hides_the_target():
    assert visible_targets(TARGETS, [Group("Den + Living", 2, (1,))]) == {"all"}


def test_an_unrelated_group_hides_nothing():
    assert visible_targets(TARGETS, [Group("Den + Kids", 2, (3,))]) == {"all", "no-kid"}


def test_a_target_can_name_a_heos_preset():
    _, targets = parse_config(cfg(**{"no-kid": {"name": "No Kid", "preset": "ec49", "leader": 1, "members": [2]}}))
    assert targets["no-kid"].preset == "ec49"


def test_targets_without_a_preset_are_built_by_hefaistos():
    _, targets = parse_config(cfg(all={"leader": 1, "members": [2, 3]}))
    assert targets["all"].preset == ""


def test_a_picked_target_stays_hidden_while_heos_regroups():
    assert switching(100.0, 100.0 + SWITCH_HIDE_S - 1)


def test_the_switch_window_expires():
    assert not switching(100.0, 100.0 + SWITCH_HIDE_S + 1)
    assert not switching(None, 100.0)
