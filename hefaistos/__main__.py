"""hefaistos CLI: HEOS grouping for the Spotify Connect target endpoints.

  serve | status | ungroup | group <target> | hook <target> | configure
"""

import argparse
import asyncio
import json
import os
import signal
import time
from pathlib import Path

from . import heos as h
from . import serve
from .groups import Target, plan_group, plan_rollback, plan_ungroup, takeover_pids
from .log import log

CONFIG = Path(os.environ.get("HEFAISTOS_CONFIG", "/config/config.json"))


def parse_config(cfg: dict) -> tuple[str, dict[str, Target]]:
    targets = {n: Target(n, t["leader"], tuple(t["members"]), t.get("name") or n) for n, t in cfg["targets"].items()}
    labels = [t.label for t in targets.values()]
    if len(set(labels)) != len(labels):
        raise SystemExit(f"target names must be unique, got {labels}; Spotify tells endpoints apart by name")
    return cfg["heos_host"], targets


def load_targets() -> tuple[str, dict[str, Target]]:
    if not CONFIG.exists():
        raise SystemExit(f"{CONFIG} not found; copy config.example.json there and fill in your HEOS host and player ids (`docker compose run --rm hefaistos status` lists them)")
    return parse_config(json.loads(CONFIG.read_text()))


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
    steps = plan_group(target, groups)
    busy = takeover_pids(target, await h.playing(heos, target.pids))
    await h.stop(heos, busy)
    await h.apply(heos, steps)
    return await h.wait_for_group(heos, target.leader, target.pids)


async def rollback(host: str, target: Target, reason: str) -> None:
    """Fail closed: never leave a half-built group behind."""
    heos = await h.connect(host)
    try:
        await h.apply(heos, plan_rollback(target, await h.read_groups(heos)))
    finally:
        await heos.disconnect()
    log("group.failed", target=target.name, reason=reason)


async def cmd_group(host: str, name: str, targets: dict[str, Target]) -> None:
    t0 = time.monotonic()
    try:
        heos = await h.connect(host)
        try:
            g = await form_group(heos, targets[name], targets)
        finally:
            await heos.disconnect()
    except Exception as e:
        await rollback(host, targets[name], f"{type(e).__name__}: {e}")
        raise SystemExit(f"grouping '{name}' failed and was rolled back: {e}") from e
    log("heos.group_formed", target=name, heos_name=g.name, s=round(time.monotonic() - t0, 2))


HOOK_DEBOUNCE_S = 20.0


async def cmd_hook(host: str, name: str, targets: dict[str, Target]) -> None:
    """Called by librespot --onevent when the target endpoint starts loading/playing.

    librespot fires several events per selection, so a lock file debounces them to one grouping.
    On success `serve` hides the endpoint once it sees the group, and the listener taps the group.
    On failure the endpoint is released here so Spotify does not keep "playing" into the silent
    sink; `serve` brings it back.
    """
    lock = Path(f"/tmp/hefaistos-hook-{name}")
    if lock.exists() and time.time() - lock.stat().st_mtime < HOOK_DEBOUNCE_S:
        return
    lock.touch()
    log("hook.selected", target=name, player_event=os.environ.get("PLAYER_EVENT"))
    try:
        await cmd_group(host, name, targets)
    except BaseException:
        release_endpoint(os.environ.get("HEFAISTOS_ENDPOINT_PID"))
        raise


def release_endpoint(pid: str | None) -> None:
    if not pid or not pid.isdigit():
        log("hook.release_skipped", reason="no endpoint pid from hook.sh")
        return
    try:
        os.kill(int(pid), signal.SIGTERM)
        log("hook.endpoint_released", pid=int(pid))
    except ProcessLookupError:
        log("hook.release_skipped", reason=f"endpoint {pid} already gone")


def main() -> None:
    p = argparse.ArgumentParser(prog="hefaistos")
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("serve", "status", "ungroup", "configure"):
        sub.add_parser(c)
    for c in ("group", "hook"):
        sub.add_parser(c).add_argument("target")
    a = p.parse_args()
    if a.cmd == "configure":
        from . import configure
        configure.run(CONFIG, Path(os.environ.get("HEFAISTOS_CONFIG_OUT", "/out/config.json")))
        return
    host, targets = load_targets()
    if a.cmd in ("group", "hook") and a.target not in targets:
        raise SystemExit(f"unknown target '{a.target}'; known: {sorted(targets)}")
    if a.cmd == "serve":
        serve.run(host, targets)
    elif a.cmd == "status":
        asyncio.run(cmd_status(host))
    elif a.cmd == "ungroup":
        asyncio.run(cmd_ungroup(host, targets))
    elif a.cmd == "group":
        asyncio.run(cmd_group(host, a.target, targets))
    elif a.cmd == "hook":
        asyncio.run(cmd_hook(host, a.target, targets))


if __name__ == "__main__":
    main()
