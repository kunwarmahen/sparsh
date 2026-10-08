"""What was done on the phone, step by step -- kept so it can be read later.

An agent working a phone for two minutes takes a dozen steps, and the
answer it gives at the end ("Done -- the text was sent") is its own
account of them. The log is the phone's: every act, who asked for it,
what it was done to, and how it ended, in
``~/.sparsh/phones/<serial>/actions.jsonl``, one JSON object a line:

    at       when, ISO 8601 with the zone
    by       "agent" (through `sparsh mcp`) or "you" (the command line)
    action   tap, type_text, scroll, press_key, open_app, confirm
    args     what was asked -- text typed into a password field is
             "(hidden)", here as everywhere
    on       the line the step was aimed at, as it was read ("6 item
             \\"Send SMS — SMS\\" [tap]"), or the held step for a confirm
    outcome  done | held | changed | not_done
    said     for anything but done: why (the hold id, the reason)
    app      the app on screen afterwards
    after    the screen afterwards, as the agent was shown it (cut short)

ONLY ACTS. Looking reads nothing worth keeping and would bury the
steps; a peek (``look --peek``) is the person watching, not doing.

BOUNDED. The newest ``KEEP`` entries are kept; when the file grows to
twice that, it is cut back. A log that fills a disk is a log someone
deletes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sparsh import SparshError
from sparsh.phone import Held, Phone, ScreenChanged
from sparsh.screen import Screen

FILE = "actions.jsonl"
KEEP = 500
#: How much of the screen afterwards is kept per step.
AFTER_CHARS = 4000

HIDDEN = "(hidden)"


def path(phone: Phone) -> Path:
    return phone.folder / FILE


def recorded(phone: Phone, by: str, action: str, args: dict, run: Callable[[], Any]) -> Any:
    """Run one act and write down how it went; its result (or its
    exception) passes through untouched."""
    on, secret = _aimed_at(phone, action, args)
    entry: dict[str, Any] = {"by": by, "action": action, "args": _shown(args, secret), "on": on}
    try:
        result = run()
    except Held as e:
        _add(phone, entry, "held", said=e.hold.id + ": " + e.hold.why)
        raise
    except ScreenChanged as e:
        _add(phone, entry, "changed", app=e.screen.app, said="the screen had moved")
        raise
    except SparshError as e:
        _add(phone, entry, "not_done", said=str(e).splitlines()[0][:300])
        raise
    after = result.text() if isinstance(result, Screen) else str(result)
    app = result.app if isinstance(result, Screen) else _app_of(after)
    granted, phone.granted = getattr(phone, "granted", None), None
    more = {"said": f'granted ahead: "{granted}"'} if granted else {}
    _add(phone, entry, "done", app=app, after=after[:AFTER_CHARS], **more)
    return result


def recent(phone: Phone, n: int = 20) -> list[dict]:
    """The newest ``n`` steps, newest first."""
    try:
        lines = path(phone).read_text().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a line cut short by a crash is skipped, not fatal
        if len(out) >= n:
            break
    return out


def line(entry: dict) -> str:
    """One step for a person: ``08:31:02 agent tap 6 ... -> held (h1: ...)``."""
    at = entry.get("at", "")[11:19]
    args = entry.get("args") or {}
    asked = " ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())
    text = f"{at} {entry.get('by', '?'):5} {entry.get('action')} {asked}".rstrip()
    if entry.get("on"):
        text += f"  [on {entry['on']}]"
    text += f" -> {entry.get('outcome')}"
    if entry.get("said"):
        text += f" ({entry['said']})"
    elif entry.get("app"):
        text += f" ({entry['app']})"
    return text


def _add(phone: Phone, entry: dict, outcome: str, **more: Any) -> None:
    entry = {"at": datetime.now().astimezone().isoformat(timespec="seconds"),
             **entry, "outcome": outcome, **more}  # fmt: skip
    file = path(phone)
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("a") as out:
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim(file)
    except OSError:
        pass  # the step happened either way; a full disk must not undo it


def _trim(file: Path) -> None:
    lines = file.read_text().splitlines()
    if len(lines) >= 2 * KEEP:
        file.write_text("\n".join(lines[-KEEP:]) + "\n")


def _aimed_at(phone: Phone, action: str, args: dict) -> tuple[str | None, bool]:
    """(the line this step is aimed at, as last read; is what it types secret)."""
    try:
        if action == "confirm":
            hold = phone.held(str(args.get("hold") or ""))
            secret = bool(hold.target and hold.target.password)
            return hold.sentence(), secret
        last = phone.last()
    except SparshError:
        return None, False
    n = args.get("n", args.get("into", args.get("on")))
    target = None
    if n is not None:
        try:
            target = last.get(int(n))
        except (SparshError, TypeError, ValueError):
            target = None
    if action == "type_text" and target is None:
        target = next((e for e in last.elements if e.focused), None)
    return (target.line() if target and n is not None else None), bool(target and target.password)


def _shown(args: dict, secret: bool) -> dict:
    shown = dict(args)
    if secret and "text" in shown:
        shown["text"] = HIDDEN
    return shown


def _app_of(text: str) -> str:
    for row in text.splitlines():
        if row.startswith("App: "):
            return row[5:]
        if row.startswith("Done. App: "):
            return row[11:]
    return ""
