"""The phone itself: a few things it can be asked to do, and nothing more.

:class:`AdbDevice` drives a real Android phone, or the emulator, through
``adb`` -- the program Android's own platform-tools install. Nothing is
installed on the phone. What each method runs:

    dump        uiautomator dump /dev/tty         the screen, as XML
    screenshot  screencap -p                      a PNG
    tap         input tap X Y
    long_press  input swipe X Y X Y 800           a swipe that doesn't move
    swipe       input swipe X1 Y1 X2 Y2 MS
    type_text   input text '...'                  plain ASCII (below)
                am broadcast -a ADB_INPUT_B64     anything else, via ADBKeyBoard
    keys        input keyevent KEYCODE_...
    launch      monkey -p PKG -c ...LAUNCHER 1    the app's front door
    apps        cmd package query-activities      apps with a front door
    front_app   dumpsys activity activities       the app in front, even when
                                                  its screen can't be read

OVER WI-FI. A phone with wireless debugging on is reached by address
(``adb pair`` once, then ``adb connect``). ``$SPARSH_CONNECT`` names
such phones, and ``attached`` connects to any that adb has forgotten
before listing: a restarted computer, or a container started fresh,
finds the phone again by itself, as a cable would.

The methods take coordinates; numbers from the screen list are turned
into coordinates one level up (phone.py), so a backend never has to
know about them. :class:`sparsh.fake.FakeDevice` is the same shape with
saved screens, for tests, and :class:`sparsh.iphone.WdaDevice` is an
iPhone -- picked when the phone's name is a web address.

TYPING. ``input text`` takes one shell word on the phone: it is quoted
here, and a space is sent as ``%s`` (which ``input`` turns back into a
space). It cannot type letters outside plain ASCII -- on Android 15 it
crashes on them -- and the phone's clipboard has no shell command.

So anything else (é, नमस्ते, emoji, a literal ``%s``) goes through
ADBKeyBoard, a small open-source keyboard app that types what adb
broadcasts to it. Sparsh never installs it: the person does, once
(SETUP.md, "Typing other languages"). For each such piece of text
Sparsh switches to it, types, and switches back to the person's own
keyboard, leaving the keyboard list as it found it. Without it, the
text is refused with a sentence rather than typed wrong.
"""

from __future__ import annotations

import base64
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
    "wakeup": "KEYCODE_WAKEUP",
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    # Not keys: the panels pulled down from the top of the screen. Android 8
    # keeps Do Not Disturb's switch only there, and no tap opens them.
    "notifications": "statusbar expand-notifications",
    "quick_settings": "statusbar expand-settings",
}

#: ADBKeyBoard (github.com/senzhk/ADBKeyBoard), for what `input` can't type.
KEYBOARD_APP = "com.android.adbkeyboard"
KEYBOARD = KEYBOARD_APP + "/.AdbIME"


class Device(Protocol):
    serial: str

    def dump(self, retry: bool = True) -> str: ...
    def screenshot(self) -> bytes: ...
    def tap(self, x: int, y: int) -> None: ...
    def long_press(self, x: int, y: int) -> None: ...
    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None: ...
    def check_text(self, text: str) -> None: ...
    def type_text(self, text: str) -> None: ...
    def keys(self, *names: str) -> None: ...
    def launch(self, package: str) -> None: ...
    def apps(self) -> list[str]: ...
    def front_app(self) -> str: ...
    def awake(self) -> tuple[bool | None, bool | None]: ...
    def keyboard_area(self) -> tuple[int, int, int, int] | None: ...


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
    adb = adb or adb_path()
    out = _run([adb, "devices", "-l"]).stdout.decode()
    if over_wifi():
        # A phone named in $SPARSH_CONNECT and not listed is connected to
        # first: after a restart, or a container's, adb has forgotten it.
        listed = {row.split()[0] for row in out.splitlines()[1:] if row.split()}
        missing = [a for a in over_wifi() if a not in listed]
        for address in missing:
            connect(address, adb)
        if missing:
            out = _run([adb, "devices", "-l"]).stdout.decode()
    found = []
    for row in out.splitlines()[1:]:
        parts = row.split()
        if len(parts) < 2:
            continue
        model = next((p.partition(":")[2] for p in parts if p.startswith("model:")), "")
        found.append(Attached(parts[0], parts[1], model))
    return found


