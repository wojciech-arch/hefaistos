"""Pure planning of HEOS set_group calls.

Takeover rule: picking a target takes its speakers, whatever they are doing. Any group holding
one of them, hand-made in the HEOS app or another target, is dissolved and the target is built
fresh. Groups that share no speaker with the target are never touched.
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    leader: int
    members: tuple[int, ...]
    label: str = ""  # what Spotify shows; defaults to the target id
    preset: str = ""  # HEOS group preset id; when set, HEOS applies the preset instead of set_group

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


def _is_known(group: Group, targets: Sequence[Target]) -> bool:
    return any(group.pids == t.pids for t in targets)


def plan_group(target: Target, groups: Sequence[Group]) -> list[list[int]]:
    """Return the ordered set_group pid lists that turn `groups` into `target`."""
    touching = [g for g in groups if g.pids & target.pids]
    if any(g.leader == target.leader and g.pids == target.pids for g in touching):
        return []
    # Every group holding a target speaker is dissolved first, even one led by the target leader:
    # HEOS keeps a reshaped group's old name (e.g. a preset's "All Rooms"), while a fresh group is
    # named after its speakers. Dissolving also frees speakers outside the target.
    steps = [[g.leader] for g in touching]
    steps.append([target.leader, *target.members])
    return steps


def plan_ungroup(groups: Sequence[Group], targets: Sequence[Target]) -> list[list[int]]:
    return [[g.leader] for g in groups if _is_known(g, targets)]


def plan_rollback(target: Target, groups: Sequence[Group]) -> list[list[int]]:
    """Undo a half-built target group: one led by the target leader whose speakers are a strict
    subset of the target. Never touches a complete target or anything with foreign speakers."""
    return [[g.leader] for g in groups
            if g.leader == target.leader and g.pids < target.pids]


def takeover_pids(target: Target, playing: dict[int, bool]) -> list[int]:
    """Target speakers that are playing and must be stopped before grouping (e.g. AirPlay, or a
    hand-made group). The listener's own Spotify playback has already moved to the endpoint."""
    return [pid for pid in (target.leader, *target.members) if playing.get(pid)]
