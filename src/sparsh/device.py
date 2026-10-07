"""The phone itself: a few things it can be asked to do, and nothing more.

:class:`AdbDevice` drives a real Android phone, or the emulator, through
``adb`` -- the program Android's own platform-tools install. Nothing is
installed on the phone. What each method runs:

    dump        uiautomator dump /dev/tty         the screen, as XML
    screenshot  screencap -p                      a PNG
    tap         input tap X Y
    long_press  input swipe X Y X Y 800           a swipe that doesn't move
    swipe       input swipe X1 Y1 X2 Y2 MS
    type_text   input text '...'                  plain ASCII only (below)
    keys        input keyevent KEYCODE_...
    launch      monkey -p PKG -c ...LAUNCHER 1    the app's front door
    apps        cmd package query-activities      apps with a front door

The methods take coordinates; numbers from the screen list are turned
into coordinates one level up (phone.py), so a backend never has to
know about them. :class:`sparsh.fake.FakeDevice` is the same shape with
saved screens, for tests, and :class:`sparsh.iphone.WdaDevice` is an
iPhone -- picked when the phone's name is a web address.

TYPING. ``input text`` takes one shell word on the phone: it is quoted
here, and a space is sent as ``%s`` (which ``input`` turns back into a
space). It cannot type letters outside plain ASCII -- that needs a
keyboard app on the phone, a later slice -- so those are refused with a
sentence rather than typed wrong.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Protocol

from sparsh import SparshError
from sparsh.iphone import WdaDevice, is_wda
from sparsh.screen import ScreenUnreadable

#: Names a model (or a person) may use for a key -> Android's key code.
KEYS = {
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "enter": "KEYCODE_ENTER",
    "recent": "KEYCODE_APP_SWITCH",
    "delete": "KEYCODE_DEL",
    "tab": "KEYCODE_TAB",
    "search": "KEYCODE_SEARCH",
    "end": "KEYCODE_MOVE_END",
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
}


class Device(Protocol):
    serial: str

    def dump(self) -> str: ...
    def screenshot(self) -> bytes: ...
    def tap(self, x: int, y: int) -> None: ...
    def long_press(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None: ...
    def type_text(self, text: str) -> None: ...
    def keys(self, *names: str) -> None: ...
    def launch(self, package: str) -> None: ...
    def apps(self) -> list[str]: ...


@dataclass(frozen=True)
class Attached:
    """One line of ``adb devices -l``."""

    serial: str
    state: str  # device, unauthorized, offline
    model: str = ""

    def line(self) -> str:
        note = {
            "unauthorized": "  (unlock the phone and allow USB debugging)",
            "offline": (
                "  (not answering -- start WebDriverAgent on it)"
                if is_wda(self.serial)
                else "  (not answering -- unplug it and plug it back in)"
            ),
        }.get(self.state, "")
        return f"{self.serial}  {self.model or '?'}  {self.state}{note}"


def adb_path() -> str:
    found = os.environ.get("SPARSH_ADB") or shutil.which("adb")
    if not found:
        home = os.environ.get("ANDROID_HOME") or os.path.expanduser("~/Android/Sdk")
        candidate = os.path.join(home, "platform-tools", "adb")
        if os.access(candidate, os.X_OK):
            return candidate
        raise SparshError(
            "adb is not installed. It comes with Android's platform-tools: "
            "`sudo apt install adb`, or Android Studio's SDK (set ANDROID_HOME)."
        )
    return found


def attached(adb: str | None = None) -> list[Attached]:
    out = _run([adb or adb_path(), "devices", "-l"]).stdout.decode()
    found = []
    for row in out.splitlines()[1:]:
        parts = row.split()
        if len(parts) < 2:
            continue
        model = next((p.partition(":")[2] for p in parts if p.startswith("model:")), "")
        found.append(Attached(parts[0], parts[1], model))
    return found


def iphones() -> list[Attached]:
    """The iPhone named by ``$SPARSH_WDA``, if any, and whether it answers."""
    url = os.environ.get("SPARSH_WDA", "")
    if not is_wda(url):
        return []
    try:
        WdaDevice(url, timeout=5).status()
        state = "device"
    except SparshError:
        state = "offline"
    return [Attached(url, state, "iPhone")]


def pick(serial: str | None = None, adb: str | None = None) -> Device:
    """The phone to use: the one named, or the only one there is.

    A name that is a web address is an iPhone's WebDriverAgent
    (iphone.py); so is ``$SPARSH_WDA`` when nothing else is named."""
    serial = serial or os.environ.get("ANDROID_SERIAL") or os.environ.get("SPARSH_WDA") or None
    if is_wda(serial):
        return WdaDevice(serial)
    adb = adb or adb_path()
    phones = attached(adb)
    if serial:
        match = [p for p in phones if p.serial == serial]
        if not match:
            raise SparshError(f"no phone called {serial} is attached (`sparsh devices` lists them)")
        chosen = match[0]
    else:
        if not phones:
            raise SparshError(
                "no phone is attached. Plug one in with USB debugging on, "
                "or start the emulator, then `sparsh devices`."
            )
        if len(phones) > 1:
            names = ", ".join(p.serial for p in phones)
            raise SparshError(f"more than one phone is attached ({names}); choose with --serial")
        chosen = phones[0]
    if chosen.state != "device":
        raise SparshError(f"the phone is attached but not ready: {chosen.line()}")
    return AdbDevice(chosen.serial, adb)


class AdbDevice:
    def __init__(self, serial: str, adb: str | None = None) -> None:
        self.serial = serial
        self.adb = adb or adb_path()

    def _shell(self, *args: str, timeout: float = 30) -> str:
        done = _run([self.adb, "-s", self.serial, "shell", *args], timeout=timeout)
        return done.stdout.decode(errors="replace")

    def dump(self) -> str:
        # An animating screen (a video, a spinner) makes uiautomator give
        # up waiting for it to be still; one more try usually lands.
        said = ""
        for attempt in range(2):
            done = _run(
                [self.adb, "-s", self.serial, "exec-out", "uiautomator", "dump", "/dev/tty"],
                timeout=30,
            )
            out = done.stdout.decode(errors="replace")
            if "</hierarchy>" in out:
                return out
            said = (out + done.stderr.decode(errors="replace")).strip()
            if attempt == 0:
                time.sleep(1)
        if "idle state" in said:
            raise ScreenUnreadable(
                "the screen keeps moving (a video or animation), so the phone "
                "can't describe it -- pause it, or take a screenshot instead"
            )
        raise ScreenUnreadable(f"the phone did not describe its screen ({said or 'no answer'})")

    def screenshot(self) -> bytes:
        done = _run([self.adb, "-s", self.serial, "exec-out", "screencap", "-p"], timeout=30)
        if not done.stdout.startswith(b"\x89PNG"):
            raise SparshError("the phone did not send a screenshot")
        return done.stdout

    def tap(self, x: int, y: int) -> None:
        self._shell("input", "tap", str(x), str(y))

    def long_press(self, x: int, y: int) -> None:
        self._shell("input", "swipe", str(x), str(y), str(x), str(y), "800")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self._shell("input", "swipe", *(str(v) for v in (x1, y1, x2, y2, ms)))

    def type_text(self, text: str) -> None:
        for chunk in typeable(text):
            self._shell("input", "text", chunk)

    def keys(self, *names: str) -> None:
        self._shell("input", "keyevent", *(key_code(n) for n in names))

    def launch(self, package: str) -> None:
        out = self._shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        if "No activities found" in out:
            raise SparshError(f"{package} has no app to open on this phone")

    def apps(self) -> list[str]:
        out = self._shell(
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        )
        found = re.findall(r"^\s*([\w.]+)/", out, flags=re.MULTILINE)
        return sorted(set(found))


def key_code(name: str) -> str:
    code = KEYS.get(name.lower().strip())
    if code is None:
        raise SparshError(f"no key called {name!r} (keys: {', '.join(KEYS)})")
    return code


def typeable(text: str) -> list[str]:
    """``text`` as shell words for ``input text``, or a sentence why not."""
    if not text:
        return []
    odd = sorted({c for c in text if not (32 <= ord(c) < 127)})
    if odd:
        shown = "".join(odd[:5]).encode("unicode_escape").decode()
        raise SparshError(
            f"can't type {shown!r} yet: only plain ASCII letters, digits and "
            "punctuation can be typed for now"
        )
    if "%s" in text:
        raise SparshError(
            "can't type the two letters '%s' together (the phone reads them as a space)"
        )
    # Long text in one go can be dropped by the phone; send it in pieces.
    pieces = [text[i : i + 200] for i in range(0, len(text), 200)]
    return ["'" + p.replace(" ", "%s").replace("'", "'\\''") + "'" for p in pieces]


def _run(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SparshError(f"the phone took longer than {timeout:.0f}s to answer") from e
    except OSError as e:
        raise SparshError(f"could not run adb ({e})") from e
    if done.returncode != 0:
        said = (
            done.stderr.decode(errors="replace").strip()
            or done.stdout.decode(errors="replace").strip()
        )
        if "not found" in said and "device" in said:
            raise SparshError("the phone went away (unplugged, or the emulator stopped)")
        raise SparshError(f"adb said: {said or f'exit {done.returncode}'}")
    return done
