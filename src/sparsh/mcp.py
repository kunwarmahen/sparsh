"""The tools an agent uses to work the phone.

    sparsh mcp [--serial S | --phone NAME=WHERE ...]

An MCP server on stdin/stdout -- newline-delimited JSON-RPC, written by
hand like Samay's -- with twelve tools in three kinds:

    look           read     the screen, as the numbered list (and, asked,
                            its picture)
    list_apps      read     apps that can be opened
    describe_hold  read     a held step, in words, with the screen it was on
    watch_phone    read     start watching the person's own hand (hand.py)
    watched        read     what they did since, and the screen now
    tap            act      tap a number from the last look
    tap_at         act      tap a spot on a screenshot -- always held
    type_text      act      type, optionally into a numbered field
    scroll         act      show more of the screen, or of one list
    press_key      act      back, home, enter, ...
    open_app       act      by everyday name or package
    confirm        confirm  do a held step -- after the person said yes

EVERY ACT IS WRITTEN DOWN (log.py), by "agent", however it ended; and
the person's own steps, seen while they show the agent a job, by "you".

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

A PICTURE ONLY WHERE THE LIST FALLS SHORT (``--shots``). The model
works from the numbered list, not from pictures: that is what lets a
local model do it, and what keeps a phone's screen out of a cloud
model's request. But some screens give the list nothing -- a page that
never goes still (Settings' About phone), an app drawn as one picture
-- and some give it only part: Google Maps' places are unnamed boxes,
and on a real Nexus 6P an agent asked for nearby restaurants opened
each blank row in turn, thirty-odd steps, to read their names. Started
with ``--shots``, a tool whose screen comes back empty, unreadable or
partly blank (``Screen.partly_blank``) also returns a screenshot of it,
as an MCP image; and ``look`` with ``picture`` asks for one on any
screen, for what the model can tell the list is missing. Only then,
and never of an app on the person's ``never`` list.

THE MODEL'S PICTURE IS MADE SMALLER, to 720 pixels across (picture.py).
A Nexus 6P's full screenshot cost ``qwen3.8`` 3635 tokens of its
context, and Maps shows one place per screen: a turn that scrolled ten
times carried ten of them, each step took two minutes, and it ran out
of time before it answered. Halved, the same screen cost 950 tokens and
read the same names. A tap by position is a share of the picture, not
a pixel, so a smaller picture names the same spot. It is OFF unless
whoever starts the server turns it on; that harness knows whether its
model can see, and whether the person lets screenshots go to it (Yantra
gives them to local models, and to cloud models only when asked).

A TAP BY POSITION ONLY ON SUCH A SCREEN, AND HELD EVERY TIME. What the
picture shows can be tapped with ``tap_at``, a spot 0-1000 across and
down it (a share of the picture, so a model that sees it smaller still
names the same spot). Refused wherever the list has something; always
held, and ``describe_hold`` returns the picture with the spot ringed,
as an image beside its words, for the harness to show the person.

WHICH PHONE. Unnamed, ``--serial`` is fixed by whoever starts the
server; with none, the only phone that answers is used, found again on
each call, so a phone plugged in after the server started still works.
NAMED (``$SPARSH_PHONES`` or ``--phone NAME=WHERE``, phones.py), one
server works several phones: with more than one, every tool takes
``phone`` and every answer starts ``Phone: NAME``, so the model never
loses track of whose screen it read. Each phone keeps its own last
look (a number from the Nexus's list never taps the iPhone), its own
holds, its own watch and its own screen-awake keeper. A hold remembers
its phone: ``confirm`` and ``describe_hold`` need only its id.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from sparsh import SparshError, __version__, log, picture
from sparsh.awake import Awake
from sparsh.device import KEYS, Device, pick
from sparsh.hand import Watch
from sparsh.phone import DIRECTIONS, Held, Phone, ScreenChanged
from sparsh.phones import kind
from sparsh.rules import Rules
from sparsh.screen import Screen

#: The most a screenshot may weigh (Anthropic's per-image cap).
SHOT_BYTES = 5 * 1024 * 1024

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
     "inputSchema": {"type": "object", "properties": {
         "picture": {"type": "boolean", "description": (
             "Also a screenshot, when what you need is on the screen but not in "
             "the list (unnamed rows, a map, a page with no words). Only if this "
             "phone sends pictures; you are told if not.")}}},
     "annotations": _READ},
    {"name": "phone_status",
     "description": (
         "The phone's battery (percent, and whether it is charging) and the calls "
         "missed since they were last looked at, without touching the screen. "
         "An iPhone tells its battery only."),
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
    {"name": "tap_at",
     "description": (
         "Tap a spot on the screenshot -- ONLY on a screen that came with one, and "
         "only for what the numbered list doesn't have. x and y each run 0 to 1000 across and "
         "down the picture (0,0 top left; 1000,1000 bottom right; 500,500 the "
         "middle). ALWAYS HELD for the person, who is shown the spot ringed on "
         "the picture: see confirm."),
     "inputSchema": {"type": "object", "properties": {
         "x": {"type": "integer", "minimum": 0, "maximum": 1000,
               "description": "Across the picture: 0 left edge, 1000 right edge."},
         "y": {"type": "integer", "minimum": 0, "maximum": 1000,
               "description": "Down the picture: 0 top edge, 1000 bottom edge."},
         "long": {"type": "boolean", "description": "Press and hold instead."}},
         "required": ["x", "y"]},
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
     "description": (
         "A held step in plain words, with the screen it was asked on (for a tap "
         "by position, the picture with the spot ringed)."),
     "inputSchema": {"type": "object", "properties": {
         "hold": {"type": "string"}}, "required": ["hold"]},
     "annotations": _READ},
    {"name": "watch_phone",
     "description": (
         "Start watching the person do a job on the phone with their own hand, "
         "while they show it to you. Returns the screen they start from. Don't "
         "touch the phone yourself while watching; call watched each time they "
         "say they did a step."),
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": _READ},
    {"name": "watched",
     "description": (
         "What the person did on the phone since watch_phone or the last watched "
         "(\"tapped 4 item 'Mom'\", \"typed on the keyboard\"), and the screen "
         "now. On a phone that can't show where it was touched, you get the screen "
         "before and after to compare: say what you think they did, and ask."),
     "inputSchema": {"type": "object", "properties": {}},
     "annotations": _READ},
    {"name": "confirm",
     "description": (
         "Carry out a step that was HELD for the person's yes (a tap on Send, "
         "Pay, Delete...; typing into a password field; a tap by position). "
         "Calling this asks the "
         "person; tell them in a sentence what it will do first. What comes back "
         "after \"Done\" is the phone's own answer to the step, which WAS carried "
         "out (a message such as \"Network is not ready\" is the phone's, not a "
         "lapsed hold)."),
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


def status_words(status: dict) -> str:
    """``phone_status`` in words a model passes on as they are."""
    level, charging, missed = status.get("battery"), status.get("charging"), status.get("missed")
    battery = ("Battery: not said." if level is None else
               f"Battery: {level}%" + ("" if charging is None else
                                       ", charging." if charging else ", not charging."))
    if missed is None:
        calls = "Missed calls: this phone doesn't let them be read."
    elif not missed:
        calls = "Missed calls: none new."
    else:
        calls = f"Missed calls ({len(missed)} new): " + ", ".join(missed) + "."
    return f"{battery}\n{calls}"


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
        shots: bool = False,
        awake: Awake | None = None,
        phones: dict[str, str] | None = None,
        awakes: dict[str, Awake] | None = None,
        devices: dict[str, Device] | None = None,
    ) -> None:
        self.shots = shots
        self.awake = awake  # the screen kept on while working (awake.py); None: left alone
        self.rules = rules
        self.state = state
        self.serial = serial
        self.device = device  # given in tests; otherwise found per call
        self.settle = settle
        # Named phones (phones.py): {name: where}, and each one's own keeper,
        # last Phone (its holds) and watch. Empty: the one phone that answers.
        self.phones = dict(phones or {})
        self.awakes = dict(awakes or {})
        self.devices = dict(devices or {})  # given in tests
        self._named: dict[str, Phone] = {}
        self._watches: dict[str, Watch] = {}
        self._now: str | None = None  # the phone this call is about
        self._phone: Phone | None = None
        self._watch = Watch()  # the person's own hand, while they show a job

    def listed(self) -> list[dict]:
        """``tools/list``: with more than one phone, each tool says which."""
        if len(self.phones) < 2:
            return TOOLS
        which = {"type": "string", "enum": list(self.phones), "description": (
            "Which phone: " + _kinds(self.phones) + ".")}
        out = []
        for tool in TOOLS:
            schema = tool["inputSchema"]
            props = {**schema.get("properties", {}), "phone": which}
            if tool["name"] in ("confirm", "describe_hold"):
                out.append({**tool, "inputSchema": {**schema, "properties": props}})
                continue  # the hold knows its phone
            required = [*schema.get("required", []), "phone"]
            out.append({**tool, "inputSchema": {**schema, "properties": props,
                                                 "required": required}})
        return out

    def phone(self) -> Phone:
        if self.phones:
            return self._named_phone(self._now or self._which({}))
        device = self.device or pick(self.serial)
        if self._phone is None or self._phone.device.serial != device.serial:
            kwargs = {} if self.settle is None else {"settle": self.settle}
            self._phone = Phone(device, self.state, rules=self.rules, **kwargs)
        else:
            self._phone.device = device
        return self._phone

    def _named_phone(self, name: str) -> Phone:
        device = self.devices.get(name) or pick(self.phones[name])
        phone = self._named.get(name)
        if phone is None or phone.device.serial != device.serial:
            kwargs = {} if self.settle is None else {"settle": self.settle}
            phone = self._named[name] = Phone(device, self.state, rules=self.rules, **kwargs)
        else:
            phone.device = device
        return phone

    def _which(self, args: dict) -> str:
        """The named phone a call is about: ``phone``, the one a hold was
        made on, or the only one there is."""
        given = args.get("phone")
        if given is not None:
            if given not in self.phones:
                raise ToolFailed(f"Not done: there is no phone {given!r}; the phones are "
                                 f"{_kinds(self.phones)}")
            return str(given)
        hold = str(args.get("hold") or "").strip()
        if hold:
            for name, phone in self._named.items():
                if hold in phone.holds:
                    return name
        if len(self.phones) == 1:
            return next(iter(self.phones))
        raise ToolFailed(f"Not done: which phone? Say `phone`: {_kinds(self.phones)}")

    def keeper(self) -> Awake | None:
        return self.awakes.get(self._now) if self.phones else self.awake

    def watch(self) -> Watch:
        if not self.phones:
            return self._watch
        return self._watches.setdefault(self._now or "", Watch())

    def stop(self) -> None:
        """The server stops: no watch outlives it, every screen gets its own back."""
        for watch in [self._watch, *self._watches.values()]:
            watch.stop()

    def call(self, name: str, args: dict) -> str:
        return self.reply(name, args)[0]

    def reply(self, name: str, args: dict) -> tuple[str, bytes | None]:
        """The tool's text, and a screenshot when one goes with it."""
        self._now = None
        if self.phones and name in KINDS:
            args = dict(args)
            self._now = self._which(args)
            args.pop("phone", None)
        text, png = self._reply(name, args)
        if len(self.phones) > 1:
            text = f"Phone: {self._now}\n{text}"
        return text, png

    def _reply(self, name: str, args: dict) -> tuple[str, bytes | None]:
        result = self._result(name, args)
        if isinstance(result, tuple):
            return result
        if not isinstance(result, Screen):
            return result, None
        text = result.text()
        if name == "confirm":
            text = _DONE + text
        phone = self.phone()
        asked = name == "look" and bool(args.get("picture"))
        phone.pictured = None
        if not (self.shots and phone.shown(result, asked)):
            if asked:
                text += "\n" + (_NOT_THIS_APP if self.shots else _NO_SHOTS)
            return text, None
        try:
            png = phone.device.screenshot()
        except SparshError as e:
            return f"{text}\n(No screenshot either: {e}.)", None
        png = picture.mark(png) or png  # smaller: see the module docstring
        if len(png) > SHOT_BYTES:
            return f"{text}\n(The screenshot was too big to attach.)", None
        phone.pictured = result.app
        if result.elements:
            return text + "\n" + _part(result, asked), png
        text = text.replace(_NOTHING, "(nothing on this screen can be read as a list)")
        return text + "\n" + _SHOT, png

    def _result(self, name: str, args: dict) -> str | Screen:
        if name not in KINDS:
            raise ToolFailed(f"no tool {name!r}")
        _known_only(name, args)
        handler = getattr(self, f"_{name}")
        try:
            keeper = self.keeper()
            if keeper is not None:
                phone = self.phone()
                try:
                    keeper.step(phone.device, phone.folder)
                except SparshError:
                    pass  # a help to the step, never a condition of it
            if KINDS[name] == "read":
                return handler(args)
            # Every act is written down where the person can read it later
            # (log.py) -- held, refused and moved-screen steps included.
            return log.recorded(self.phone(), "agent", name, args, lambda: handler(args))
        except (Held, ScreenChanged) as e:
            raise ToolFailed(str(e)) from None
        except SparshError as e:
            raise ToolFailed(f"Not done: {e}") from None

    def _look(self, args: dict) -> Screen:
        return self.phone().see()

    def _phone_status(self, args: dict) -> str:
        return status_words(self.phone().device.battery_and_calls())

    def _list_apps(self, args: dict) -> str:
        return "\n".join(self.phone().apps(str(args.get("like") or ""))) or "(none)"

    def _tap(self, args: dict) -> Screen:
        return self.phone().tap(_n(args, "n"), long=bool(args.get("long")))

    def _tap_at(self, args: dict) -> Screen:
        return self.phone().tap_at(_spot(args, "x"), _spot(args, "y"),
                                   long=bool(args.get("long")))  # fmt: skip

    def _type_text(self, args: dict) -> Screen:
        text = args.get("text")
        if not isinstance(text, str):
            raise ToolFailed("missing: text")
        into = _n(args, "into") if args.get("into") is not None else None
        phone = self.phone()
        screen = phone.type(text, into=into, clear=bool(args.get("clear")),
                            enter=bool(args.get("enter")))  # fmt: skip
        return screen

    def _scroll(self, args: dict) -> Screen:
        on = _n(args, "on") if args.get("on") is not None else None
        return self.phone().scroll(str(args.get("direction") or "down"), on=on)

    def _press_key(self, args: dict) -> Screen:
        keys = args.get("keys")
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            raise ToolFailed("missing: keys")
        return self.phone().key(*[str(k) for k in keys])

    def _open_app(self, args: dict) -> Screen:
        name = str(args.get("name") or "").strip()
        if not name:
            raise ToolFailed("missing: name")
        return self.phone().open_app(name)

    def _watch_phone(self, args: dict) -> Screen:
        return self.watch().start(self.phone())

    def _watched(self, args: dict) -> str:
        return self.watch().since(self.phone())

    def _describe_hold(self, args: dict) -> tuple[str, bytes | None]:
        phone = self.phone()
        hold = phone.held(str(args.get("hold") or ""))
        shot = hold.picture()
        if shot is not None and len(shot) > SHOT_BYTES:
            shot = None
        return hold.describe(phone.device.serial, phone.name()), shot

    def _confirm(self, args: dict) -> Screen:
        # A Screen, like every act's: on a screen the list can't read, the
        # picture comes with it, and the next spot is chosen by looking --
        # in the trial, without it qwen guessed where OK was, and missed.
        return self.phone().confirm(str(args.get("hold") or ""))


