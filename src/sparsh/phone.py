"""Numbers in, taps out -- and never a tap on something that moved.

:class:`Phone` is what the CLI and the MCP server hold. It keeps the
last screen it showed, so that ``tap(7)`` means the 7 the agent (or the
person) actually read:

    look()          read the screen; remember it; return it
    tap(7)          look again; is 7 still the same thing in the same
                    place? -> tap the middle of it. Not there any more
                    -> ScreenChanged, carrying the screen as it is now
    tap_at(500, 300)   a spot on the picture, 0-1000 each way: only on a
                    screen that came with one, and ALWAYS held (below)
    type("hi", into=7, clear=True, enter=True)
    scroll("down", on=4)       "down" = show what is further down
    key("back") / open_app("settings") / apps("goo")

Every action ends with a short wait and a fresh look, which is what it
returns: the agent always gets the screen its action led to -- or, when
that screen can't be read, a sentence saying the action WAS done.

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

THE PERSON SEES WHAT THEY SAY YES TO. A hold keeps a screenshot taken
as it was made, with what would be tapped or typed into ringed, and
the words filled in on the screen (the message, the number). That and
one sentence are the question -- not the numbered list, which is the
model's: on a real Nexus 6P, a yes to "Call" came as forty-one lines of
the dialler's keys, and its person couldn't find the number in them.
The list is said only when no picture can be had.

A TAP BY POSITION IS HELD EVERY TIME. Some screens give the list
nothing (Settings' About page, its clock ticking; an app drawn as one
picture), some give it only part (Maps' unnamed places, a web page not
yet described: ``Screen.partly_blank``), and the agent sees what is
missing only in a screenshot. ``tap_at`` taps a spot on that picture --
only on a screen that came with one (``pictured``), never in an app
whose rules refuse words, since a spot has no words to check. No rule
can tell what is at a spot, so every one is held, and the person is
shown the picture with the spot ringed (picture.py). ``confirm`` taps
only if the same app is in front and a new screenshot matches the one
the person saw (``_as_pictured``); the spot is the same share of the
screen as it was of the picture. Typing on such a screen is held too
(``_type_unseen``): nothing says which field has the keyboard.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from sparsh import SparshError, picture
from sparsh.awake import mode as awake_mode
from sparsh.device import Device
from sparsh.rules import Rules
from sparsh.screen import Element, Screen, ScreenUnreadable, read

#: Seconds to let the phone react before looking again.
SETTLE = 0.8
#: Seconds a held step waits for its yes.
HOLD_FOR = 600
#: The share of a screenshot that may differ from the one a person said
#: yes to by looking (a ticking clock, a blinking cursor) -- no more.
CHANGED = 0.02

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
    action: str  # "tap", "tap_at", "type" or "key"
    why: str
    app: str
    target: Element | None  # what to tap, or the field typed into
    screen: str  # the screen as it was, said only when there is no picture
    args: dict = field(default_factory=dict)
    made: float = field(default_factory=time.monotonic)
    #: The screenshot taken as the step was held, for the person; where
    #: on it (0-1000 each way) the ring goes; the words filled in on it.
    card: bytes | None = None
    ring: tuple[int, int] | None = None
    filled: tuple[str, ...] = ()

    def sentence(self) -> str:
        if self.action == "tap_at":
            what = "press and hold" if self.args.get("long") else "tap"
            return (
                f"{what} the spot ringed on the picture (x {self.args['x']}, "
                f"y {self.args['y']} of 1000) in {self.app or 'the app in front'} "
                f"-- held because {self.why}"
            )
        if self.action == "key":
            return f"press {', '.join(self.args['keys'])} in {self.app} -- held because {self.why}"
        if self.action == "tap":
            what = f"tap {self.target.kind} {_quoted(self.target)}"
            if self.args.get("long"):
                what = "press and hold " + what[4:]
        else:
            where = f"into {self.target.kind} {_quoted(self.target)}" if self.target else ""
            if not self.target and "picture" in self.args:
                where = "where the keyboard is, on the screen in the picture"
            shown = "(a password; not shown)" if self._secret else repr(self.args["text"])
            what = f"type {shown} {where}".strip()
            if self.args.get("enter"):
                what += ", then press enter"
        return f"{what} in {self.app} -- held because {self.why}"

    @property
    def _secret(self) -> bool:
        return bool(self.target and self.target.password)

    def describe(self, serial: str) -> str:
        """One sentence, and what is filled in on the screen; the numbered
        list only when there is no picture to show (module docstring)."""
        said = f"On the phone {serial}: {self.sentence()}."
        if self.filled:
            said += "\nOn the screen: " + "; ".join(self.filled)
        if self.picture() is None:
            said += f"\nThe screen when it was asked for:\n{self.screen}"
        return said

    def picture(self) -> bytes | None:
        """The screen as it was held, for the person: a tap by position
        with its spot ringed, any other step with what it would tap or
        type into ringed -- made smaller once, or as it was if it can't
        be marked here. None when no screenshot could be had."""
        if "marked" in self.args:
            return self.args["marked"]
        shot = self.args.get("picture", self.card)
        if shot is None:
            return None
        spot = (self.args["x"], self.args["y"]) if "x" in self.args else self.ring
        self.args["marked"] = picture.mark(shot, *spot) if spot else picture.mark(shot)
        self.args["marked"] = self.args["marked"] or shot
        return self.args["marked"]


class Held(SparshError):
    def __init__(self, hold: Hold) -> None:
        self.hold = hold
        super().__init__(
            f"NOT DONE -- this needs the person's yes: {hold.sentence()}. "
            f'Call confirm with hold "{hold.id}" now, in this same answer: that '
            "is how they are asked. Do not ask them in words first, and do not "
            "try another way round it."
        )


def state_root(given: str | os.PathLike | None = None) -> Path:
    return Path(given or os.environ.get("SPARSH_STATE") or Path.home() / ".sparsh")


def _always_on() -> bool:
    try:
        return awake_mode() == "always"
    except SparshError:
        return False  # a bad word is said where the server starts, not here


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
        #: When the last step in each app was taken, for an app's pace.
        self._acted: dict[str, float] = {}
        #: The app in front when the screen last couldn't be described.
        self._restless: str | None = None
        #: The grant the last step was done under, for the log (log.py).
        self.granted: str | None = None
        #: The app whose screen last went to the agent with a picture
        #: (mcp.py): a tap by position is only for a screen it has seen.
        self.pictured: str | None = None

    # -- seeing --------------------------------------------------------

    def look(self, shot: str | os.PathLike | None = None, keep: bool = True) -> Screen:
        """Read the screen. ``keep=False`` is a PEEK: someone else looking
        (a person's page beside a running agent) must not change what the
        agent's numbers mean, so the last screen is left as it was.

        A SCREEN THAT NEVER GOES STILL IS TRIED ONCE. While the app that
        last couldn't be described is still in front, one try, not two:
        each waits about twelve seconds, and a look of two tries plus an
        act's look after it outran a harness's thirty-second call."""
        retry = self._restless is None or self._front() != self._restless
        try:
            xml = self.device.dump(retry=retry)
        except ScreenUnreadable:
            self._restless = self._front()
            raise
        self._restless = None
        screen = read(xml)
        if screen.blank_page and self.settle:
            # Chrome describes a page a moment after it is first asked
            # (screen.py): one more look, after two settles, reads it.
            time.sleep(self.settle * 2)
            try:
                xml = self.device.dump(retry=retry)
                screen = read(xml)
            except ScreenUnreadable:
                pass
        if keep:
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / "last.xml").write_text(xml)
        if self._off_limits(screen.app):
            return Screen(screen.app, size=screen.size, note=_OFF_LIMITS)
        if screen.app in _LOCK_HOSTS and self.device.awake()[1]:
            # A real Nexus 6P, asked to open Settings while locked, printed
            # its lock screen and nothing else: an agent reads that as
            # Settings. Only the system's own screens are asked about.
            screen.remark = _LOCKED
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
        """The screen an act led to. THE ACT WAS DONE either way: a screen
        that can't be read afterwards (a clock ticking on it) is said as
        such, never as "Not done" -- told that, an agent does it again,
        and a second Send is a second message. The last look stays as it
        was, so the next number is checked against a screen it can't
        find, and refused."""
        if self.settle:
            time.sleep(self.settle)
        try:
            return self.look()
        except ScreenUnreadable as e:
            return self._unreadable(f"{_UNREAD}{e}.")

    def see(self) -> Screen:
        """The agent's look. A screen that can't be read is an ANSWER, not
        a failure: it says which app is in front and what to do, and a
        screenshot can go with it (mcp.py, ``--shots``)."""
        try:
            return self.look()
        except ScreenUnreadable as e:
            return self._unreadable(f"(this screen can't be read as a list: {e}.)")

    def _unreadable(self, note: str) -> Screen:
        try:
            app = self.device.front_app()
        except SparshError:
            app = ""
        if self._off_limits(app):
            return Screen(app, note=_OFF_LIMITS)
        return Screen(app, note=note)

    def shown(self, screen: Screen, asked: bool = False) -> bool:
        """Whether a picture of ``screen`` may be shown: only when the list
        has nothing to give (empty, or the screen can't be read), gives
        only part (``partly_blank``), or the agent ``asked`` for one -- and
        never of an app the rules keep the agent out of, nor of one that
        can't be named while the rules keep it out of some."""
        if screen.note == _OFF_LIMITS:
            return False
        # A lock screen's notifications are unnamed boxes, but what it
        # needs is its person, not a look: it says so (_LOCKED).
        blank = screen.partly_blank and screen.remark != _LOCKED
        if screen.elements and not (asked or blank):
            return False
        if not screen.app:
            return not (self.rules and self.rules.never)
        return not self._off_limits(screen.app)

    # -- doing ---------------------------------------------------------

    def tap(self, n: int, long: bool = False) -> Screen:
        target = self._still_there(n)
        app = self.last().app
        if self.rules and (refused := self.rules.refused(target, app)):
            raise SparshError(refused)
        why = self.rules.why_tap(target, app) if self.rules else None
        granted = self._granted(target, app) if why else None
        if why and granted is None:
            self._hold("tap", why, target, long=long)
        self._pace(app)
        screen = self._tap(target, long)
        if granted is not None:
            self.granted = granted.said
            screen.remark = f'(Done without asking: the schedule allows "{granted.said}".)' + (
                f"\n{screen.remark}" if screen.remark else ""
            )
        return screen

    def _granted(self, target: Element, app: str):
        """The grant that lets this held tap through, or None (rules.py).
        Checked against the screen as it is NOW, which ``_still_there``
        has just read."""
        if not self.rules or not self.rules.grants:
            return None
        screen = self.last().text()
        for g in self.rules.grants:
            if g.covers(target.label, app, screen, self.which_app):
                return g
        return None

    def tap_at(self, x: int, y: int, long: bool = False) -> Screen:
        """A spot on the screenshot, each of x and y 0 to 1000 across and
        down it. Only on a screen that came with a picture, and held every
        time (module docstring)."""
        for value in (x, y):
            if not 0 <= value <= 1000:
                raise SparshError(f"x and y run from 0 to 1000 across the picture, not {value}")
        screen = self.see()
        seen = self.pictured is not None and self.pictured == screen.app
        if screen.elements and not (screen.partly_blank or seen):
            raise SparshError(
                "this screen can be read as a list, so tap by number, not by position. "
                "If what you need isn't in the list, look with picture first. "
                "The screen now:\n" + screen.text()
            )
        if not self.shown(screen, asked=seen):
            raise SparshError("no picture of this screen may be shown, so it has no spot to tap")
        rule = self.rules.apps.get(screen.app) if self.rules else None
        if rule and rule.refuse:
            raise SparshError(
                f"a spot has no words to check against what {screen.app} refuses "
                f"({rule.why or 'its rules'}), so nothing is tapped by position there"
            )
        if self.rules is None:  # the person's own hands
            return self._tap_spot(x, y, long, self.device.screenshot())
        self._hold("tap_at", "it is a tap by position: the screen gives no list, so what "
                   "is at that spot is known only from the picture", None,
                   where=(screen.app, screen.text()), x=x, y=y, long=long,
                   picture=self.device.screenshot())  # fmt: skip

    def _tap_spot(self, x: int, y: int, long: bool, shot: bytes) -> Screen:
        """The spot as the same share of the screen: an Android phone taps in
        the picture's pixels, an iPhone in points (``touch_size``)."""
        touch = getattr(self.device, "touch_size", None)
        size = touch() if touch else picture.size(shot)
        if not size:
            raise SparshError("the screen's size is not known, so nothing was tapped")
        width, height = size
        px, py = x * (width - 1) // 1000, y * (height - 1) // 1000
        if long:
            self.device.long_press(px, py)
        else:
            self.device.tap(px, py)
        return self._after()

    def _pace(self, app: str) -> None:
        """AN APP'S PACE IS KEPT BETWEEN STEPS. Rules a harness added may
        say how fast steps in an app may come (X locks accounts that tap
        like a program); the wait is here, before the step, not after."""
        wait = self.rules.pace(app) if self.rules else 0.0
        if wait and app in self._acted:
            left = self._acted[app] + wait - time.monotonic()
            if left > 0:
                time.sleep(left)
        self._acted[app] = time.monotonic()

    def _tap(self, target: Element, long: bool) -> Screen:
        if not target.enabled:
            raise SparshError(
                f'{target.n} ({target.kind} "{target.label}") is switched off on the phone'
            )
        x, y = self._uncovered(target).centre
        if long:
            self.device.long_press(x, y)
        else:
            self.device.tap(x, y)
        return self._after()

    def type(
        self, text: str, into: int | None = None, clear: bool = False, enter: bool = False
    ) -> Screen:
        self.device.check_text(text)  # refused before anything is tapped
        if into is not None:
            target = self._still_there(into)
            if not target.type:
                raise SparshError(
                    f'{into} ({target.kind} "{target.label}") is not a field to type in'
                )
        elif self.rules:
            # Typing goes wherever the keyboard is: find out where first.
            try:
                now = self.look()
            except ScreenUnreadable as e:
                return self._type_unseen(text, clear, enter, e)
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
            why = self._why_enter(self.last(), target)
        if why:
            self._hold("type", why, target, text=text, tap_first=into is not None,
                       clear=clear, enter=enter)  # fmt: skip
        self._pace(self.last().app if self._has_last() else "")
        return self._type(target if into is not None else None, text, clear, enter)

    def _type_unseen(self, text: str, clear: bool, enter: bool, e: ScreenUnreadable) -> NoReturn:
        """TYPING ON A SCREEN WITH NO LIST IS HELD. A dialog over Settings'
        About page can't be read either (the page behind it never goes
        still), so after a tap by position opens it, nothing says which
        field the keyboard is in -- or that it isn't a password. The
        person is shown the picture and the words, and decides."""
        screen = self._unreadable(f"(this screen can't be read as a list: {e}.)")
        if not self.shown(screen):
            raise e
        self._hold("type", "the screen gives no list, so where the words go is known "
                   "only from the picture", None, where=(screen.app, screen.text()),
                   text=text, tap_first=False, clear=clear, enter=enter,
                   picture=self.device.screenshot())  # fmt: skip

    def _uncovered(self, target: Element) -> Element:
        """THE KEYBOARD HIDES WHAT THE LIST SHOWS. Android's list leaves the
        keyboard out, so a field under it is listed, and a tap there lands
        on a key: on a real Nexus 6P, "Last name" and "Phone" under Gboard
        took a stray letter each, and the agent's words all went into the
        first field. So a target under the keyboard gets back pressed
        once (with a keyboard up, back only closes it), the screen read
        again, and the same thing found there. Asked only while a field
        had the keyboard, so a plain tap costs nothing."""
        if not any(e.focused and e.type for e in self.last().elements):
            return target
        area = self.device.keyboard_area()
        x, y = target.centre
        if area is None or not (area[0] <= x < area[2] and area[1] <= y < area[3]):
            return target
        self.device.keys("back")
        return self._find(target)

    def _type(self, field: Element | None, text: str, clear: bool, enter: bool) -> Screen:
        if field is not None:
            field = self._uncovered(field)
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
        self._pace(self.last().app if self._has_last() else "")
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

    def _why_enter(self, screen: Screen, field: Element | None = None) -> str | None:
        """ENTER IS HELD WHERE A TAP WOULD BE. In a chat app with "Enter to
        send" on, Enter is the Send button; so while something on the
        screen that Enter could press would itself be held, so is Enter.

        What Enter could press is what sits BESIDE THE FIELD being typed
        into -- Send next to the message box, Post under a reply -- so
        with a field focused, only things overlapping its row (give or
        take the field's own height) count. In the phone trial, Chrome's
        address bar held every Enter because the news feed far below it
        had a row saying "Share". With no field focused, anything on the
        screen counts, as before: unsure is the side to ask on."""
        field = field or next((e for e in screen.elements if e.focused), None)
        for element in screen.elements:
            if field is not None and not _beside(element, field):
                continue
            refused = element.tap and self.rules.refused(element, screen.app)
            if refused:
                # what a tap there may not do, Enter may not do either
                raise SparshError(f"enter could do what a tap would: {refused}")
            why = element.tap and self.rules.why_tap(element, screen.app)
            if why:
                return f"enter could do what {element.kind} {_quoted(element)} does ({why})"
        return None

    def open_app(self, name: str) -> Screen:
        """AN APP REOPENS WHERE IT WAS LEFT. If that was a page that can't
        be read (Settings' About page, its clock ticking), opening the app
        again only lands there again -- the phone trial watched an agent go
        home and reopen Settings for nineteen minutes. So Sparsh presses
        back, up to twice, until there is a page to read, and says so.
        Back is never held, and loses nothing."""
        package = self.which_app(name)
        self._guard(package)
        if self.device.awake()[1] and self.device.secure() is False:
            self.device.dismiss_lock()  # a swipe with no PIN: nobody's to open
        self.device.launch(package)
        screen = self._after()
        pressed = 0
        while _unread(screen) and pressed < 2:
            self.device.keys("back")
            pressed += 1
            screen = self._after()
        if pressed and not _unread(screen):
            screen.remark = (
                f"(It opened on a page that can't be read, so back was pressed "
                f"{'once' if pressed == 1 else 'twice'}. This is where that led.)"
            )
        return screen

    # -- holds ---------------------------------------------------------

    def _hold(self, action: str, why: str, target: Element | None,
              where: tuple[str, str] | None = None, **args) -> NoReturn:  # fmt: skip
        """``where`` is (app, screen) when the last look isn't the screen
        asked on (one that can't be read is never kept as the last)."""
        now = time.monotonic()
        for old in [h for h in self.holds.values() if now - h.made > HOLD_FOR]:
            del self.holds[old.id]
        app, screen = where or (self.last().app, self.last().text())
        hold = Hold(
            id="h" + secrets.token_hex(3),
            action=action,
            why=why,
            app=app,
            target=target,
            screen=screen,
            args=args,
        )
        if "picture" not in args and where is None:
            self._card(hold)
        self.holds[hold.id] = hold
        raise Held(hold)

    def _card(self, hold: Hold) -> None:
        """What the person is shown (module docstring): the screen now,
        the target's middle as a share of it, the words filled in."""
        last = self.last()
        hold.filled = tuple(
            f'{e.kind} "{_short(e.label)}"'
            for e in last.elements
            if e.type and e.label and not e.password
        )[:3]
        if self._off_limits(hold.app):
            return
        if hold.action == "tap" and hold.target is not None:
            # A target under the keyboard is shown as the yes will find it:
            # the keyboard put away (back only closes it), or the ring sits
            # on a key -- the 6P's Call button, under Gboard's number pad.
            try:
                hold.target = self._uncovered(hold.target)
            except SparshError:
                pass
        try:
            hold.card = self.device.screenshot()
        except SparshError:
            return  # the words, and the list, are still asked
        # The spot as a share of what was photographed: Android's list
        # leaves the navigation bar out, its screenshot doesn't (the ring
        # sat on Home); an iPhone's list is in points, like its touches.
        touch = getattr(self.device, "touch_size", None)
        try:
            size = (touch() if touch else picture.size(hold.card)) or last.size
        except SparshError:
            size = last.size
        width, height = size
        if hold.target is not None and width > 0 and height > 0:
            x, y = hold.target.centre
            hold.ring = (min(1000, x * 1000 // width), min(1000, y * 1000 // height))

    def held(self, hold_id: str) -> Hold:
        hold = self.holds.get(hold_id.strip())
        if hold is None or time.monotonic() - hold.made > HOLD_FOR:
            self.holds.pop(hold_id.strip(), None)
            raise SparshError(
                f"no step is waiting under {hold_id!r} (a hold lasts {HOLD_FOR // 60} "
                "minutes, and only while these tools run) -- do the step again and "
                "call confirm straight away"
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
        if hold.action == "tap_at":
            self._as_pictured(hold, "tapped")
            self._pace(hold.app)
            return self._tap_spot(hold.args["x"], hold.args["y"], hold.args["long"],
                                  hold.args["picture"])  # fmt: skip
        if hold.action == "tap":
            return self._tap(self._find(hold.target), hold.args.get("long", False))
        if "picture" in hold.args:
            self._as_pictured(hold, "typed")
        field = hold.target
        if hold.args["tap_first"]:
            field = self._find(field)
        return self._type(
            field if hold.args["tap_first"] else None,
            hold.args["text"],
            hold.args["clear"],
            hold.args["enter"],
        )

    def _as_pictured(self, hold: Hold, done: str) -> None:
        """THE SCREEN MUST STILL BE THE PICTURE. A step the person said yes
        to by looking is done only on the screen they looked at: the same
        app in front, and a new screenshot that matches the one they saw
        (a clock may tick; a page scrolled, a dialog gone, may not). A
        picture, not a reading: reading a screen that never goes still
        takes ten seconds or more, and finds nothing."""
        front = self._front()
        if front != hold.app:
            raise SparshError(
                f"the phone is in {front or 'another app'} now, not "
                f"{hold.app or 'the app it was'}; nothing was {done}"
            )
        changed = picture.changed(hold.args["picture"], self.device.screenshot())
        if changed is None or changed > CHANGED:
            raise SparshError(
                "the screen is not the one in the picture any more (it moved, or "
                f"something opened or closed); nothing was {done}. Look again"
            )

    # -- whether it is free ----------------------------------------------

    def state(self) -> dict:
        """Whether a run nobody started may use the phone now:

            in_use   the screen is on and unlocked: someone has it in hand
            locked   the lock screen is up and needs a PIN: only its person
                     can open it
            asleep   nobody has it and nothing stands in the way: the screen
                     is off with no lock, or the lock is a swipe with no PIN.
                     ``wake`` turns it on and swipes that lock away
            unknown  the phone didn't say (an iPhone says only "locked")

        A harness decides what to do about each (Dvara: wait, ask, wake).

        A LOCK WITH NO PIN IS NO ONE'S TO OPEN. A real Nexus 6P with only a
        swipe lock read as ``locked``, so a schedule asked its person to
        unlock what anything could have swiped. Its person chose no PIN;
        a PIN still asks.

        With ``SPARSH_AWAKE=always`` the screen never goes dark, so a lit,
        unlocked one is no sign of a person: it is ``asleep``, free."""
        on, locked = self.device.awake()
        secure = self.device.secure() if locked else None
        if locked and secure is False:
            state = "asleep"
        elif locked:
            state = "locked"
        elif locked is None or on is None:
            state = "unknown"
        else:
            state = "in_use" if on else "asleep"
            if state == "in_use" and _always_on():
                state = "asleep"  # lit by SPARSH_AWAKE=always, not by a person (awake.py)
        return {
            "screen": None if on is None else ("on" if on else "off"),
            "locked": locked,
            "pin": secure,
            "state": state,
        }

    def wake(self) -> dict:
        """Screen on; a lock with no PIN swiped away (Android won't
        dismiss one with a PIN). The state it led to."""
        on, locked = self.device.awake()
        if locked and self.device.secure() is False:
            self.device.dismiss_lock()
            for _ in range(10):  # the swipe lands a moment later
                if not self.device.awake()[1]:
                    break
                time.sleep(0.2)
        else:
            self.device.keys("wakeup")
        return self.state()

    # -- apps ----------------------------------------------------------

    def apps(self, like: str = "") -> list[str]:
        found = [a for a in self.device.apps() if not self._off_limits(a)]
        return [a for a in found if like.lower() in a.lower()] if like else found

    def which_app(self, name: str) -> str:
        """``settings`` -> ``com.android.settings``; a package name as is.
        An iPhone's bundle ids don't say what an app is called
        (``com.apple.Preferences``), so its device brings ``nicknames``."""
        apps = self.device.apps()
        wanted = name.strip().lower()
        nicknames = getattr(self.device, "nicknames", {})
        if wanted in nicknames:
            return nicknames[wanted]
        same = [a for a in apps if a.lower() == wanted]
        if same:
            return same[0]
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

    def _front(self) -> str:
        try:
            return self.device.front_app()
        except SparshError:
            return ""

    def _off_limits(self, app: str) -> bool:
        return self.rules is not None and self.rules.forbidden(app)

    def _guard(self, app: str) -> None:
        if self._off_limits(app):
            raise SparshError(f"{app} is off limits: the person's rules keep the agent out of it")

    def _has_last(self) -> bool:
        return (self.folder / "last.xml").exists()


_UNREAD = "Done. But the screen it led to can't be read: "

_OFF_LIMITS = (
    "(this app is off limits: the person's rules keep the agent out of it, so "
    "nothing on it is shown. Press back or home to leave.)"
)

#: Apps that draw the lock screen (Android's system bar; an iPhone's home).
_LOCK_HOSTS = {"com.android.systemui", "com.apple.springboard"}

_LOCKED = (
    "(The phone is locked: this is its lock screen, not the app asked for. "
    "Ask its person to unlock it, then look again.)"
)


def _unread(screen: Screen) -> bool:
    return screen.note.startswith(_UNREAD)


def _beside(element: Element, field: Element) -> bool:
    """Overlapping the field's row, stretched by the field's height."""
    _, top, _, bottom = field.bounds
    reach = bottom - top
    return element.bounds[1] < bottom + reach and element.bounds[3] > top - reach


def _short(words: str, most: int = 200) -> str:
    return words if len(words) <= most else words[: most - 1] + "…"


def _quoted(element: Element) -> str:
    return '"' + element.label + '"' if element.label else f"number {element.n}"


def _safe(serial: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in serial) or "phone"
