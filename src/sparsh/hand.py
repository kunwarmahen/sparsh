"""The person's own hand on the phone: what they did, between two looks.

A person teaching their agent a job by SHOWING it (Yantra's ``/learn
watch``) does each step with their own finger and says "next". Sparsh
sees only what it does itself (log.py), so without this the agent would
be told "next" and see a new screen with no idea how it got there.

    watch_phone   the screen now, kept as "before"; on Android, touches
                  start being read
    watched       what the person did since, and the screen now -- which
                  becomes the next "before"

ANDROID READS THE FINGER, AGAINST THE SCREEN AS IT WAS. ``adb shell
getevent -lt`` streams the touchscreen's raw events; each touch, from
finger down to finger up, is one gesture: a tap, a long press or a
swipe. A tap's spot is matched to the smallest thing on the "before"
screen that holds it, so the agent is told ``tapped 4 item "Mom"``, not a
pair of numbers. No accessibility service, nothing installed on the
phone, and nothing that fights ``uiautomator dump`` for the screen.

ONLY THE FIRST STEP CAN BE NAMED. After a tap the screen moves, and the
screen it moved to was never read -- reading it after every touch would
race the person's next one. So a gesture after the first that changed
the screen is said as what it is (a tap, at a spot) and plainly not
named. Touches on the keyboard change no screen: they are counted as
typing, and the words typed are read off the screen afterwards, never
off the keys -- a password typed while showing is a row of dots, as it
is on the screen.

AN iPHONE SHOWS NO FINGERS. WDA drives the phone; it cannot watch it.
There ``watched`` gives both screens, before and after, and says so: the
agent works out the step and asks the person whether it guessed right.

THE PERSON'S STEPS ARE WRITTEN DOWN TOO, in the same log, by "you":
``/phone log`` shows the walk-through as well as the agent's steps.

THE SCREEN IS ASSUMED UPRIGHT. A touch is scaled from the touchscreen's
own range to the screen's size as ``wm size`` gives it; a phone turned
sideways while showing would put the spot in the wrong place.
"""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Iterable
from dataclasses import dataclass

from sparsh import log
from sparsh.screen import Element, Screen

#: A finger that moved less than this many pixels tapped; more, swiped.
MOVED = 40
#: A finger held at least this long, unmoved, long-pressed.
LONG_S = 0.6
#: How much of the "before" screen an iPhone's ``watched`` shows.
BEFORE_CHARS = 2500

_EVENT = re.compile(r"\[\s*([\d.]+)\]\s+(?:\S+:\s+)?(EV_\w+)\s+(\w+)\s+(\w+)")
_RANGE = re.compile(r"(ABS_MT_POSITION_[XY])\s*:.*?max (\d+)")
_SIZE = re.compile(r"(Physical|Override) size: (\d+)x(\d+)")


@dataclass(frozen=True)
class Gesture:
    """One finger, down to up, in screen pixels."""

    kind: str  # tap, long_press, swipe
    x: int
    y: int
    x2: int
    y2: int

    def direction(self) -> str:
        dx, dy = self.x2 - self.x, self.y2 - self.y
        if abs(dy) >= abs(dx):
            return "up" if dy < 0 else "down"
        return "left" if dx < 0 else "right"


