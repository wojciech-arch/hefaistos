import asyncio
import time

from pyheos import Heos, HeosOptions, PlayState

from .groups import Group
from .log import log


async def connect(host: str) -> Heos:
    heos = Heos(HeosOptions(host, events=False, heart_beat=False))
    await heos.connect()
    return heos


async def read_groups(heos: Heos) -> list[Group]:
    groups = await heos.get_groups(refresh=True)
    return [Group(g.name, g.lead_player_id, tuple(g.member_player_ids)) for g in groups.values()]


async def snapshot(heos: Heos) -> dict[str, object]:
    players = await heos.get_players(refresh=True)
    groups = await read_groups(heos)
    return {
        "players": {pid: p.name for pid, p in players.items()},
        "groups": [{"name": g.name, "leader": g.leader, "members": list(g.members)} for g in groups],
    }


async def playing(heos: Heos, pids: frozenset[int]) -> dict[int, bool]:
    return {pid: await heos.player_get_play_state(pid) == PlayState.PLAY for pid in pids}


async def stop(heos: Heos, pids: list[int]) -> None:
    for pid in pids:
        log("heos.takeover_stop", pid=pid)
        await heos.player_set_play_state(pid, PlayState.STOP)
    if pids:
        await asyncio.sleep(1.0)


async def apply(heos: Heos, steps: list[list[int]]) -> None:
    for pids in steps:
        log("heos.set_group", pids=pids)
        await heos.set_group(pids)


async def wait_for_group(heos: Heos, leader: int, pids: frozenset[int], timeout: float = 20.0) -> Group:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for g in await read_groups(heos):
            if g.leader == leader and g.pids == pids:
                return g
        await asyncio.sleep(0.5)
    raise TimeoutError(f"HEOS did not report group leader={leader} pids={sorted(pids)} within {timeout}s; "
                       "check the HEOS app for a stuck or partial group")


async def wait_ungrouped(heos: Heos, pids: frozenset[int], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(g.pids & pids for g in await read_groups(heos)):
            return
        await asyncio.sleep(0.5)
    raise TimeoutError(f"speakers {sorted(pids)} still grouped after {timeout}s")
