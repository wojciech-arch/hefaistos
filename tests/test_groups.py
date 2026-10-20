import pytest

from hefaistos.groups import Group, GroupConflict, Target, plan_group, plan_rollback, plan_ungroup, takeover_pids

LIVING, DEN, KIDS, OTHER = 1001, 1002, 1003, 555
ALL = Target("all", LIVING, (DEN, KIDS))
NO_KID = Target("no-kid", LIVING, (DEN,))
TARGETS = [ALL, NO_KID]


def group(leader, *members, name="g"):
    return Group(name=name, leader=leader, members=tuple(members))


def test_no_groups_creates_target():
    assert plan_group(NO_KID, [], TARGETS) == [[LIVING, DEN]]


def test_target_already_formed_is_noop():
    assert plan_group(ALL, [group(LIVING, DEN, KIDS, name="user group")], TARGETS) == []


def test_member_order_does_not_matter():
    assert plan_group(ALL, [group(LIVING, KIDS, DEN)], TARGETS) == []


def test_takeover_of_other_known_composition_reshapes_with_same_leader():
    assert plan_group(NO_KID, [group(LIVING, DEN, KIDS, name="user group")], TARGETS) == [[LIVING, DEN]]


def test_known_composition_with_other_leader_is_ungrouped_first():
    plan = plan_group(NO_KID, [group(DEN, LIVING)], TARGETS)
    assert plan == [[LIVING, DEN]] or plan == [[DEN], [LIVING, DEN]]


def test_foreign_group_touching_target_is_refused():
    with pytest.raises(GroupConflict, match="not a hefaistos target"):
        plan_group(NO_KID, [group(DEN, OTHER)], TARGETS)


def test_foreign_group_not_touching_target_is_ignored():
    assert plan_group(NO_KID, [group(KIDS, OTHER)], TARGETS) == [[LIVING, DEN]]


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


def test_busy_speakers_outside_leaders_group_are_taken_over():
    playing = {LIVING: True, DEN: True, KIDS: False}
    assert takeover_pids(ALL, [], playing) == [LIVING, DEN]


def test_reshaping_a_playing_target_group_is_not_interrupted():
    playing = {LIVING: True, DEN: True, KIDS: True}
    assert takeover_pids(NO_KID, [group(LIVING, DEN, KIDS)], playing) == []