_NOTHING = "(nothing on this screen can be read -- try a screenshot)"
_SHOT = (
    "(A screenshot of this screen is attached to this result: you can already see "
    "it, no tool is needed. To act on what it shows, first try another way -- press "
    "back, scroll, or search; if there is none, tap_at its position, which the "
    "person is asked about.)"
)


#: Names other tools use, and what they are called here.
_DONE = "Done: the step was carried out. The phone now (its answer to the step):\n"
_NO_SHOTS = "(No picture: this phone's tools send none to this model. Work from the list.)"
_NOT_THIS_APP = "(No picture: the person's rules keep pictures of this app from the agent.)"


def _kinds(phones: dict[str, str]) -> str:
    return ", ".join(f"{name} ({kind(where)})" for name, where in phones.items())


def _part(screen: Screen, asked: bool) -> str:
    why = ("you asked for it" if asked
           else "the page's words aren't in the list" if screen.blank_page
           else f"{screen.blanks} things on it to tap have no words")  # fmt: skip
    return (
        f"(A screenshot is attached -- {why}: you can already see it, no tool is "
        "needed. Tap by number whatever the list has; for what only the picture "
        "shows, tap_at its position, which the person is asked about.)"
    )


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


def _spot(args: dict, key: str) -> int:
    value = args.get(key)
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        raise ToolFailed(f"{key} is a number from 0 to 1000 across the picture, "
                         f"not {value!r}") from None  # fmt: skip
    if not 0 <= number <= 1000:
        raise ToolFailed(f"{key} runs from 0 to 1000 across the picture, not {value!r}")
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
            "instructions": _instructions(tools),
        })  # fmt: skip
    if method == "ping":
        return _ok(ident, {})
    if method == "tools/list":
        return _ok(ident, {"tools": tools.listed()})
    if method == "tools/call":
        params = message.get("params") or {}
        try:
            text, png = tools.reply(str(params.get("name")), params.get("arguments") or {})
            content: list[dict] = [{"type": "text", "text": text}]
            if png is not None:
                data = base64.b64encode(png).decode()
                content.append({"type": "image", "data": data, "mimeType": "image/png"})
            return _ok(ident, {"content": content, "isError": False})
        except ToolFailed as e:
            return _ok(ident, {"content": [{"type": "text", "text": str(e)}], "isError": True})
    return {
        "jsonrpc": "2.0",
        "id": ident,
        "error": {"code": -32601, "message": f"no method {method!r}"},
    }


def _instructions(tools: Tools) -> str:
    said = ("A phone (Android or iPhone): look, then act by number. A held step needs "
            "the person's yes through confirm.")
    if len(tools.phones) > 1:
        said += (f" There are {len(tools.phones)} phones: {_kinds(tools.phones)}; every "
                 "tool but confirm and describe_hold says which with `phone`.")
    return said


def _ok(ident: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def serve(tools: Tools, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
    """Read one message per line until stdin closes -- and then stop
    reading the person's touches, or getevent outlives the server."""
    try:
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
    finally:
        tools.stop()
