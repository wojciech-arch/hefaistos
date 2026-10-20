from hefaistos.log import log


def test_field_named_event_does_not_collide(capsys):
    log("hook.selected", event="playing")
    assert '"event": "hook.selected"' in capsys.readouterr().out


def test_spotify_non_json_body_is_tolerated():
    from hefaistos.spotify import _parse

    assert _parse(b"") == {}
    assert _parse(b'{"a": 1}') == {"a": 1}
    assert "raw" in _parse(b"1x2")
