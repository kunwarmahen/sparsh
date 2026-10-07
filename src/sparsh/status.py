"""What Sparsh is, for a harness that finds it: ``sparsh status --json``.

The contract is ``format``; a harness that doesn't know the format
refuses rather than guesses (Yantra's sparsh_link does). Fields:

    format   "sparsh.status.v1"
    version  this program's version
    state    the state folder (the last screen of each phone)
    rules    the person's rules file, whether it exists, and what it holds
    phones   [{serial, state, model}] -- what adb sees now, and the
             iPhone at ``$SPARSH_WDA`` (its serial is that address);
             adb's are missing when adb itself is, with ``adb`` saying why
    mcp      {command, args}: how to start the agent's tools
    shots    the flag that adds a screenshot to a screen that can't be
             read as a list (mcp.py); a harness adds it to ``mcp.args``
             only when its model can see and the person allows it
    tools    {name: "read" | "act" | "confirm"} -- what each tool is
             (mcp.py says what a harness should do with each kind)
    wda      the iPhone's WebDriverAgent signature, once ``sparsh wda
             WDA.ipa`` has read it: {ipa, signed_until, days_left, note},
             where ``note`` is a sentence for the person when two days or
             fewer are left (iphone.py), else ""; null when there's none
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from sparsh import SparshError, __version__
from sparsh.device import attached, iphones
from sparsh.iphone import signature, signature_note
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
    phones += [{"serial": p.serial, "state": p.state, "model": p.model} for p in iphones()]
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
        "shots": "--shots",
        "tools": dict(KINDS),
        "wda": _wda(state),
    }


def _wda(state: Path) -> dict | None:
    sig = signature(state)
    return {**sig, "note": signature_note(sig)} if sig else None
