"""Pure planning of HEOS set_group calls.

Ownership rule: hefaistos may only reshape or dissolve a group whose leader+members equal one
of the configured targets (so a user-made group with a target's exact composition is taken over);
any other group touching a target speaker is a conflict and is never modified.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    leader: int
    members: tuple[int, ...]

    @property
    def pids(self) -> frozenset[int]:
        return frozenset((self.leader, *self.members))


@dataclass(frozen=True)
class Group:
    name: str
    leader: int
    members: tuple[int, ...]

    @property
    def pids(self) -> frozenset[int]:
        return frozenset((self.leader, *self.members))


class GroupConflict(Exception):
    pass


def _is_known(group: Group, targets: Sequence[Target]) -> bool:
    return any(group.pids == t.pids for t in targets)


def plan_group(target: Target, groups: Sequence[Group], targets: Sequence[Target]) -> list[list[int]]:
    """Return the ordered set_group pid lists that turn `groups` into `target`."""
    touching = [g for g in groups if g.pids & target.pids]
    if any(g.leader == target.leader and g.pids == target.pids for g in touching):
        return []
    for g in touching:
        if not _is_known(g, targets):
            raise GroupConflict(
                f"group '{g.name}' (leader {g.leader}, members {list(g.members)}) is not a hefaistos "
                f"target; ungroup it in the HEOS app or add its composition to config.json"
            )
    steps = [[g.leader] for g in touching if g.leader != target.leader]
    steps.append([target.leader, *target.members])
    return steps


def plan_ungroup(groups: Sequence[Group], targets: Sequence[Target]) -> list[list[int]]:
    return [[g.leader] for g in groups if _is_known(g, targets)]


def plan_rollback(target: Target, groups: Sequence[Group]) -> list[list[int]]:
    """Undo a half-built target group: one led by the target leader whose speakers are a strict
    subset of the target. Never touches a complete target or anything with foreign speakers."""
    return [[g.leader] for g in groups
            if g.leader == target.leader and g.pids < target.pids]


def takeover_pids(target: Target, groups: Sequence[Group], playing: dict[int, bool]) -> list[int]:
    """Target speakers that are busy with something else and must be stopped before grouping
    (picking a target takes its speakers over, e.g. stops AirPlay on them).

    Speakers already in a group led by the target leader are playing our session; stopping them
    would break a seamless All <-> No Kid reshape."""
    ours = next((g.pids for g in groups if g.leader == target.leader), frozenset())
    return [pid for pid in (target.leader, *target.members) if playing.get(pid) and pid not in ours]
