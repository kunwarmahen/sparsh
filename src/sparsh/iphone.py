"""An iPhone, through WebDriverAgent -- the same few things, asked over HTTP.

Android lets a computer drive the phone with ``adb`` and nothing
installed on it. An iPhone doesn't: the way in is WebDriverAgent (WDA),
a small test app from the Appium project that runs on the phone and
answers HTTP on port 8100. It has to be built and signed with Xcode,
which only runs on a Mac -- once, or once a week with a free Apple ID
(``scripts/build-wda-on-mac.sh``, and README "An iPhone"). After that
the Mac is not needed: WDA is installed and started from Linux (go-ios),
and :class:`WdaDevice` talks to it from anywhere on the network.

    sparsh look --serial http://192.168.1.40:8100

What each method asks for:

    dump        GET  /source               the screen, as XCUITest's XML
                GET  /wda/activeAppInfo    which app is in front
    screenshot  GET  /screenshot           a PNG, base64
    tap, long_press, swipe
                POST /session/S/actions    one finger, W3C pointer actions
    type_text   POST /session/S/wda/keys   into whatever has the keyboard
    keys        (below)
    launch      POST /session/S/wda/apps/launch

ONE SCREEN READER, TWO PHONES. The numbered list is made by screen.py
from Android's description of a screen, and that reader has been argued
over (notes/01). Rather than a second reader for the iPhone, :func:`as_android`
rewrites XCUITest's description into the shape uiautomator prints --
a Cell becomes a tappable row that takes its words from inside, a Switch
whose value is "1" is a checked switch, a SecureTextField is a password
field, and a row that has its own words doesn't repeat them from
inside -- so the list, the check before every tap and the rules all work
the same on both. Coordinates are the iPhone's points, not pixels, and
the taps are sent in points too, so they agree.

WHAT AN IPHONE HAS NOT GOT. It has no Back key: ``back`` is the swipe
from the left edge that most apps take to mean back. ``end`` does
nothing (tapping a field puts the cursor at the end of it already);
``recent``, ``search`` and the arrow keys are refused with a sentence.
WDA can't list the apps on the phone, so :meth:`WdaDevice.apps` is
Apple's own apps plus any named in ``$SPARSH_IOS_APPS``, and everyday
names ("settings", "messages") are looked up in :data:`NICKNAMES`.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from sparsh import SparshError
from sparsh.screen import ScreenUnreadable

#: Apple's own apps, by everyday name -> bundle id.
NICKNAMES = {
    "settings": "com.apple.Preferences",
    "safari": "com.apple.mobilesafari",
    "messages": "com.apple.MobileSMS",
    "phone": "com.apple.mobilephone",
    "mail": "com.apple.mobilemail",
    "camera": "com.apple.camera",
    "photos": "com.apple.mobileslideshow",
    "maps": "com.apple.Maps",
    "calendar": "com.apple.mobilecal",
    "clock": "com.apple.mobiletimer",
    "notes": "com.apple.mobilenotes",
    "reminders": "com.apple.reminders",
    "contacts": "com.apple.MobileAddressBook",
    "app store": "com.apple.AppStore",
    "files": "com.apple.DocumentsApp",
    "weather": "com.apple.weather",
    "calculator": "com.apple.calculator",
    "music": "com.apple.Music",
    "wallet": "com.apple.Passbook",
    "health": "com.apple.Health",
    "facetime": "com.apple.facetime",
}

#: Keys an iPhone's keyboard can be sent as letters.
_TYPED_KEYS = {"enter": "\n", "delete": "\b", "tab": "\t"}
_BUTTONS = {"volume_up": "volumeUp", "volume_down": "volumeDown"}

#: XCUIElementType... -> the Android class name screen.py knows it by.
_AS = {
    "Button": "android.widget.Button",
    "Switch": "android.widget.Switch",
    "Toggle": "android.widget.Switch",
    "CheckBox": "android.widget.CheckBox",
    "RadioButton": "android.widget.RadioButton",
    "TextField": "android.widget.EditText",
    "SecureTextField": "android.widget.EditText",
    "SearchField": "android.widget.EditText",
    "TextView": "android.widget.EditText",
    "Image": "android.widget.ImageView",
    "StaticText": "android.widget.TextView",
}
_TAPPABLE = {
    "Button", "Cell", "Link", "Icon", "MenuItem", "Tab", "Slider", "PickerWheel",
    "SegmentedControl", "Stepper", "Switch", "Toggle", "CheckBox", "RadioButton",
}  # fmt: skip
_SCROLLS = {"Table", "CollectionView", "ScrollView"}
_FIELDS = {"TextField", "SecureTextField", "SearchField", "TextView"}
#: Never shown: the on-screen keyboard (adb's dump leaves it out too).
_SKIP = {"Keyboard"}


def is_wda(serial: str | None) -> bool:
    return bool(serial) and serial.startswith(("http://", "https://"))


class WdaDevice:
    def __init__(self, url: str, timeout: float = 30) -> None:
        self.url = url.rstrip("/")
        self.serial = self.url
        self.timeout = timeout
        self.nicknames = dict(NICKNAMES)
        self._session: str | None = None

    # -- talking to WDA --------------------------------------------------

    def _call(
        self, method: str, path: str, body: dict | None = None, whole: bool = False
    ) -> object:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )  # fmt: skip
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as answer:
                reply = json.loads(answer.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                reply = json.loads(e.read() or b"{}")
            except ValueError:
                reply = {}
            said = _said(reply) or f"HTTP {e.code}"
            raise WdaError(said, invalid_session="invalid session" in said.lower()) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise SparshError(
                f"the iPhone isn't answering at {self.url} ({getattr(e, 'reason', e)}). "
                "Is WebDriverAgent running on it? (README: An iPhone)"
            ) from None
        except ValueError:
            raise SparshError(f"{self.url} answered, but not like WebDriverAgent") from None
        if isinstance(reply, dict) and isinstance(reply.get("value"), dict):
            if "error" in reply["value"]:
                raise WdaError(_said(reply))
        if whole or not isinstance(reply, dict):
            return reply
        return reply.get("value")

    def status(self) -> object:
        return self._call("GET", "/status")

    def _session_id(self) -> str:
        if self._session:
            return self._session
        # The session WDA already has (the answer's top level says it).
        status = self._call("GET", "/status", whole=True)
        found = status.get("sessionId") or "" if isinstance(status, dict) else ""
        if not found:
            made = self._call("POST", "/session", {"capabilities": {}})
            found = made.get("sessionId", "") if isinstance(made, dict) else ""
        if not found:
            raise SparshError("WebDriverAgent did not open a session")
        self._session = found
        return found

    def _act(self, path: str, body: dict) -> object:
        """A call inside the session; a lapsed session is opened again once."""
        for attempt in range(2):
            try:
                return self._call("POST", f"/session/{self._session_id()}{path}", body)
            except WdaError as e:
                if not e.invalid_session or attempt:
                    raise
                self._session = None
        raise AssertionError("unreachable")

    # -- the Device shape --------------------------------------------------

    def dump(self) -> str:
        source = self._call("GET", "/source?format=xml")
        if not isinstance(source, str) or not source.strip():
            raise ScreenUnreadable("the iPhone did not describe its screen")
        try:
            info = self._call("GET", "/wda/activeAppInfo")
        except WdaError:
            info = {}
        bundle = info.get("bundleId", "") if isinstance(info, dict) else ""
        return as_android(source, bundle)

    def screenshot(self) -> bytes:
        shot = self._call("GET", "/screenshot")
        png = base64.b64decode(shot) if isinstance(shot, str) else b""
        if not png.startswith(b"\x89PNG"):
            raise SparshError("the iPhone did not send a screenshot")
        return png

    def tap(self, x: int, y: int) -> None:
        self._finger(x, y, [{"type": "pause", "duration": 80}])

    def long_press(self, x: int, y: int) -> None:
        self._finger(x, y, [{"type": "pause", "duration": 800}])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self._finger(x1, y1, [
            {"type": "pause", "duration": 50},
            {"type": "pointerMove", "duration": ms, "x": x2, "y": y2},
        ])  # fmt: skip

    def _finger(self, x: int, y: int, between: list[dict]) -> None:
        steps = [
            {"type": "pointerMove", "duration": 0, "x": x, "y": y},
            {"type": "pointerDown", "button": 0},
            *between,
            {"type": "pointerUp", "button": 0},
        ]
        finger = {"type": "pointer", "id": "finger1",
                  "parameters": {"pointerType": "touch"}, "actions": steps}  # fmt: skip
        self._act("/actions", {"actions": [finger]})

    def type_text(self, text: str) -> None:
        if text:
            self._act("/wda/keys", {"value": [text]})

    def keys(self, *names: str) -> None:
        typed = ""
        for name in (n.lower().strip() for n in names):
            if name in _TYPED_KEYS:
                typed += _TYPED_KEYS[name]
                continue
            if typed:  # in order: what was typed goes before the next button
                self._act("/wda/keys", {"value": [typed]})
                typed = ""
            if name == "end":
                continue
            if name == "home":
                self._call("POST", "/wda/homescreen", {})
            elif name == "back":
                self._back()
            elif name in _BUTTONS:
                self._act("/wda/pressButton", {"name": _BUTTONS[name]})
            else:
                known = ["back", "home", *_TYPED_KEYS, *_BUTTONS]
                raise SparshError(
                    f"an iPhone has no {name!r} key (keys on an iPhone: {', '.join(known)})"
                )
        if typed:
            self._act("/wda/keys", {"value": [typed]})

    def _back(self) -> None:
        # The swipe in from the left edge most apps take as back.
        size = self._call("GET", "/window/size")
        if not isinstance(size, dict):
            size = {}
        width, height = int(size.get("width", 390)), int(size.get("height", 844))
        self.swipe(2, height // 2, width * 2 // 3, height // 2, 250)

    def launch(self, package: str) -> None:
        try:
            self._act("/wda/apps/launch", {"bundleId": package})
        except WdaError as e:
            raise SparshError(f"{package} could not be opened on this iPhone ({e})") from None

    def apps(self) -> list[str]:
        extra = os.environ.get("SPARSH_IOS_APPS", "")
        named = {a.strip() for a in extra.split(",") if a.strip()}
        return sorted(set(NICKNAMES.values()) | named)


class WdaError(SparshError):
    def __init__(self, said: str, invalid_session: bool = False) -> None:
        self.invalid_session = invalid_session
        super().__init__(f"WebDriverAgent said: {said}")


def _said(reply: object) -> str:
    value = reply.get("value") if isinstance(reply, dict) else None
    if isinstance(value, dict):
        return str(value.get("message") or value.get("error") or "").strip()
    return ""


# -- XCUITest's screen, in uiautomator's words ------------------------------


def as_android(source: str, bundle: str = "") -> str:
    """WDA's ``/source`` XML rewritten as a ``uiautomator dump``."""
    try:
        root = ET.fromstring(source.strip().encode())
    except ET.ParseError as e:
        raise ScreenUnreadable(f"the iPhone's description of its screen was cut short ({e})") from e
    out = ['<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">']
    # The application itself: the first node, which screen.read takes the
    # app and the screen's size from. Its own name is not a line.
    out.append(
        f'<node class="android.widget.FrameLayout" text="" content-desc="" '
        f'resource-id="" package={quoteattr(bundle)} bounds={quoteattr(_bounds(root))}>'
    )
    guessed = _focus_guess(root)
    for child in root:
        _node(child, bundle, out, guessed, quiet=False)
    out.append("</node></hierarchy>")
    return "".join(out)