def gestures(lines: Iterable[str], scale: tuple[float, float] = (1.0, 1.0)) -> list[Gesture]:
    """``getevent -lt`` lines as the gestures they make. Only the first
    finger (slot 0) is followed: a pinch is read as its first finger."""
    out: list[Gesture] = []
    slot, down = 0, False
    start: list[float | None] = [None, None]
    at: list[float | None] = [None, None]
    began = 0.0
    sx, sy = scale

    def finish(when: float) -> None:
        if start[0] is None or start[1] is None:
            return
        x, y = int(start[0] * sx), int(start[1] * sy)
        x2 = int((at[0] if at[0] is not None else start[0]) * sx)
        y2 = int((at[1] if at[1] is not None else start[1]) * sy)
        if abs(x2 - x) + abs(y2 - y) >= MOVED:
            kind = "swipe"
        else:
            kind = "long_press" if when - began >= LONG_S else "tap"
        out.append(Gesture(kind, x, y, x2, y2))

    for line in lines:
        match = _EVENT.search(line)
        if match is None:
            continue
        when, kind, code, value = float(match[1]), match[2], match[3], match[4]
        if kind == "EV_ABS" and code == "ABS_MT_SLOT":
            slot = int(value, 16)
            continue
        if slot != 0:
            continue
        if code == "ABS_MT_TRACKING_ID" or (code == "BTN_TOUCH" and kind == "EV_KEY"):
            lifted = value in ("ffffffff", "UP")
            if not lifted and not down:
                down, began = True, when
                start[:], at[:] = [None, None], [None, None]
            elif lifted and down:
                down = False
                finish(when)
            continue
        if down and kind == "EV_ABS" and code in ("ABS_MT_POSITION_X", "ABS_MT_POSITION_Y"):
            i = 0 if code.endswith("X") else 1
            number = float(int(value, 16))
            if start[i] is None:
                start[i] = number
            at[i] = number
    return out


def scale_of(capabilities: str, size: str) -> tuple[float, float]:
    """Touchscreen units to pixels, from ``getevent -lp`` and ``wm size``."""
    ranges = {m[1]: int(m[2]) for m in _RANGE.finditer(capabilities)}
    sizes = {m[1]: (int(m[2]), int(m[3])) for m in _SIZE.finditer(size)}
    width, height = sizes.get("Override") or sizes.get("Physical") or (0, 0)
    max_x, max_y = ranges.get("ABS_MT_POSITION_X"), ranges.get("ABS_MT_POSITION_Y")
    if not (width and height and max_x and max_y):
        return 1.0, 1.0
    return width / (max_x + 1), height / (max_y + 1)


def touchscreen(capabilities: str) -> str | None:
    """Which ``/dev/input/event*`` is the touchscreen, from ``getevent -lp``."""
    device = None
    for line in capabilities.splitlines():
        if line.startswith("add device"):
            device = line.split(":", 1)[1].strip()
        elif "ABS_MT_POSITION_X" in line and device:
            return device
    return None