def over_wifi() -> list[str]:
    """The phones named in ``$SPARSH_CONNECT`` (``192.168.1.23:41234``,
    comma-separated): reached over the network, no cable."""
    raw = os.environ.get("SPARSH_CONNECT", "")
    return [a.strip() for a in raw.split(",") if a.strip()]


def connect(address: str, adb: str | None = None) -> str:
    """``adb connect``: adb's own words, or a sentence why not. Never
    raises for a phone that isn't answering -- it is listed as not there."""
    if not re.fullmatch(r"[A-Za-z0-9.\-\[\]:]{1,80}:\d{1,5}", address):
        raise SparshError(f"{address!r} is not an address and port (192.168.1.23:41234)")
    try:
        done = subprocess.run(
            [adb or adb_path(), "connect", address], capture_output=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return f"{address} did not answer in 10s (is the phone on this network?)"
    except OSError as e:
        raise SparshError(f"could not run adb ({e})") from e
    return (done.stdout + done.stderr).decode(errors="replace").strip()


def pair(address: str, code: str, adb: str | None = None) -> str:
    """``adb pair``, once per computer: the phone's "Pair device with
    pairing code" screen shows both. Afterwards this computer's adb key
    is trusted over Wi-Fi."""
    if not re.fullmatch(r"\d{6}", code.strip()):
        raise SparshError("the pairing code is the six digits the phone shows")
    done = _run([adb or adb_path(), "pair", address, code.strip()], timeout=30)
    return (done.stdout + done.stderr).decode(errors="replace").strip()


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
        self._keyboard = False  # only a yes is kept: it may be installed later

    def _shell(self, *args: str, timeout: float = 30) -> str:
        done = _run([self.adb, "-s", self.serial, "shell", *args], timeout=timeout)
        return done.stdout.decode(errors="replace")

    def dump(self, retry: bool = True) -> str:
        # An animating screen (a video, a spinner) makes uiautomator give
        # up waiting for it to be still; one more try usually lands.
        # ``retry=False`` when this screen is already known not to: each
        # try waits about twelve seconds for a stillness that won't come.
        said = ""
        for attempt in range(2 if retry else 1):
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
            # Something on it never stops changing: a video, an animation,
            # or a clock ticking every second (Settings' About page counts
            # its "Up time"). Waiting longer doesn't help; leaving does.
            raise ScreenUnreadable(
                "the screen keeps changing (a video, an animation, or a clock "
                "ticking -- Settings' About page does), so the phone can't "
                "describe it. Press back to leave this page, and find what you "
                "need another way (a search, a different page)"
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

    def check_text(self, text: str) -> None:
        """Raise, before anything is done, if ``text`` can't be typed here."""
        if not plain(text) and not self.has_keyboard():
            raise needs_keyboard(text)

    def has_keyboard(self) -> bool:
        if not self._keyboard:
            out = self._shell("pm", "list", "packages", KEYBOARD_APP)
            self._keyboard = f"package:{KEYBOARD_APP}" in out.split()
        return self._keyboard

    def type_text(self, text: str) -> None:
        if plain(text):
            for chunk in typeable(text):
                self._shell("input", "text", chunk)
            return
        self.check_text(text)
        was = self._shell("settings", "get", "secure", "default_input_method").strip()
        listed = self._shell("ime", "list", "-s").split()
        if was != KEYBOARD:
            if KEYBOARD not in listed:
                self._shell("ime", "enable", KEYBOARD)
            self._shell("ime", "set", KEYBOARD)
            time.sleep(0.5)  # for it to take over the field
        try:
            for piece in pieces(text):
                msg = base64.b64encode(piece.encode()).decode()
                self._shell("am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", msg)
        finally:
            # Back to the person's own keyboard, and off the list if it wasn't on it.
            if was != KEYBOARD:
                if was and was != "null":
                    self._shell("ime", "set", was)
                if KEYBOARD not in listed:
                    self._shell("ime", "disable", KEYBOARD)

    def keys(self, *names: str) -> None:
        codes: list[str] = []
        for code in (key_code(n) for n in names):
            if code.startswith("statusbar "):
                if codes:  # in order: the keys before go first
                    self._shell("input", "keyevent", *codes)
                    codes = []
                self._shell("cmd", *code.split())
            else:
                codes.append(code)
        if codes:
            self._shell("input", "keyevent", *codes)

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

    def awake(self) -> tuple[bool | None, bool | None]:
        """(screen on?, locked?), from Android's own power and window
        state; None for what it didn't say."""
        power = self._shell("dumpsys", "power")
        found = re.search(r"mWakefulness=(\w+)", power)
        on = None if not found else found.group(1) == "Awake"
        window = self._shell("dumpsys", "window")
        found = re.search(r"isKeyguardShowing=(true|false)", window) or re.search(
            r"mDreamingLockscreen=(true|false)", window
        )
        locked = None if not found else found.group(1) == "true"
        return on, locked

    def keyboard_area(self) -> tuple[int, int, int, int] | None:
        """Where the on-screen keyboard is (left, top, right, bottom), or
        None when it isn't up or Android didn't say. The screen's list
        leaves the keyboard out: what it covers is still listed, and a tap
        there lands on a key."""
        if "mInputShown=true" not in self._shell("dumpsys", "input_method"):
            return None
        window = self._shell("dumpsys", "window", "windows")
        start = window.find(" InputMethod}:")
        if start < 0:
            return None
        end = window.find("Window #", start)
        found = re.search(
            r"touchable region=SkRegion\(\((\d+),(\d+),(\d+),(\d+)\)\)",
            window[start : end if end > 0 else None],
        )
        if not found:
            return None
        left, top, right, bottom = map(int, found.groups())
        return left, top, right, bottom

    def front_app(self) -> str:
        out = self._shell("dumpsys", "activity", "activities")
        found = re.search(r"topResumedActivity=ActivityRecord\{\S+ \S+ ([\w.]+)/", out)
        return found.group(1) if found else ""


def key_code(name: str) -> str:
    code = KEYS.get(name.lower().strip())
    if code is None:
        raise SparshError(f"no key called {name!r} (keys: {', '.join(KEYS)})")
    return code


def plain(text: str) -> bool:
    """Whether ``input text`` can type ``text`` on its own."""
    return all(32 <= ord(c) < 127 for c in text) and "%s" not in text


def needs_keyboard(text: str) -> SparshError:
    odd = sorted({c for c in text if not (32 <= ord(c) < 127)})
    if not odd:
        return SparshError(
            "can't type the two letters '%s' together on this phone (it reads them "
            'as a space) without the ADBKeyBoard app -- SETUP.md, "Typing other '
            'languages". Nothing was typed'
        )
    shown = "".join(odd[:5]).encode("unicode_escape").decode()
    return SparshError(
        f"can't type {shown!r} on this phone: only plain ASCII letters, digits "
        "and punctuation, unless the person installs the small ADBKeyBoard app "
        '(SETUP.md, "Typing other languages"). Nothing was typed'
    )


def pieces(text: str, size: int = 200) -> list[str]:
    # Long text in one go can be dropped by the phone; send it in pieces.
    return [text[i : i + size] for i in range(0, len(text), size)]


def typeable(text: str) -> list[str]:
    """``text`` as shell words for ``input text``, or a sentence why not."""
    if not plain(text):
        raise needs_keyboard(text)
    return ["'" + p.replace(" ", "%s").replace("'", "'\\''") + "'" for p in pieces(text)]


def _run(args: list[str], timeout: float = 30, again: bool = True) -> subprocess.CompletedProcess:
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
        serial = args[args.index("-s") + 1] if "-s" in args else ""
        if again and ":" in serial and ("error: closed" in said or "offline" in said):
            # A Wi-Fi link that went stale while the screen was off (a real
            # Nexus 6P, locked, its Wi-Fi dozing) is still listed as a
            # device, and its first command says "closed": a schedule read
            # that as a phone it couldn't reach. Reconnected, it answers.
            subprocess.run([args[0], "disconnect", serial], capture_output=True, timeout=10)
            subprocess.run([args[0], "connect", serial], capture_output=True, timeout=10)
            return _run(args, timeout, again=False)
        raise SparshError(f"adb said: {said or f'exit {done.returncode}'}")
    return done
