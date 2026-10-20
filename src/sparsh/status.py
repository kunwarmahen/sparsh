"""What Sparsh is, for a harness that finds it: ``sparsh status --json``.

The contract is ``format``; a harness that doesn't know the format
refuses rather than guesses (Yantra's sparsh_link does). Fields:

    format   "sparsh.status.v1"
    version  this program's version
    state    the state folder (the last screen of each phone)
    rules    the person's rules file, whether it exists, and what it holds
    phones   [{serial, state, model, note}] -- what adb sees now, and the
             iPhone at ``$SPARSH_WDA`` (its serial is that address)
             and the one a running ``sparsh iphone`` serves (``unnamed``
             until one of those names it: only ``device`` is ready);
             adb's are missing when adb itself is, with ``adb`` saying why.
             A ``$SPARSH_CONNECT`` address that doesn't answer is listed
             ``offline``. ``note`` is why one isn't ready, as a person
             would fix it ("" when it is); a harness that knows only the
             first three fields loses nothing. ``name`` is the phone's
             name in ``$SPARSH_PHONES`` ("" when it has none)
    named    [{name, where, kind}] -- the phones ``$SPARSH_PHONES`` (or
             ``--phone``) names, answering or not: where each is reached,
             and "Android" or "iPhone" (phones.py); [] when none is
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
from sparsh.phones import kind
from sparsh.phones import named as phones_named
from sparsh.rules import load

FORMAT = "sparsh.status.v1"


def sparsh_command() -> str:
    beside = Path(sys.executable).parent / "sparsh"
    if beside.exists():
        return str(beside)
    return shutil.which("sparsh") or "sparsh"


def report(state: Path, named: dict[str, str] | None = None) -> dict:
    try:
        phones = [{"serial": p.serial, "state": p.state, "model": p.model, "note": p.note()}
                  for p in attached()]
        adb = "ok"
    except SparshError as e:
        phones, adb = [], str(e)
    phones += [{"serial": p.serial, "state": p.state, "model": p.model, "note": p.note()}
               for p in iphones(state)]
    found = phones
    if named is None:
        try:
            named = phones_named()
        except SparshError:
            named = {}
    names = {where: name for name, where in named.items()}
    for phone in found:
        phone["name"] = names.get(phone["serial"], "")
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
        "phones": found,
        "named": [{"name": n, "where": w, "kind": kind(w)} for n, w in named.items()],
        "mcp": {"command": sparsh_command(), "args": ["mcp", "--state", str(state)]},
        "shots": "--shots",
        "tools": dict(KINDS),
        "wda": _wda(state),
    }


def _wda(state: Path) -> dict | None:
    sig = signature(state)
    return {**sig, "note": signature_note(sig)} if sig else None
