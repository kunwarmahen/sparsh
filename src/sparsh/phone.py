"""Numbers in, taps out -- and never a tap on something that moved.

:class:`Phone` is what the CLI (and later the MCP server) holds. It
keeps the last screen it showed, so that ``tap(7)`` means the 7 the
agent (or the person) actually read:

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
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from sparsh import SparshError
from sparsh.device import Device
from sparsh.screen import Element, Screen, read

#: Seconds to let the phone react before looking again.
SETTLE = 0.8

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


def state_root(given: str | os.PathLike | None = None) -> Path:
    return Path(given or os.environ.get("SPARSH_STATE") or Path.home() / ".sparsh")


class Phone:
    def __init__(
        self, device: Device, state: str | os.PathLike | None = None, settle: float = SETTLE
    ) -> None:
        self.device = device
        self.settle = settle
        self.folder = state_root(state) / "phones" / _safe(device.serial)

    # -- seeing --------------------------------------------------------

    def look(self, shot: str | os.PathLike | None = None) -> Screen:
        xml = self.device.dump()
        screen = read(xml)
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "last.xml").write_text(xml)
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
        now = self.look()
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
        if not target.enabled:
            raise SparshError(f'{n} ({target.kind} "{target.label}") is switched off on the phone')
        x, y = target.centre
        if long:
            self.device.long_press(x, y)
        else:
            self.device.tap(x, y)
        return self._after()

    def type(
        self, text: str, into: int | None = None, clear: bool = False, enter: bool = False
    ) -> Screen:
        field = None
        if into is not None:
            field = self._still_there(into)
            if not field.type:
                raise SparshError(
                    f'{into} ({field.kind} "{field.label}") is not a field to type in'
                )
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
            width, height = (self.last() if self._has_last() else self.look()).size
            left, top, right, bottom = 0, 0, width, height
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
        self.device.keys(*names)
        return self._after()

    def open_app(self, name: str) -> Screen:
        self.device.launch(self.which_app(name))
        return self._after()

    # -- apps ----------------------------------------------------------

    def apps(self, like: str = "") -> list[str]:
        found = self.device.apps()
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
        raise SparshError(f"no app matches {name!r}. Apps on this phone: {', '.join(apps)}")

    def _has_last(self) -> bool:
        return (self.folder / "last.xml").exists()


def _safe(serial: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in serial) or "phone"
