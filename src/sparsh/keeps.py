"""What Sparsh keeps on this computer, for a backup to take.

A backup of the house (Sarathi's ``sarathi backup``) is one file holding
every program's own files, and each program says where its are --
``sparsh keeps --json``, asked the way ``status --json`` is -- so the
program that packs it knows nothing of what is inside.

Two places. The state folder: your rules (``rules.toml``: what is never
touched, what always asks), each phone's log of what was done on it, the
iPhone's apps and its WebDriverAgent's dates. And adb's key: the phone
trusts this computer by that key alone, so a new computer holding it is
trusted at once, with no "Allow USB debugging?" on the phone again.

WHAT IS LEFT OUT: logs, a process's pid and the socket the containers
borrow adb through (each made again when it starts), the iPhone's
developer disk images and the tunnel's certificates (fetched again on the
next ``sparsh iphone``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sparsh.phone import state_root

FORMAT = "sparsh.keeps.v1"
LEAVE_OUT = ["*.log", "*.pid", "*.sock", "devimages", "ios-roots.pem"]


def adb_home() -> Path:
    """Where adb keeps its key: $ANDROID_USER_HOME, else ~/.android."""
    named = os.environ.get("ANDROID_USER_HOME", "").strip()
    return Path(named).expanduser() if named else Path.home() / ".android"


def report(state: str | os.PathLike | None = None) -> dict[str, Any]:
    keeps = [{"id": "state", "path": str(state_root(state)), "leave_out": LEAVE_OUT,
              "what": "your rules for the phone, what was done on each phone, the "
                      "iPhone's apps and its WebDriverAgent's dates"}]
    for name in ("adbkey", "adbkey.pub"):
        keeps.append({"id": name, "path": str(adb_home() / name), "leave_out": [],
                      "what": "adb's key: the phone trusts this computer by it"})
    for place in keeps:
        place["exists"] = Path(place["path"]).exists()
    return {"format": FORMAT, "keeps": keeps}
