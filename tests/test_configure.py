import pytest

from hefaistos.configure import edit_target, parse_speakers, problems, slug

PLAYERS = {11: "Den", 22: "Living", 33: "Kids"}


def test_slug_makes_a_stable_target_id():
    assert slug("No Kid") == "no-kid"
    assert slug("Leże + Den") == "le-e-den"
    assert slug("!!!") == "target"


def test_speakers_are_picked_by_number_leader_first():
    assert parse_speakers("2 1", [11, 22, 33]) == [22, 11]
    assert parse_speakers("3,1", [11, 22, 33]) == [33, 11]


@pytest.mark.parametrize("text, error", [("4", "between 1 and 3"), ("x", "not a speaker"), ("1 1", "twice")])
def test_bad_speaker_input_says_what_is_wrong(text, error):
    with pytest.raises(ValueError, match=error):
        parse_speakers(text, [11, 22, 33])


def test_a_valid_config_has_no_problems():
    targets = {"all": {"name": "All", "leader": 22, "members": [11, 33]},
               "quiet": {"name": "Quiet", "leader": 22, "members": [11]}}
    assert problems(targets, PLAYERS) == []


def test_problems_are_reported_with_the_fix():
    targets = {"a": {"name": "All", "leader": 22, "members": [11]},
               "b": {"name": "All", "leader": 11, "members": [22]},
               "c": {"name": "Solo", "leader": 33, "members": []},
               "d": {"name": "Gone", "leader": 99, "members": [11]}}
    found = "\n".join(problems(targets, PLAYERS))
    assert "unique names" in found
    assert "same speakers as 'All'" in found
    assert "at least 2 speakers" in found
    assert "unknown player ids [99]" in found


def test_editing_keeps_strategy_and_preset(monkeypatch):
    answers = iter(["No Kid", "2 1"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    old = {"name": "No Kid", "leader": 22, "members": [11], "strategy": "switch", "preset": "ec49"}
    new = edit_target(old, PLAYERS, [11, 22, 33])
    assert new == {"name": "No Kid", "leader": 22, "members": [11], "strategy": "switch", "preset": "ec49"}
