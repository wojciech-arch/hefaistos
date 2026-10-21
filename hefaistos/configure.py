"""Interactive terminal editor for config.json targets.

Reads the current config (if any), lists the HEOS speakers, and writes the edited config to a
separate output path; the calling script shows the diff and decides whether to install it.
"""

import asyncio
import json
import re
from pathlib import Path

from . import heos as h

LETTERS = "abcdefghijklmnopqrstuvwxyz"


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "target"


def parse_speakers(text: str, players: list[int]) -> list[int]:
    """'1 3' or '1,3' (positions in the speaker list) -> player ids, first one is the leader."""
    picked: list[int] = []
    for tok in re.split(r"[\s,]+", text.strip()):
        if not tok:
            continue
        if not tok.isdigit() or not 1 <= int(tok) <= len(players):
            raise ValueError(f"'{tok}' is not a speaker number between 1 and {len(players)}")
        pid = players[int(tok) - 1]
        if pid in picked:
            raise ValueError(f"speaker {tok} is listed twice")
        picked.append(pid)
    return picked


def problems(targets: dict[str, dict], players: dict[int, str]) -> list[str]:
    out: list[str] = []
    names: dict[str, str] = {}
    sets: dict[frozenset[int], str] = {}
    for tid, t in targets.items():
        pids = [t["leader"], *t["members"]]
        label = t.get("name") or tid
        if len(pids) < 2:
            out.append(f"{label}: needs at least 2 speakers; a single speaker is already in Spotify")
        missing = [p for p in pids if p not in players]
        if missing:
            out.append(f"{label}: unknown player ids {missing}; pick the speakers again")
        if label in names:
            out.append(f"{label}: name also used by '{names[label]}'; Spotify needs unique names")
        names.setdefault(label, tid)
        key = frozenset(pids)
        if key in sets:
            out.append(f"{label}: same speakers as '{sets[key]}'; one of them would never be listed")
        sets.setdefault(key, label)
    return out


def describe(t: dict, players: dict[int, str]) -> str:
    leader = players.get(t["leader"], str(t["leader"]))
    members = [players.get(p, str(p)) for p in t["members"]]
    return ", ".join([f"{leader} (leader)", *members])


def ask(prompt: str, default: str = "") -> str:
    shown = f"{prompt} [{default}]: " if default else f"{prompt}: "
    answer = input(shown).strip()
    return answer or default


def edit_target(t: dict | None, players: dict[int, str], order: list[int]) -> dict | None:
    name = ask("  Spotify name", (t or {}).get("name", ""))
    if not name:
        print("  cancelled: a name is required")
        return None
    current = ""
    if t:
        current = " ".join(str(order.index(p) + 1) for p in [t["leader"], *t["members"]] if p in order)
    while True:
        text = ask("  Speakers by number, leader first (e.g. 1 2)", current)
        try:
            pids = parse_speakers(text, order)
        except ValueError as e:
            print(f"  {e}")
            continue
        if len(pids) < 2:
            print("  pick at least 2 speakers")
            continue
        return {**(t or {}), "name": name, "leader": pids[0], "members": pids[1:]}


def show(targets: dict[str, dict], players: dict[int, str], order: list[int]) -> None:
    print("\nSpeakers:")
    for i, pid in enumerate(order, 1):
        print(f"  {i}) {players[pid]}")
    print("Targets:")
    if not targets:
        print("  (none)")
    for letter, (tid, t) in zip(LETTERS, targets.items()):
        mode = "" if t.get("strategy", "rebuild") == "rebuild" else "  [switch: HEOS preset]"
        print(f"  {letter}) {t.get('name') or tid:<14} {describe(t, players)}{mode}")
    print("\n[n] new  [e <letter>] edit  [d <letter>] delete  [s] save  [q] quit without saving")


def pick(targets: dict[str, dict], arg: str) -> str | None:
    if len(arg) == 1 and arg in LETTERS[: len(targets)]:
        return list(targets)[LETTERS.index(arg)]
    print(f"  no target '{arg}'")
    return None


def run(src: Path, dst: Path) -> None:
    cfg = json.loads(src.read_text()) if src.exists() else {}
    host = cfg.get("heos_host") or ask("IP of any HEOS speaker")
    print(f"Reading speakers from HEOS at {host} ...")

    async def read_players() -> dict[int, str]:
        heos = await h.connect(host)
        try:
            return {pid: p.name for pid, p in (await heos.get_players(refresh=True)).items()}
        finally:
            await heos.disconnect()

    players = asyncio.run(read_players())
    order = sorted(players, key=lambda p: players[p].lower())
    targets: dict[str, dict] = dict(cfg.get("targets", {}))

    while True:
        show(targets, players, order)
        try:
            cmd, _, arg = input("> ").strip().partition(" ")
        except EOFError:
            print("\nquit without saving")
            return
        if cmd == "n":
            t = edit_target(None, players, order)
            if t:
                tid, n = slug(t["name"]), 2
                while tid in targets:
                    tid, n = f"{slug(t['name'])}-{n}", n + 1
                targets[tid] = t
        elif cmd == "e" and (tid := pick(targets, arg.strip())):
            t = edit_target(targets[tid], players, order)
            if t:
                targets[tid] = t
        elif cmd == "d" and (tid := pick(targets, arg.strip())):
            del targets[tid]
        elif cmd == "s":
            issues = problems(targets, players)
            if issues:
                print("Fix these first:\n  " + "\n  ".join(issues))
                continue
            dst.write_text(json.dumps({"heos_host": host, "targets": targets}, indent=2, ensure_ascii=False) + "\n")
            print(f"saved {len(targets)} target(s)")
            return
        elif cmd == "q":
            print("quit without saving")
            return
        elif cmd not in ("e", "d"):
            print("  unknown command")
