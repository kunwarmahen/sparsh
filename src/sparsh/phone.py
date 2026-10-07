"""Numbers in, taps out -- and never a tap on something that moved.

:class:`Phone` is what the CLI and the MCP server hold. It keeps the
last screen it showed, so that ``tap(7)`` means the 7 the agent (or the
person) actually read:

    look()          read the screen; remember it; return it
    tap(7)          look again; is 7 still the same thing in the same
                    place? -> tap the middle of it. Not there any more
                    -> ScreenChanged, carrying the screen as it is now
    type("hi", into=7, clear=True, enter=True)
    scroll("down", on=4)       "down" = show what is further down
    key("back") / open_app("settings") / apps("goo")

Every action ends with a short wait and a fresh look, which is what it
returns: the agent always gets the screen its action led to.

The last screen is saved per phone under the state folder
(``~/.sparsh/phones/<serial>/last.xml``), so ``sparsh look`` and a
later ``sparsh tap 7`` -- two separate programs -- agree on what 7 is.

HELD, NOT DONE. Given :class:`~sparsh.rules.Rules` (the MCP server
always gives them; the command line, which is the person's own hands,
doesn't), a tap or a typing the rules want a yes for is not carried
out -- nor is Enter while the screen shows something that would be
(``_why_enter``). It is kept as a :class:`Hold` and :class:`Held` is
raised with its id; ``confirm(id)`` -- called once the person has said yes -- finds the
same thing on the screen as it is then, and does it. Holds live in this
process only (what was going to be typed into a password field never
touches the disk) and lapse after ``HOLD_FOR`` seconds.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from sparsh import SparshError
from sparsh.device import Device, typeable
from sparsh.rules import Rules
from sparsh.screen import Element, Screen, read

#: Seconds to let the phone react before looking again.
SETTLE = 0.8
#: Seconds a held step waits for its yes.
HOLD_FOR = 600

DIRECTIONS = ("down", "up", "left", "right")


class ScreenChanged(SparshError):
    """The thing asked for isn't where it was; ``screen`` is the screen now."""

    def __init__(self, before: Element, screen: Screen) -> None:
        self.before = before
        self.screen = screen
        super().__init__(
            f"the screen changed since it was read: {before.n} ({before.kind} "
            f'"{before.label}") is not there any more. Nothing was done. '
            "The screen now:\n" + screen.text()
        )


@dataclass
class Hold:
    """A step waiting for a person's yes."""

    id: str
    action: str  # "tap", "type" or "key"
    why: str
    app: str
    target: Element | None  # what to tap, or the field typed into
    screen: str  # the screen as it was, for the person to read
    args: dict = field(default_factory=dict)
    made: float = field(default_factory=time.monotonic)

    def sentence(self) -> str:
        if self.action == "key":
            return f"press {', '.join(self.args['keys'])} in {self.app} -- held because {self.why}"
        if self.action == "tap":
            what = f"tap {self.target.kind} {_quoted(self.target)}"
            if self.args.get("long"):
                what = "press and hold " + what[4:]
        else:
            where = f"into {self.target.kind} {_quoted(self.target)}" if self.target else ""
            shown = "(a password; not shown)" if self._secret else repr(self.args["text"])
            what = f"type {shown} {where}".strip()
            if self.args.get("enter"):
                what += ", then press enter"
        return f"{what} in {self.app} -- held because {self.why}"

    @property
    def _secret(self) -> bool:
        return bool(self.target and self.target.password)

    def describe(self, serial: str) -> str:
        return (
            f"On the phone {serial}: {self.sentence()}.\n"
            f"The screen when it was asked for:\n{self.screen}"
        )


class Held(SparshError):
    def __init__(self, hold: Hold) -> None:
        self.hold = hold
        super().__init__(
            f"NOT DONE -- this needs the person's yes: {hold.sentence()}. "
            f'Call confirm with hold "{hold.id}" to ask them. Do not try '
            "another way round it."
        )


def state_root(given: str | os.PathLike | None = None) -> Path:
    return Path(given or os.environ.get("SPARSH_STATE") or Path.home() / ".sparsh")