def _node(
    el: ET.Element, bundle: str, out: list[str], guessed: ET.Element | None, quiet: bool
) -> None:
    """One node and what's inside. ``quiet``: inside something tappable
    that already has its words, so plain text here would say them twice."""
    kind = _type(el)
    if kind in _SKIP:
        return
    if el.get("visible", "true") != "true":
        # Off screen (a row scrolled away) -- but something inside may not be.
        for child in el:
            _node(child, bundle, out, guessed, quiet)
        return
    label = (el.get("label") or "").strip()
    value = (el.get("value") or "").strip()
    name = (el.get("name") or "").strip()
    field = kind in _FIELDS
    switch = kind in ("Switch", "Toggle", "CheckBox", "RadioButton")
    tappable = kind in _TAPPABLE
    # A ROW WITH A SWITCH IS THE SWITCH. On Android tapping the row flips
    # it; on an iPhone only the switch itself does, so the row steps
    # aside and the switch takes the line, under the row's words.
    if kind == "Cell" and any(_type(c) in ("Switch", "Toggle") for c in el.iter()):
        tappable, label, value = False, "", ""
        quiet = True
    text, desc = label, ""
    if field:
        text = value or (el.get("placeholderValue") or "").strip() or label
    elif switch:
        pass
    elif value and value != label:
        desc = value  # a row's detail: "Wi-Fi (HomeNet)"
    if not text and not desc and kind == "StaticText":
        text = value
    if quiet and kind in ("StaticText", "Image"):
        text = desc = ""
    focused = el.get("focused") == "true" or el.get("hasFocus") == "true" or el is guessed
    attrs = {
        "class": _AS.get(kind, "android.view.View"),
        "text": text,
        "content-desc": desc,
        "resource-id": name if name and name not in (label, value) else "",
        "package": bundle,
        "clickable": _yes(tappable),
        "scrollable": _yes(kind in _SCROLLS),
        "checkable": _yes(switch),
        "checked": _yes(switch and value in ("1", "true")),
        "password": _yes(kind == "SecureTextField"),
        "focused": _yes(field and focused),
        "enabled": _yes(el.get("enabled", "true") == "true"),
        "bounds": _bounds(el),
    }
    out.append("<node " + " ".join(f"{k}={quoteattr(v)}" for k, v in attrs.items()) + ">")
    quiet = quiet or (tappable and bool(text or desc))
    for child in el:
        _node(child, bundle, out, guessed, quiet)
    out.append("</node>")


def _focus_guess(root: ET.Element) -> ET.Element | None:
    """Which field has the keyboard. Older WDA doesn't say; when the
    keyboard is up and only one field is on screen, it is that one."""
    fields, keyboard = [], False
    for el in root.iter():
        kind = _type(el)
        if kind == "Keyboard" and el.get("visible", "true") == "true":
            keyboard = True
        elif kind in _FIELDS and el.get("visible", "true") == "true":
            fields.append(el)
    return fields[0] if keyboard and len(fields) == 1 else None


def _type(el: ET.Element) -> str:
    return (el.get("type") or el.tag).removeprefix("XCUIElementType")


def _bounds(el: ET.Element) -> str:
    def num(name: str) -> int:
        try:
            return round(float(el.get(name) or 0))
        except ValueError:
            return 0

    x, y = num("x"), num("y")
    return f"[{x},{y}][{x + num('width')},{y + num('height')}]"


def _yes(flag: bool) -> str:
    return "true" if flag else "false"
