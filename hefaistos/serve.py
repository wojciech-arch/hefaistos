"""Runs one librespot endpoint per configured target in this process tree.

An endpoint that exits is restarted on its own; the hook releases its endpoint after grouping so
Spotify stops "playing" into the silent sink. Each endpoint keeps a fixed ZeroConf port, so Spotify
apps that cached its address still reach it after a restart. Too many restarts in a short window
exit the whole process and leave recovery to the container restart policy.
As PID 1 this also reaps the detached hook processes that librespot's --onevent leaves behind.
"""

import os
import signal
import subprocess
import sys
import time

from .groups import Target
from .log import log

LIBRESPOT = [
    "librespot", "--backend", "subprocess", "--device", "/app/hefaistos/sink.sh",
    "--disable-audio-cache", "--device-type", "speaker", "--onevent", "/app/hefaistos/hook.sh",
]
PORT_BASE = int(os.environ.get("HEFAISTOS_ZEROCONF_PORT_BASE", "50100"))
MAX_RESTARTS, RESTART_WINDOW_S = 10, 60.0


def zeroconf_ports(targets: dict[str, Target]) -> dict[str, int]:
    return {name: PORT_BASE + i for i, name in enumerate(targets)}


def librespot_cmd(target: Target, port: int) -> list[str]:
    return [*LIBRESPOT, "--zeroconf-port", str(port), "--name", target.label]


def too_many_restarts(history: list[float], now: float) -> bool:
    history[:] = [t for t in history if now - t < RESTART_WINDOW_S]
    history.append(now)
    return len(history) > MAX_RESTARTS


def run(targets: dict[str, Target]) -> None:
    ports = zeroconf_ports(targets)

    def spawn(t: Target) -> int:
        return subprocess.Popen(librespot_cmd(t, ports[t.name]), env={**os.environ, "HEFAISTOS_TARGET": t.name}).pid

    procs = {spawn(t): t for t in targets.values()}
    restarts: dict[str, list[float]] = {name: [] for name in targets}
    log("serve.started", endpoints={t.name: {"name": t.label, "port": ports[t.name]} for t in procs.values()})
    stopping = failed = False

    def stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        for pid in list(procs):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while procs:
        try:
            pid, status = os.wait()
        except ChildProcessError:
            break
        target = procs.pop(pid, None)
        if target is None or stopping:
            continue
        if too_many_restarts(restarts[target.name], time.monotonic()):
            failed = True
            log("serve.endpoint_flapping", target=target.name, status=status,
                hint=f"more than {MAX_RESTARTS} restarts in {RESTART_WINDOW_S:.0f}s; check the librespot output above")
            stop(signal.SIGTERM, None)
            continue
        procs[spawn(target)] = target
        log("serve.endpoint_restarted", target=target.name, status=status)
    sys.exit(1 if failed else 0)
