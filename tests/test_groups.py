from hefaistos.groups import Group, Target, plan_group, plan_rollback, plan_ungroup, takeover_pids

LIVING, DEN, KIDS, OTHER = 1001, 1002, 1003, 555
ALL = Target("all", LIVING, (DEN, KIDS))
NO_KID = Target("no-kid", LIVING, (DEN,))
TARGETS = [ALL, NO_KID]


def group(leader, *members, name="g"):
    return Group(name=name, leader=leader, members=tuple(members))


def test_no_groups_creates_target():
    assert plan_group(NO_KID, []) == [[LIVING, DEN]]


def test_target_already_formed_is_noop():
    assert plan_group(ALL, [group(LIVING, DEN, KIDS, name="user group")]) == []


def test_member_order_does_not_matter():
    assert plan_group(ALL, [group(LIVING, KIDS, DEN)]) == []


def test_takeover_of_other_known_composition_reshapes_with_same_leader():
    assert plan_group(NO_KID, [group(LIVING, DEN, KIDS, name="user group")]) == [[LIVING, DEN]]


def test_known_composition_with_other_leader_is_ungrouped_first():
    plan = plan_group(NO_KID, [group(DEN, LIVING)])
    assert plan == [[LIVING, DEN]] or plan == [[DEN], [LIVING, DEN]]


def test_hand_made_group_holding_a_target_speaker_is_dissolved():
    assert plan_group(NO_KID, [group(DEN, OTHER, name="hand made")]) == [[DEN], [LIVING, DEN]]


def test_hand_made_group_led_by_target_leader_is_reshaped():
    assert plan_group(ALL, [group(LIVING, KIDS, name="hand made")]) == [[LIVING, DEN, KIDS]]


def test_foreign_group_not_touching_target_is_ignored():
    assert plan_group(NO_KID, [group(KIDS, OTHER)]) == [[LIVING, DEN]]


def test_ungroup_known_composition():
    assert plan_ungroup([group(LIVING, DEN, KIDS)], TARGETS) == [[LIVING]]


def test_ungroup_leaves_foreign_groups_alone():
    assert plan_ungroup([group(KIDS, OTHER)], TARGETS) == []


def test_rollback_dissolves_partial_group_led_by_target_leader():
    assert plan_rollback(ALL, [group(LIVING, KIDS)]) == [[LIVING]]


def test_rollback_leaves_complete_or_foreign_groups():
    assert plan_rollback(ALL, [group(LIVING, DEN, KIDS)]) == []
    assert plan_rollback(NO_KID, [group(LIVING, OTHER)]) == []
    assert plan_rollback(NO_KID, [group(DEN, KIDS)]) == []


def test_playing_target_speakers_are_taken_over():
    playing = {LIVING: True, DEN: True, KIDS: False}
    assert takeover_pids(ALL, playing) == [LIVING, DEN]


def test_speakers_outside_the_target_are_never_stopped():
    assert takeover_pids(NO_KID, {LIVING: False, DEN: False, KIDS: True}) == []
