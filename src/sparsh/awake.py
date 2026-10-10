"""The screen kept on while the agent works the phone.

    SPARSH_AWAKE=working   the default: on while working, then the person's own
    SPARSH_AWAKE=always    the screen never sleeps: a phone set aside for the agent
    SPARSH_AWAKE=off       Sparsh leaves the screen's timeout alone

A SCREEN THAT SLEEPS MID-TASK LOCKS THE TASK OUT. A local model thinks
for longer than a phone's usual thirty seconds between steps, and an
Android screen that goes dark puts its lock screen up. With a PIN that
lock is the person's alone, so the agent stops and asks them to unlock a
phone they never touched -- a real Nexus 6P, renaming itself from
Telegram, did exactly that. Sparsh can't open a PIN; it can keep the
screen from going dark in the first place.

ON WHILE WORKING, THEN THE PERSON'S OWN. The first step of a spell of
work raises Android's screen timeout to ten minutes (and swipes away a
lock with no PIN, if the screen had already gone); each later step
keeps the spell going. Two minutes after the last step, or when the
server stops, the person's own timeout is put back -- but only if the
timeout is still the one Sparsh set: a person who changed it meanwhile
keeps theirs. Their own value is written in the phone's folder before
anything is changed (``~/.sparsh/phones/<serial>/screen-timeout``), so
a server that was killed puts it back the next time one starts.

ALWAYS IS A PHONE SET ASIDE FOR THE AGENT. The screen never times out,
until ``SPARSH_AWAKE`` says otherwise. A lit, unlocked screen is then
no sign that someone has the phone in hand, so ``state`` says ``asleep``
-- free for a schedule -- where it would say ``in_use``. Pick it only
for a phone nobody carries.

Reads count as work: a model that looks and thinks is still working.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from sparsh import SparshError
from sparsh.device import Device

MODES = ("working", "always", "off")
#: The screen's timeout while working, and how long after the last step
#: the person's own comes back.
WORKING_MS = 10 * 60 * 1000
IDLE_SECONDS = 120.0
#: Android's largest timeout: the screen never sleeps.
NEVER_MS = 2147483647
FILE = "screen-timeout"


def mode(raw: str | None = None) -> str:
    """``$SPARSH_AWAKE``, checked: a word Sparsh doesn't know is an error,
    never a guess."""
    raw = os.environ.get("SPARSH_AWAKE", "") if raw is None else raw
    word = raw.strip().lower() or "working"
    if word not in MODES:
        raise SparshError(f"SPARSH_AWAKE is {raw!r}; it is one of {', '.join(MODES)}")
    return word


class Awake:
    """One server's keeper of one phone's screen (the module docstring)."""

    def __init__(self, how: str = "working", idle: float = IDLE_SECONDS) -> None:
        self.how = how
        self.idle = idle
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._device: Device | None = None
        self._folder: Path | None = None

    def step(self, device: Device, folder: Path) -> None:
        """Before each tool call: keep (or start) the spell."""
        with self._lock:
            self._cancel()
            if self._device is not None and self._device.serial != device.serial:
                self._put_back()  # another phone now: the last one gets its own back
            self._device, self._folder = device, folder
            if self.how == "off":
                self._put_back()  # left over from a killed server or from always
                return
            want = NEVER_MS if self.how == "always" else WORKING_MS
            now = device.screen_timeout()
            if now is None:
                return  # this phone doesn't say (an iPhone): nothing to keep
            if now != want:
                saved = folder / FILE
                if not saved.exists() and now not in (WORKING_MS, NEVER_MS):
                    folder.mkdir(parents=True, exist_ok=True)
                    saved.write_text(f"{now}\n")
                device.set_screen_timeout(want)
                on, locked = device.awake()
                if (not on or locked) and device.secure() is False:
                    device.dismiss_lock()  # gone dark already: no PIN, nobody's to open
            if self.how == "working":
                self._timer = threading.Timer(self.idle, self.rest)
                self._timer.daemon = True
                self._timer.start()

    def rest(self) -> None:
        """The spell is over (idle, or the server stops)."""
        with self._lock:
            self._cancel()
            if self.how != "always":
                self._put_back()

    def _put_back(self) -> None:
        device, folder = self._device, self._folder
        if device is None or folder is None:
            return
        saved = folder / FILE
        try:
            own = int(saved.read_text().strip())
        except (OSError, ValueError):
            return
        try:
            if device.screen_timeout() in (WORKING_MS, NEVER_MS):
                device.set_screen_timeout(own)
        except SparshError:
            return  # the phone went away: put back when it is next seen
        saved.unlink(missing_ok=True)

    def _cancel(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
