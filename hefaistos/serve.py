"""Runs one librespot endpoint per configured target in this process tree.

Exits as soon as any endpoint dies so the container restart policy brings all of them back.
As PID 1 it also reaps the detached hook processes that librespot's --onevent leaves behind.
"""

import os
import signal
import subprocess
import sys

from .groups import Target
from .log import log

LIBRESPOT = [
    "librespot", "--backend", "subprocess", "--device", "/app/hefaistos/sink.sh",
    "--disable-audio-cache", "--device-type", "speaker", "--onevent", "/app/hefaistos/hook.sh",
]


def librespot_cmd(target: Target) -> list[str]:
    return [*LIBRESPOT, "--name", target.label]


def run(targets: dict[str, Target]) -> None:
    procs = {
        subprocess.Popen(librespot_cmd(t), env={**os.environ, "HEFAISTOS_TARGET": t.name}).pid: t
        for t in targets.values()
    }
    log("serve.started", endpoints={t.name: t.label for t in procs.values()})
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
        if target is None:
            continue
        if not stopping:
            failed = True
            log("serve.endpoint_exited", target=target.name, status=status,
                hint="restarting all endpoints; check the librespot output above")
            stop(signal.SIGTERM, None)
    sys.exit(1 if failed else 0)
