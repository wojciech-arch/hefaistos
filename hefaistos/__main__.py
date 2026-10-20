"""hefaistos CLI: HEOS grouping and Spotify handoff for the All / No Kid endpoints.

  status | ungroup | group <target> | login | devices | handoff <target>
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from . import heos as h
from . import spotify
from .groups import Target, plan_group, plan_rollback, plan_ungroup, takeover_pids
from .log import log

CONFIG = Path(os.environ.get("HEFAISTOS_CONFIG", "/secrets/config.json"))


def load_targets() -> tuple[str, dict[str, Target]]:
    if not CONFIG.exists():
        raise SystemExit(f"{CONFIG} not found; copy config.example.json there and fill in your HEOS host and player ids (`docker compose run --rm cli status` lists them)")
    cfg = json.loads(CONFIG.read_text())
    targets = {n: Target(n, t["leader"], tuple(t["members"])) for n, t in cfg["targets"].items()}
    return cfg["heos_host"], targets


async def cmd_status(host: str) -> None:
    heos = await h.connect(host)
    try:
        log("heos.snapshot", **await h.snapshot(heos))
    finally:
        await heos.disconnect()


async def cmd_ungroup(host: str, targets: dict[str, Target]) -> None:
    heos = await h.connect(host)
    try:
        steps = plan_ungroup(await h.read_groups(heos), list(targets.values()))
        await h.apply(heos, steps)
        all_pids = frozenset().union(*(t.pids for t in targets.values()))
        await h.wait_ungrouped(heos, all_pids)
        log("heos.snapshot", **await h.snapshot(heos))
    finally:
        await heos.disconnect()


async def form_group(heos: h.Heos, target: Target, targets: dict[str, Target]) -> h.Group:
    groups = await h.read_groups(heos)
    steps = plan_group(target, groups, list(targets.values()))
    busy = takeover_pids(target, groups, await h.playing(heos, target.pids))
    await h.stop(heos, busy)
    await h.apply(heos, steps)
    return await h.wait_for_group(heos, target.leader, target.pids)


async def rollback(host: str, target: Target, api: spotify.Api, reason: str) -> None:
    """Fail closed: never leave a half-built group or Spotify 'playing' silently on the endpoint."""
    heos = await h.connect(host)
    try:
        await h.apply(heos, plan_rollback(target, await h.read_groups(heos)))
    finally:
        await heos.disconnect()
    status, _ = api.call("PUT", "/me/player/pause")
    log("handoff.failed", target=target.name, reason=reason, spotify_pause=status)


async def cmd_group(host: str, name: str, targets: dict[str, Target]) -> None:
    heos = await h.connect(host)
    try:
        g = await form_group(heos, targets[name], targets)
        log("heos.group_formed", target=name, heos_name=g.name)
        log("heos.snapshot", **await h.snapshot(heos))
    finally:
        await heos.disconnect()


def now_playing(api: spotify.Api) -> dict[str, object]:
    p = api.player()
    item = p.get("item") or {}
    dev = p.get("device") or {}
    return {"device": dev.get("name"), "device_id": dev.get("id"), "playing": p.get("is_playing"),
            "track": item.get("uri") if isinstance(item, dict) else None, "progress_ms": p.get("progress_ms")}


async def cmd_handoff(host: str, name: str, targets: dict[str, Target], *, require_playing: bool = True) -> None:
    api = spotify.Api(spotify.load_client())
    before = now_playing(api)
    log("spotify.before", **before)
    if require_playing and not before["playing"]:
        raise SystemExit("nothing is playing in Spotify; start a track on the Mac or iPhone first")
    t0 = time.monotonic()
    try:
        heos = await h.connect(host)
        try:
            g = await form_group(heos, targets[name], targets)
        finally:
            await heos.disconnect()
    except Exception as e:
        await rollback(host, targets[name], api, f"{type(e).__name__}: {e}")
        raise SystemExit(f"handoff to '{name}' failed and was rolled back: {e}") from e
    t_group = time.monotonic()
    log("heos.group_formed", target=name, heos_name=g.name, s=round(t_group - t0, 2))
    # HEOS renames a reshaped group ~0.5 s after membership settles, so re-read the name on
    # every poll instead of trusting the one seen at formation.
    dev: dict[str, object] | None = None
    deadline = time.monotonic() + 30
    while dev is None and time.monotonic() < deadline:
        heos = await h.connect(host)
        try:
            current = next(x for x in await h.read_groups(heos) if x.leader == g.leader)
        finally:
            await heos.disconnect()
        dev = next((d for d in api.devices() if d.get("name") == current.name), None)
        if dev is None:
            await asyncio.sleep(1)
    if dev is None:
        raise SystemExit(f"Spotify never listed the HEOS group; visible: {[d.get('name') for d in api.devices()]}")
    log("spotify.device_visible", name=current.name, s=round(time.monotonic() - t0, 2))
    status, body = api.transfer(str(dev["id"]))
    log("spotify.transfer", status=status, body=body, s=round(time.monotonic() - t0, 2))
    if status not in (200, 202, 204):
        raise SystemExit(f"transfer refused ({status}); see body above")
    deadline = time.monotonic() + 20
    after = now_playing(api)
    while time.monotonic() < deadline and not (after["device_id"] == dev["id"] and after["playing"]):
        await asyncio.sleep(1)
        after = now_playing(api)
    log("spotify.after", **after, s=round(time.monotonic() - t0, 2),
        same_track=after["track"] == before["track"], ok=after["device_id"] == dev["id"] and bool(after["playing"]))


HOOK_DEBOUNCE_S = 20.0


async def cmd_hook(host: str, name: str, targets: dict[str, Target]) -> None:
    """Called by librespot --onevent when the synthetic endpoint starts loading/playing.

    librespot fires several events per selection, so a lock file debounces them to one handoff.
    """
    lock = Path(f"/tmp/hefaistos-hook-{name}")
    if lock.exists() and time.time() - lock.stat().st_mtime < HOOK_DEBOUNCE_S:
        return
    lock.touch()
    log("hook.selected", target=name, player_event=os.environ.get("PLAYER_EVENT"), user=bool(os.environ.get("USER_NAME")))
    await cmd_handoff(host, name, targets, require_playing=False)


def main() -> None:
    p = argparse.ArgumentParser(prog="hefaistos")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("status", "ungroup", "login", "devices"):
        sub.add_parser(c)
    for c in ("group", "handoff", "hook"):
        sub.add_parser(c).add_argument("target")
    a = p.parse_args()
    host, targets = load_targets()
    if a.cmd in ("group", "handoff", "hook") and a.target not in targets:
        raise SystemExit(f"unknown target '{a.target}'; known: {sorted(targets)}")
    if a.cmd == "status":
        asyncio.run(cmd_status(host))
    elif a.cmd == "ungroup":
        asyncio.run(cmd_ungroup(host, targets))
    elif a.cmd == "group":
        asyncio.run(cmd_group(host, a.target, targets))
    elif a.cmd == "login":
        spotify.login(spotify.load_client())
    elif a.cmd == "devices":
        api = spotify.Api(spotify.load_client())
        log("spotify.devices", devices=[{k: d.get(k) for k in ("name", "type", "is_active")} for d in api.devices()])
    elif a.cmd == "handoff":
        asyncio.run(cmd_handoff(host, a.target, targets))
    elif a.cmd == "hook":
        asyncio.run(cmd_hook(host, a.target, targets))


if __name__ == "__main__":
    main()
