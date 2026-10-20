from hefaistos.log import log


def test_field_named_event_does_not_collide(capsys):
    log("hook.selected", event="playing")
    assert '"event": "hook.selected"' in capsys.readouterr().out