class TouchFeed:
    """``getevent -lt`` running behind, its lines kept until taken."""

    def __init__(self, command: list[str], scale: tuple[float, float]) -> None:
        self.command = command
        self.scale = scale
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        self.stop()
        with self._lock:
            self._lines = []
        self._proc = subprocess.Popen(self.command, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._read, args=(self._proc,), daemon=True,
                         name="sparsh-hand").start()

    def _read(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            with self._lock:
                self._lines.append(line)

    def take(self) -> list[Gesture]:
        with self._lock:
            lines, self._lines = self._lines, []
        return gestures(lines, self.scale)

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None


def under(screen: Screen, x: int, y: int) -> Element | None:
    """The smallest thing on ``screen`` that holds the spot."""
    holding = [e for e in screen.elements
               if e.bounds[0] <= x < e.bounds[2] and e.bounds[1] <= y < e.bounds[3]]
    return min(holding, key=lambda e: (e.bounds[2] - e.bounds[0]) * (e.bounds[3] - e.bounds[1]),
               default=None)


def _on_keyboard(area: tuple[int, int, int, int] | None, g: Gesture) -> bool:
    return (area is not None and g.kind == "tap"
            and area[0] <= g.x < area[2] and area[1] <= g.y < area[3])


def described(found: list[Gesture], before: Screen,
              keyboard: tuple[int, int, int, int] | None) -> list[tuple[str, str, str | None]]:
    """Each step as (action, words for the agent, the line it was on).
    Keys in a row are one step of typing; only steps before the screen
    first moved are named from ``before``."""
    steps: list[tuple[str, str, str | None]] = []
    still = True        # the screen is still the one read as "before"
    keys = 0

    def typed() -> None:
        nonlocal keys
        if keys:
            steps.append(("typing", f"typed on the keyboard ({keys} key(s); what it "
                                    f"says is on the screen now)", None))
            keys = 0

    for g in found:
        if _on_keyboard(keyboard, g):
            keys += 1
            continue
        typed()
        if g.kind == "swipe":
            steps.append(("swipe", f"swiped {g.direction()}", None))
            still = False
            continue
        verb = "long-pressed" if g.kind == "long_press" else "tapped"
        target = under(before, g.x, g.y) if still else None
        if target is not None:
            steps.append((g.kind, f"{verb} {target.line()}", target.line()))
        else:
            spot = f"the screen at {g.x},{g.y}"
            why = " (the screen had moved on by then, so what was there wasn't read)" \
                if not still else ""
            steps.append((g.kind, f"{verb} {spot}{why}", None))
        still = False
    typed()
    return steps


class Watch:
    """One phone's walk-through: the screen last seen, and the finger."""

    def __init__(self) -> None:
        self.before: Screen | None = None
        self.feed: TouchFeed | None = None

    def start(self, phone) -> Screen:
        """``watch_phone``: what the person starts from."""
        if self.feed is not None:
            self.feed.stop()
        feed = getattr(phone.device, "touch_feed", None)
        self.feed = feed() if callable(feed) else None
        if self.feed is not None:
            self.feed.start()
        self.before = phone.see()
        return self.before

    def since(self, phone) -> str:
        """``watched``: what they did since the last look, and the screen now."""
        if self.before is None:
            self.start(phone)
            return ("I wasn't watching yet, so I started now; nothing before this is "
                    "known. Ask them to do the step again, then call watched.\n"
                    "The phone now:\n" + (self.before.text() if self.before else ""))
        before = self.before
        found = self.feed.take() if self.feed is not None else None
        keyboard = None
        if found:
            try:
                keyboard = phone.device.keyboard_area()
            except Exception:  # noqa: BLE001 -- a help to the reading, never needed
                keyboard = None
        now = phone.see()
        self.before = now
        if found is None:
            return _without_hand(before, now)
        steps = described(found, before, keyboard)
        for action, words, on in steps:
            _write(phone, action, words, on, now.app)
        if not steps:
            moved = before.text() != now.text()
            head = ("No touch was seen, but the screen changed (a notification, a page "
                    "that loaded, or a button on the side):" if moved
                    else "Nothing was touched, and the screen is the same:")
            return f"{head}\nThe phone now:\n{now.text()}"
        lines = [f"What the person did since the last look (on {before.app}):"]
        lines += [f"{n}. {words}" for n, (_, words, _) in enumerate(steps, start=1)]
        return "\n".join(lines) + "\nThe phone now:\n" + now.text()

    def stop(self) -> None:
        if self.feed is not None:
            self.feed.stop()
        self.feed, self.before = None, None


def _without_hand(before: Screen, now: Screen) -> str:
    """An iPhone's answer: both screens, for the agent to compare."""
    if before.text() == now.text():
        return ("This phone doesn't show where it is touched, and its screen is the "
                "same as at the last look: nothing seems to have been done.\n"
                "The phone now:\n" + now.text())
    shown = before.text()
    if len(shown) > BEFORE_CHARS:
        shown = shown[:BEFORE_CHARS] + "\n(... more of the screen before)"
    return ("This phone doesn't show where it is touched, so compare the two "
            "screens to tell what the person did -- and ask them if unsure.\n"
            f"The phone before:\n{shown}\n\nThe phone now:\n{now.text()}")


def _write(phone, action: str, words: str, on: str | None, app: str) -> None:
    log.noted(phone, "you", action, on=on, said=words, app=app)