class Phone:
    def __init__(
        self,
        device: Device,
        state: str | os.PathLike | None = None,
        settle: float = SETTLE,
        rules: Rules | None = None,
    ) -> None:
        self.device = device
        self.settle = settle
        self.rules = rules
        self.folder = state_root(state) / "phones" / _safe(device.serial)
        self.holds: dict[str, Hold] = {}

    # -- seeing --------------------------------------------------------

    def look(self, shot: str | os.PathLike | None = None) -> Screen:
        xml = self.device.dump()
        screen = read(xml)
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "last.xml").write_text(xml)
        if self._off_limits(screen.app):
            return Screen(screen.app, size=screen.size, note=_OFF_LIMITS)
        if shot is not None:
            Path(shot).write_bytes(self.device.screenshot())
        return screen

    def last(self) -> Screen:
        """The screen as it was last shown (not read again)."""
        try:
            return read((self.folder / "last.xml").read_text())
        except FileNotFoundError:
            raise SparshError("nothing has been read from this phone yet -- look first") from None

    def _still_there(self, n: int) -> Element:
        before = self.last().get(n)
        self._guard(self.last().app)
        return self._find(before)

    def _find(self, before: Element) -> Element:
        now = self.look()
        self._guard(now.app)
        found = now.find(before)
        if found is None:
            raise ScreenChanged(before, now)
        return found

    def _after(self) -> Screen:
        if self.settle:
            time.sleep(self.settle)
        return self.look()

    # -- doing ---------------------------------------------------------

    def tap(self, n: int, long: bool = False) -> Screen:
        target = self._still_there(n)
        why = self.rules.why_tap(target) if self.rules else None
        if why:
            self._hold("tap", why, target, long=long)
        return self._tap(target, long)

    def _tap(self, target: Element, long: bool) -> Screen:
        if not target.enabled:
            raise SparshError(
                f'{target.n} ({target.kind} "{target.label}") is switched off on the phone'
            )
        x, y = target.centre
        if long:
            self.device.long_press(x, y)
        else:
            self.device.tap(x, y)
        return self._after()

    def type(
        self, text: str, into: int | None = None, clear: bool = False, enter: bool = False
    ) -> Screen:
        typeable(text)  # refused before anything is tapped
        if into is not None:
            target = self._still_there(into)
            if not target.type:
                raise SparshError(
                    f'{into} ({target.kind} "{target.label}") is not a field to type in'
                )
        elif self.rules:
            # Typing goes wherever the keyboard is: find out where first.
            now = self.look()
            self._guard(now.app)
            target = next((e for e in now.elements if e.focused), None)
            if target is None:
                # Typed with no field to take it, the words are lost and
                # the agent reads the next screen as if they had landed.
                raise SparshError(
                    "no field has the keyboard, so nothing was typed -- say which "
                    "field with its number (`into`)"
                )
        else:
            target = None
        why = self.rules.why_type(target) if self.rules else None
        if not why and enter and self.rules:
            why = self._why_enter(self.last())
        if why:
            self._hold("type", why, target, text=text, tap_first=into is not None,
                       clear=clear, enter=enter)  # fmt: skip
        return self._type(target if into is not None else None, text, clear, enter)

    def _type(self, field: Element | None, text: str, clear: bool, enter: bool) -> Screen:
        if field is not None:
            self.device.tap(*field.centre)
            time.sleep(min(self.settle, 0.5))
        if clear:
            # The field may show its hint as its text; deleting a few too
            # many letters from an empty field does nothing.
            count = min(len(field.label) + 5 if field else 100, 500)
            self.device.keys("end", *(["delete"] * count))
        self.device.type_text(text)
        if enter:
            self.device.keys("enter")
        return self._after()

    def scroll(self, direction: str = "down", on: int | None = None) -> Screen:
        direction = direction.lower()
        if direction not in DIRECTIONS:
            raise SparshError(f"scroll {' / '.join(DIRECTIONS)}, not {direction!r}")
        if on is not None:
            left, top, right, bottom = self._still_there(on).bounds
        else:
            screen = self.last() if self._has_last() else self.look()
            self._guard(screen.app)
            left, top, right, bottom = 0, 0, *screen.size
        cx, cy = (left + right) // 2, (top + bottom) // 2
        dx, dy = (right - left) * 3 // 10, (bottom - top) * 3 // 10
        # The finger moves the other way to the content: to see what is
        # further down, push the page up.
        x1, y1, x2, y2 = {
            "down": (cx, cy + dy, cx, cy - dy),
            "up": (cx, cy - dy, cx, cy + dy),
            "right": (cx + dx, cy, cx - dx, cy),
            "left": (cx - dx, cy, cx + dx, cy),
        }[direction]
        self.device.swipe(x1, y1, x2, y2, 400)
        return self._after()

    def key(self, *names: str) -> Screen:
        # Back and Home are how you leave an app that's off limits, so
        # keys are never refused -- but Enter can be held (_why_enter).
        if self.rules and any(n.lower().strip() == "enter" for n in names):
            why = self._why_enter(self.look())
            if why:
                self._hold("key", why, None, keys=list(names))
        self.device.keys(*names)
        return self._after()

    def _why_enter(self, screen: Screen) -> str | None:
        """ENTER IS HELD WHERE A TAP WOULD BE. In a chat app with "Enter to
        send" on, Enter is the Send button; so while anything on the
        screen would itself be held, so is Enter. A search screen showing
        an Install button pays one yes for it."""
        for element in screen.elements:
            why = element.tap and self.rules.why_tap(element)
            if why:
                return f"enter could do what {element.kind} {_quoted(element)} does ({why})"
        return None

    def open_app(self, name: str) -> Screen:
        package = self.which_app(name)
        self._guard(package)
        self.device.launch(package)
        return self._after()

    # -- holds ---------------------------------------------------------

    def _hold(self, action: str, why: str, target: Element | None, **args) -> None:
        now = time.monotonic()
        for old in [h for h in self.holds.values() if now - h.made > HOLD_FOR]:
            del self.holds[old.id]
        hold = Hold(
            id="h" + secrets.token_hex(3),
            action=action,
            why=why,
            app=self.last().app,
            target=target,
            screen=self.last().text(),
            args=args,
        )
        self.holds[hold.id] = hold
        raise Held(hold)

    def held(self, hold_id: str) -> Hold:
        hold = self.holds.get(hold_id.strip())
        if hold is None or time.monotonic() - hold.made > HOLD_FOR:
            self.holds.pop(hold_id.strip(), None)
            raise SparshError(
                f"no step is waiting under {hold_id!r} (a hold lasts {HOLD_FOR // 60} "
                "minutes) -- look again and ask again"
            )
        return hold

    def confirm(self, hold_id: str) -> Screen:
        """Do a held step: the person said yes to it."""
        hold = self.held(hold_id)
        del self.holds[hold.id]
        if hold.action == "key":
            now = self.look()
            if now.app != hold.app:
                raise SparshError(
                    f"the phone is in {now.app or 'another app'} now, not {hold.app}; "
                    "nothing was pressed"
                )
            self.device.keys(*hold.args["keys"])
            return self._after()
        if hold.action == "tap":
            return self._tap(self._find(hold.target), hold.args.get("long", False))
        field = hold.target
        if hold.args["tap_first"]:
            field = self._find(field)
        return self._type(
            field if hold.args["tap_first"] else None,
            hold.args["text"],
            hold.args["clear"],
            hold.args["enter"],
        )

    # -- apps ----------------------------------------------------------

    def apps(self, like: str = "") -> list[str]:
        found = [a for a in self.device.apps() if not self._off_limits(a)]
        return [a for a in found if like.lower() in a.lower()] if like else found

    def which_app(self, name: str) -> str:
        """``settings`` -> ``com.android.settings``; a package name as is."""
        apps = self.device.apps()
        wanted = name.strip().lower()
        if wanted in apps:
            return wanted
        squashed = wanted.replace(" ", "")
        stem = squashed[: max(4, len(squashed) - 2)]
        found = [
            a
            for a in apps
            if any(part == squashed or part.startswith(stem) for part in a.lower().split("."))
        ]
        if len(found) == 1:
            return found[0]
        if found:
            raise SparshError(f"more than one app matches {name!r}: {', '.join(found)}")
        shown = [a for a in apps if not self._off_limits(a)]
        raise SparshError(f"no app matches {name!r}. Apps on this phone: {', '.join(shown)}")

    def _off_limits(self, app: str) -> bool:
        return self.rules is not None and self.rules.forbidden(app)

    def _guard(self, app: str) -> None:
        if self._off_limits(app):
            raise SparshError(f"{app} is off limits: the person's rules keep the agent out of it")

    def _has_last(self) -> bool:
        return (self.folder / "last.xml").exists()


_OFF_LIMITS = (
    "(this app is off limits: the person's rules keep the agent out of it, so "
    "nothing on it is shown. Press back or home to leave.)"
)


def _quoted(element: Element) -> str:
    return '"' + element.label + '"' if element.label else f"number {element.n}"


def _safe(serial: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in serial) or "phone"
