"""What Sparsh is, for a harness that finds it: ``sparsh status --json``.

The contract is ``format``; a harness that doesn't know the format
refuses rather than guesses (Yantra's sparsh_link does). Fields:

    format   "sparsh.status.v1"
    version  this program's version
    state    the state folder (the last screen of each phone)
    rules    the person's rules file, whether it exists, and what it holds
    phones   [{serial, state, model}] -- what adb sees now; [] when adb
             itself is missing, with ``adb`` saying why
    mcp      {command, args}: how to start the agent's tools
    tools    {name: "read" | "act" | "confirm"} -- what each tool is
             (mcp.py says what a harness should do with each kind)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sparsh import SparshError, __version__
from sparsh.device import attached
from sparsh.mcp import KINDS
from sparsh.rules import load

FORMAT = "sparsh.status.v1"


def sparsh_command() -> str:
    beside = Path(sys.executable).parent / "sparsh"
    if beside.exists():
        return str(beside)
    return shutil.which("sparsh") or "sparsh"


def report(state: Path) -> dict:
    try:
        phones = [{"serial": p.serial, "state": p.state, "model": p.model} for p in attached()]
        adb = "ok"
    except SparshError as e:
        phones, adb = [], str(e)
    rules, path = load(state)
    return {
        "format": FORMAT,
        "version": __version__,
        "state": str(state),
        "rules": {
            "path": str(path),
            "exists": path.exists(),
            "never": list(rules.never),
            "ask": list(rules.ask),
        },
        "adb": adb,
        "phones": phones,
        "mcp": {"command": sparsh_command(), "args": ["mcp", "--state", str(state)]},
        "tools": dict(KINDS),
    }
