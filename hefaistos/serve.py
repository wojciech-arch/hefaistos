"""Runs one librespot endpoint per target, but only while that target's HEOS group does not exist.

When a target is picked, the hook stops its endpoint at once (Spotify pauses and the entry goes)
and marks it as switching, which keeps it down while HEOS regroups. Once the group is formed, the
group itself is what Spotify should offer, so the endpoint stays down until the group is gone. It comes back when the
group is replaced by another target or dissolved, e.g. by AirPlay to one of its speakers.
If HEOS cannot be read, every endpoint is shown: better a redundant entry than a missing one.

Each endpoint keeps a fixed ZeroConf port, so Spotify apps that cached its address still reach it
after a restart. Endpoints that keep dying exit the whole process and leave recovery to the
container restart policy. As PID 1 this also reaps the hook processes librespot leaves behind.
"""

import asyncio
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from . import heos as h
from .groups import Group, Target
from .log import log

LIBRESPOT = [
    "librespot", "--backend", "subprocess", "--device", "/app/hefaistos/sink.sh",
    "--disable-audio-cache", "--device-type", "speaker", "--onevent", "/app/hefaistos/hook.sh",
]
PORT_BASE = int(os.environ.get("HEFAISTOS_ZEROCONF_PORT_BASE", "50100"))
POLL_S = 2.0
TICK_S = 0.5
MAX_RESTARTS, RESTART_WINDOW_S = 10, 60.0
SWITCH_HIDE_S = 60.0


def switch_marker(name: str) -> Path:
    """Touched by the hook when a target is picked: keep its endpoint down while HEOS regroups."""
    return Path(f"/tmp/hefaistos-switching-{name}")


def switching(marker_mtime: float | None, now: float) -> bool:
    return marker_mtime is not None and now - marker_mtime < SWITCH_HIDE_S


def _marker_mtime(name: str) -> float | None:
    try:
        return switch_marker(name).stat().st_mtime
    except FileNotFoundError:
        return None


def zeroconf_ports(targets: dict[str, Target]) -> dict[str, int]:
    return {name: PORT_BASE + i for i, name in enumerate(targets)}


def librespot_cmd(target: Target, port: int) -> list[str]:
    return [*LIBRESPOT, "--zeroconf-port", str(port), "--name", target.label]


def visible_targets(targets: dict[str, Target], groups: Sequence[Group]) -> set[str]:
    """Targets to offer in Spotify: those whose speakers are not already grouped exactly so."""
    formed = {g.pids for g in groups}
    return {name for name, t in targets.items() if t.pids not in formed}


def too_many_restarts(history: list[float], now: float) -> bool:
    history[:] = [t for t in history if now - t < RESTART_WINDOW_S]
    history.append(now)
    return len(history) > MAX_RESTARTS


class Visibility:
    """Latest wanted set of endpoints, written by the HEOS watcher thread."""

    def __init__(self, all_targets: set[str]) -> None:
        self._lock = threading.Lock()
        self._all = all_targets
        self._wanted = set(all_targets)
        self.known = threading.Event()
        self.stopping = False

    def update(self, wanted: set[str] | None) -> None:
        wanted = self._all if wanted is None else wanted
        with self._lock:
            changed, self._wanted = wanted != self._wanted, wanted
        self.known.set()
        if changed:
            log("serve.visible", targets=sorted(wanted))

    def wanted(self) -> set[str]:
        with self._lock:
            return set(self._wanted)


async def watch(host: str, targets: dict[str, Target], vis: Visibility) -> None:
    heos = None
    healthy = True
    while not vis.stopping:
        try:
            if heos is None:
                heos = await h.connect(host)
            vis.update(visible_targets(targets, await h.read_groups(heos)))
            if not healthy:
                log("serve.heos_reachable")
            healthy = True
        except Exception as e:
            if healthy:
                log("serve.heos_unreachable", error=f"{type(e).__name__}: {e}",
                    hint=f"showing every target until HEOS at {host} answers again")
            healthy = False
            vis.update(None)
            if heos is not None:
                try:
                    await heos.disconnect()
                except Exception:
                    pass
                heos = None
        await asyncio.sleep(POLL_S)


def run(host: str, targets: dict[str, Target]) -> None:
    ports = zeroconf_ports(targets)
    vis = Visibility(set(targets))
    running: dict[str, int] = {}
    released: set[int] = set()
    restarts: dict[str, list[float]] = {name: [] for name in targets}
    failed = False

    def spawn(name: str) -> None:
        p = subprocess.Popen(librespot_cmd(targets[name], ports[name]), env={**os.environ, "HEFAISTOS_TARGET": name})
        running[name] = p.pid

    def release(name: str) -> None:
        pid = running.get(name)
        if pid is None or pid in released:
            return
        released.add(pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def on_signal(signum: int, _frame: object) -> None:
        vis.stopping = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    threading.Thread(target=lambda: asyncio.run(watch(host, targets, vis)), daemon=True).start()
    # Start endpoints only once the first HEOS read says which are wanted, so a formed group's
    # target does not flash up in Spotify at every container start.
    vis.known.wait(timeout=5.0)
    log("serve.started", endpoints={n: {"name": t.label, "port": ports[n]} for n, t in targets.items()})

    while True:
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                pid = 0
            if pid == 0:
                break
            name = next((n for n, p in running.items() if p == pid), None)
            if name is None:
                continue
            del running[name]
            if pid in released:
                released.discard(pid)
            elif switching(_marker_mtime(name), time.time()):
                log("serve.endpoint_switching", target=name)
            elif not vis.stopping and too_many_restarts(restarts[name], time.monotonic()):
                failed = True
                log("serve.endpoint_flapping", target=name, status=status,
                    hint=f"more than {MAX_RESTARTS} exits in {RESTART_WINDOW_S:.0f}s; check the librespot output above")
                vis.stopping = True
            elif not vis.stopping:
                log("serve.endpoint_exited", target=name, status=status)

        if vis.stopping:
            for name in list(running):
                release(name)
            if not running:
                break
        else:
            now = time.time()
            wanted = {n for n in vis.wanted() if not switching(_marker_mtime(n), now)}
            for name in targets:
                if name in wanted and name not in running:
                    spawn(name)
                elif name not in wanted and name in running:
                    release(name)
        time.sleep(TICK_S)
    sys.exit(1 if failed else 0)
