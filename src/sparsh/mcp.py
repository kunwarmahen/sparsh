"""The tools an agent uses to work the phone.

    sparsh mcp [--serial S]

An MCP server on stdin/stdout -- newline-delimited JSON-RPC, written by
hand like Samay's -- with nine tools in three kinds:

    look           read     the screen, as the numbered list
    list_apps      read     apps that can be opened
    describe_hold  read     a held step, in words, with the screen it was on
    tap            act      tap a number from the last look
    type_text      act      type, optionally into a numbered field
    scroll         act      show more of the screen, or of one list
    press_key      act      back, home, enter, ...
    open_app       act      by everyday name or package
    confirm        confirm  do a held step -- after the person said yes

EVERY ACT IS WRITTEN DOWN (log.py), by "agent", however it ended.

EVERY ACT RETURNS THE SCREEN IT LED TO, so the next number to use is
always in the model's last tool result, and a turn needs one ``look`` at
the start and none after.

THE PHONE'S RULES DECIDE WHAT ASKS (rules.py). The acts carry honest
hints -- they change the phone -- and a harness that asks before every
change will ask before every tap. One that knows Sparsh (Yantra's link
reads ``sparsh status --json``, which names each tool's kind) lets the
acts run, because Sparsh holds the risky ones itself: a held tap or
typing comes back as an error with a hold id, nothing done, and the
only way through is ``confirm`` -- marked destructive, so every harness
asks a person first. ``describe_hold`` is what a harness shows them.
A harness that lets ``confirm`` through without asking has given its
yes on the person's behalf; Sparsh can't tell the difference.

ONE PHONE PER SERVER. ``--serial`` is fixed by whoever starts the
server. With none, the only attached phone is used, found again on
each call, so a phone plugged in after the server started still works.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from sparsh import SparshError, __version__, log
from sparsh.device import KEYS, Device, pick
from sparsh.phone import DIRECTIONS, Held, Phone, ScreenChanged
from sparsh.rules import Rules

#: What this server speaks, newest first; the client's choice wins when
#: it is one of these.
VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

_N = {"type": "integer", "minimum": 1, "description": "A number from the last screen list."}
_READ = {"readOnlyHint": True}
_ACT = {"readOnlyHint": False, "destructiveHint": False}

TOOLS: list[dict] = [
    {"name": "look",
     "description": (
         "Read the phone's screen: one numbered line per thing on it -- kind, "
         'words, and what it does ([tap], [type], [scroll], [on]/[off]). Use the '
         "numbers with tap, type_text and scroll. Every other tool returns the "
         "new screen too, so look only at the start or when unsure."),
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": _READ},
    {"name": "list_apps",
     "description": "Apps on the phone that can be opened, as package names.",
     "inputSchema": {"type": "object", "properties": {
         "like": {"type": "string", "description": "Only names containing this."}}},
     "annotations": _READ},
    {"name": "tap",
     "description": (
         "Tap a thing on the screen by its number. If the screen changed since "
         "it was read, nothing is tapped and the new screen comes back. A tap on "
         "Send, Pay, Buy, Delete and the like is HELD for the person: see confirm."),
     "inputSchema": {"type": "object", "properties": {
         "n": _N,
         "long": {"type": "boolean", "description": "Press and hold instead."}},
         "required": ["n"]},
     "annotations": _ACT},
    {"name": "type_text",
     "description": (
         "Type text. With `into`, the numbered field is tapped first; without, "
         "it goes where the keyboard already is. Any language if the phone "
         "allows it; if not, you are told and nothing is typed. `clear` "
         "empties the field first; `enter` presses enter after (to search)."),
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string"},
         "into": _N,
         "clear": {"type": "boolean"},
         "enter": {"type": "boolean"}},
         "required": ["text"]},
     "annotations": _ACT},
    {"name": "scroll",
     "description": (
         '"down" shows what is further down (and so on). With `on`, only that '
         "numbered list scrolls."),
     "inputSchema": {"type": "object", "properties": {
         "direction": {"type": "string", "enum": list(DIRECTIONS)},
         "on": _N},
         "required": ["direction"]},
     "annotations": _ACT},
    {"name": "press_key",
     "description": "Press keys in order: " + ", ".join(KEYS) + ".",
     "inputSchema": {"type": "object", "properties": {
         "keys": {"type": "array", "items": {"type": "string", "enum": list(KEYS)},
                  "minItems": 1}},
         "required": ["keys"]},
     "annotations": _ACT},
    {"name": "open_app",
     "description": (
         'Open an app by its everyday name ("settings", "messages") or package '
         "name. If the name is unclear, the apps that exist come back."),
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string"}}, "required": ["name"]},
     "annotations": _ACT},
    {"name": "describe_hold",
     "description": "A held step in plain words, with the screen it was asked on.",
     "inputSchema": {"type": "object", "properties": {
         "hold": {"type": "string"}}, "required": ["hold"]},
     "annotations": _READ},
    {"name": "confirm",
     "description": (
         "Carry out a step that was HELD for the person's yes (a tap on Send, "
         "Pay, Delete...; typing into a password field). Calling this asks the "
         "person; tell them in a sentence what it will do first."),
     "inputSchema": {"type": "object", "properties": {
         "hold": {"type": "string", "description": "The id the held step gave."}},
         "required": ["hold"]},
     "annotations": {"readOnlyHint": False, "destructiveHint": True}},
]  # fmt: skip

#: Each tool's kind, as ``sparsh status --json`` names it to a harness.
KINDS = {
    t["name"]: (
        "read"
        if t["annotations"].get("readOnlyHint")
        else "confirm"
        if t["annotations"].get("destructiveHint")
        else "act"
    )
    for t in TOOLS
}


class ToolFailed(Exception):
    """A call the model can read about and fix."""


class Tools:
    def __init__(
        self,
        rules: Rules,
        state: str | Path | None = None,
        serial: str | None = None,
        device: Device | None = None,
        settle: float | None = None,
    ) -> None:
        self.rules = rules
        self.state = state
        self.serial = serial
        self.device = device  # given in tests; otherwise found per call
        self.settle = settle
        self._phone: Phone | None = None

    def phone(self) -> Phone:
        device = self.device or pick(self.serial)
        if self._phone is None or self._phone.device.serial != device.serial:
            kwargs = {} if self.settle is None else {"settle": self.settle}
            self._phone = Phone(device, self.state, rules=self.rules, **kwargs)
        else:
            self._phone.device = device
        return self._phone

    def call(self, name: str, args: dict) -> str:
        if name not in KINDS:
            raise ToolFailed(f"no tool {name!r}")
        _known_only(name, args)
        handler = getattr(self, f"_{name}")
        try:
            if KINDS[name] == "read":
                return handler(args)
            # Every act is written down where the person can read it later
            # (log.py) -- held, refused and moved-screen steps included.
            return log.recorded(self.phone(), "agent", name, args, lambda: handler(args))
        except (Held, ScreenChanged) as e:
            raise ToolFailed(str(e)) from None
        except SparshError as e:
            raise ToolFailed(f"Not done: {e}") from None

    def _look(self, args: dict) -> str:
        return self.phone().look().text()

    def _list_apps(self, args: dict) -> str:
        return "\n".join(self.phone().apps(str(args.get("like") or ""))) or "(none)"

    def _tap(self, args: dict) -> str:
        return self.phone().tap(_n(args, "n"), long=bool(args.get("long"))).text()

    def _type_text(self, args: dict) -> str:
        text = args.get("text")
        if not isinstance(text, str):
            raise ToolFailed("missing: text")
        into = _n(args, "into") if args.get("into") is not None else None
        phone = self.phone()
        screen = phone.type(text, into=into, clear=bool(args.get("clear")),
                            enter=bool(args.get("enter")))  # fmt: skip
        return screen.text()

    def _scroll(self, args: dict) -> str:
        on = _n(args, "on") if args.get("on") is not None else None
        return self.phone().scroll(str(args.get("direction") or "down"), on=on).text()

    def _press_key(self, args: dict) -> str:
        keys = args.get("keys")
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            raise ToolFailed("missing: keys")
        return self.phone().key(*[str(k) for k in keys]).text()

    def _open_app(self, args: dict) -> str:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ToolFailed("missing: name")
        return self.phone().open_app(name).text()

    def _describe_hold(self, args: dict) -> str:
        phone = self.phone()
        return phone.held(str(args.get("hold") or "")).describe(phone.device.serial)

    def _confirm(self, args: dict) -> str:
        return "Done. " + self.phone().confirm(str(args.get("hold") or "")).text()


#: Names other tools use, and what they are called here.
_SAID_INSTEAD = {"ref": "n", "index": "n", "number": "n", "element": "n", "id": "n",
                 "field": "into", "value": "text", "key": "keys", "app": "name",
                 "package": "name", "hold_id": "hold"}  # fmt: skip


def _known_only(name: str, args: dict) -> None:
    """UNKNOWN ARGUMENTS ARE ERRORS. A model used to browser tools sends
    ``ref``; ignored, its number is lost and the step goes somewhere else
    -- typing into no field at all. Refused, it says the right name."""
    schema = next(t["inputSchema"] for t in TOOLS if t["name"] == name)
    known = set(schema.get("properties", {}))
    for key in args:
        if key in known:
            continue
        instead = _SAID_INSTEAD.get(key)
        if name in ("type_text", "scroll") and instead == "n":
            instead = "into" if name == "type_text" else "on"
        hint = f" -- use `{instead}`" if instead in known else ""
        names = ", ".join(f"`{k}`" for k in known) or "none"
        raise ToolFailed(f"Not done: {name} has no argument `{key}`{hint} (it takes {names})")


def _n(args: dict, key: str) -> int:
    value = args.get(key)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ToolFailed(f"{key} is a number from the screen list, not {value!r}") from None
    if number < 1:
        raise ToolFailed(f"{key} is a number from the screen list (1 or more)")
    return number


def answer(tools: Tools, message: dict) -> dict | None:
    """One JSON-RPC message in, its reply out (None for a notification)."""
    method, ident = message.get("method"), message.get("id")
    if ident is None:
        return None  # notifications/initialized and kin
    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion")
        return _ok(ident, {
            "protocolVersion": asked if asked in VERSIONS else VERSIONS[0],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sparsh", "version": __version__},
            "instructions": (
                "A phone (Android or iPhone): look, then act by number. A held step needs "
                "the person's yes through confirm."),
        })  # fmt: skip
    if method == "ping":
        return _ok(ident, {})
    if method == "tools/list":
        return _ok(ident, {"tools": TOOLS})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            text = tools.call(str(params.get("name")), params.get("arguments") or {})
            return _ok(ident, {"content": [{"type": "text", "text": text}], "isError": False})
        except ToolFailed as e:
            return _ok(ident, {"content": [{"type": "text", "text": str(e)}], "isError": True})
    return {
        "jsonrpc": "2.0",
        "id": ident,
        "error": {"code": -32601, "message": f"no method {method!r}"},
    }


def _ok(ident: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def serve(tools: Tools, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    """Read one message per line until stdin closes."""
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "not JSON"}}  # fmt: skip
        else:
            reply = answer(tools, message) if isinstance(message, dict) else None
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
