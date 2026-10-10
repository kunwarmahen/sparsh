"""What's on the phone's screen, as a numbered list a model can read.

Android describes every screen as a tree (the accessibility tree that
TalkBack reads aloud); ``uiautomator dump`` prints it as XML. Most of
that tree is layout -- frames inside frames -- and the useful parts are
scattered: a Settings row is a tappable box with no words of its own,
whose label sits in two text nodes inside it, and whose on/off switch
is a third. :func:`read` folds that into one line per thing a person
would point at::

    App: com.android.settings
    1 image "Profile picture, double tap to open Google Account" [tap]
    2 text "Settings"
    3 item "Search settings" [tap]
    4 list [scroll]
    5 item "Network & internet — Mobile, Wi‑Fi, hotspot" [tap]
    6 item "Airplane mode" [tap, off]
    7 field "hello world" [type, focused]

The model answers with a number. It never sees a coordinate: the
number is turned back into the middle of that thing's box by
:class:`Element`, and :meth:`Screen.find` checks the thing is still
where it was before anything is tapped (phone.py).

What gets a line: anything that can be tapped, typed into, scrolled or
switched, and any words not already used as some tappable thing's
label. Boxes with no size (a row scrolled half off the bottom reports
upside-down bounds) are left out -- there is nothing there to tap.

A LIST CAN BE THERE AND STILL SAY NOTHING. Two kinds of screen give
lines that tell the model nothing about what matters on them, and each
is counted so that a picture can go with it (phone.py, ``shown``):

* ``blank_page`` -- a web page whose words haven't reached the list.
  Chrome fills in a page's description a moment after it is first
  asked for, so a look straight after a search on a real Nexus 6P read
  only ``text "Web View"`` and the browser's own bar around it.
* ``blanks`` -- things to tap with no words at all. Google Maps draws
  each place in its results as an unnamed box: the 6P's list of Indian
  restaurants was six ``item [tap]`` lines and their buttons ("Call",
  "Directions"), with no restaurant named. A box as big as the screen
  is a backdrop, not counted. ``BLANKS`` of them make a screen partly
  blank; across 194 screens the agents had read, only Maps reached it.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

from sparsh import SparshError

#: Smaller than this (pixels, either way) is not something to tap.
MIN_SIZE = 10
#: Unnamed things to tap that make a screen partly blank (module docstring).
BLANKS = 3

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

#: The end of a widget's class name -> what the line calls it.
_KINDS = (
    ("EditText", "field"),
    ("AutoCompleteTextView", "field"),
    ("Switch", "switch"),
    ("SwitchCompat", "switch"),
    ("SwitchMaterial", "switch"),
    ("ToggleButton", "switch"),
    ("CheckBox", "checkbox"),
    ("CheckedTextView", "checkbox"),
    ("RadioButton", "radio"),
    ("ImageButton", "button"),
    ("Button", "button"),
    ("ImageView", "image"),
    ("TextView", "text"),
)


class ScreenUnreadable(SparshError):
    """The phone didn't give us a screen to read (see device.py)."""


@dataclass(frozen=True)
class Element:
    """One line of the list."""

    n: int
    kind: str
    label: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    id: str = ""  # the app's own name for it (resource-id, after the /)
    tap: bool = False
    long: bool = False
    scroll: bool = False
    type: bool = False
    switch: bool = False
    on: bool = False
    focused: bool = False
    password: bool = False
    enabled: bool = True

    @property
    def centre(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2

    @property
    def what(self) -> tuple[str, str, tuple[int, int, int, int]]:
        """What must still match for the same number to mean the same thing."""
        return (self.kind, self.label, self.bounds)

    def line(self) -> str:
        flags = [
            name
            for name, present in (
                ("tap", self.tap),
                ("long-press", self.long and not self.tap),
                ("type", self.type),
                ("scroll", self.scroll),
                ("on" if self.on else "off", self.switch),
                ("focused", self.focused),
                ("password", self.password),
                ("disabled", not self.enabled),
            )
            if present
        ]
        text = f"{self.n} {self.kind}"
        if self.label:
            text += " " + json.dumps(self.label, ensure_ascii=False)
        if flags:
            text += f" [{', '.join(flags)}]"
        return text

    def to_json(self) -> dict:
        data = asdict(self)
        data["bounds"] = list(self.bounds)
        return data


@dataclass
class Screen:
    app: str
    elements: list[Element] = field(default_factory=list)
    size: tuple[int, int] = (0, 0)  # the whole screen's width, height
    #: Said instead of the list when the screen is not to be shown.
    note: str = ""
    #: Said above the list: what Sparsh did on its own to get here.
    remark: str = ""
    #: Things to tap with no words, and a web page with none in the list
    #: (module docstring).
    blanks: int = 0
    blank_page: bool = False

    @property
    def partly_blank(self) -> bool:
        """The list is there, but what matters on the screen isn't in it."""
        return self.blank_page or self.blanks >= BLANKS

    def text(self) -> str:
        lines = [f"App: {self.app or '(unknown)'}"]
        if self.remark:
            lines.append(self.remark)
        if self.note:
            return "\n".join([*lines, self.note])
        lines += [e.line() for e in self.elements]
        if not self.elements:
            lines.append("(nothing on this screen can be read -- try a screenshot)")
        return "\n".join(lines)

    def get(self, n: int) -> Element:
        for element in self.elements:
            if element.n == n:
                return element
        raise SparshError(f"there is no {n} on this screen (1 to {len(self.elements)})")

    def find(self, element: Element) -> Element | None:
        """The same thing on this (newer) screen, if it is still there."""
        for candidate in self.elements:
            if candidate.what == element.what:
                return candidate
        return None

    def to_json(self) -> dict:
        return {
            "app": self.app,
            "size": list(self.size),
            "note": self.note,
            "remark": self.remark,
            "elements": [e.to_json() for e in self.elements],
        }


def read(xml: str) -> Screen:
    """The numbered list for one ``uiautomator dump``."""
    start = xml.find("<?xml")
    if start < 0:
        start = xml.find("<hierarchy")
    end = xml.rfind("</hierarchy>")
    if start < 0 or end < 0:
        said = xml.strip().splitlines()[0] if xml.strip() else "nothing"
        raise ScreenUnreadable(f"the phone did not describe its screen (it said: {said})")
    try:
        root = ET.fromstring(xml[start : end + len("</hierarchy>")])
    except ET.ParseError as e:
        raise ScreenUnreadable(f"the phone's description of its screen was cut short ({e})") from e

    nodes = list(root)
    app = nodes[0].get("package", "") if nodes else ""
    size = (0, 0)
    if nodes:
        left, top, right, bottom = _bounds(nodes[0])
        size = (right - left, bottom - top)

    used: set[int] = set()  # id() of nodes folded into another's line
    picked: list[tuple[ET.Element, dict]] = []
    for node in root.iter("node"):
        if id(node) in used or not _visible(node):
            continue
        line = _describe(node, used)
        if line is not None:
            picked.append((node, line))

    elements = [Element(n=i, **line) for i, (_, line) in enumerate(picked, start=1)]
    whole = size[0] * size[1] * 9 // 10
    blanks = sum(1 for e in elements if e.tap and not e.label and _area(e.bounds) < whole)
    blank_page = any(_kind_name(node).endswith("WebView") and not _has_words(node)
                     for node in root.iter("node"))  # fmt: skip
    return Screen(app=app, elements=elements, size=size, blanks=blanks, blank_page=blank_page)


def _area(bounds: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = bounds
    return max(0, right - left) * max(0, bottom - top)


def _kind_name(node: ET.Element) -> str:
    return node.get("class", "").rpartition(".")[2]


def _has_words(node: ET.Element) -> bool:
    """Whether anything inside (not the node itself) has words."""
    return any(_own_label(n) for n in node.iter("node") if n is not node)


def _describe(node: ET.Element, used: set[int]) -> dict | None:
    """The line for one node, or None if it doesn't get one."""
    yes = lambda name: node.get(name) == "true"  # noqa: E731
    kind = _kind(node)
    tap, long, scroll = yes("clickable"), yes("long-clickable"), yes("scrollable")
    typing = kind == "field"
    switch = yes("checkable")
    on = yes("checked")
    own = _own_label(node)
    acts = tap or long or scroll or typing or switch

    if not acts:
        if not own:
            return None
        kind = "image" if kind == "image" else "text"
    elif scroll and not (tap or typing):
        kind = "list"
        own = node.get("content-desc", "") or _humanise(node.get("resource-id", ""))
    elif not typing:
        if kind not in ("button", "switch", "checkbox", "radio", "image", "text"):
            kind = "item"
        # A tappable box takes its words, and a switch that can't be
        # tapped by itself, from inside -- stopping at anything inside
        # that acts on its own (it gets its own line).
        words: list[str] = []
        for child in _inside(node):
            if not _visible(child) and not _own_label(child):
                continue
            if _acts(child):
                if child.get("checkable") == "true" and child.get("clickable") != "true":
                    switch, on = True, child.get("checked") == "true"
                    used.add(id(child))
                continue
            label = _own_label(child)
            if label and not own:
                words.append(label)
                used.add(id(child))
        if not own:
            own = " — ".join(dict.fromkeys(words))
        if not own:
            own = _humanise(node.get("resource-id", ""))
        if switch and kind == "text":
            kind = "item"

    password = yes("password")
    if password:
        own = "(hidden)" if node.get("text") else own
    return {
        "kind": kind,
        "label": own,
        "bounds": _bounds(node),
        "id": node.get("resource-id", "").rpartition("/")[2],
        "tap": tap,
        "long": long,
        "scroll": scroll,
        "type": typing,
        "switch": switch,
        "on": on,
        "focused": yes("focused") and typing,
        "password": password,
        "enabled": node.get("enabled", "true") == "true",
    }


def _inside(node: ET.Element):
    """Every node under this one, not crossing into ones that act on their own."""
    for child in node:
        yield child
        if not _acts(child):
            yield from _inside(child)


def _acts(node: ET.Element) -> bool:
    acting = ("clickable", "long-clickable", "scrollable", "checkable")
    return any(node.get(a) == "true" for a in acting) or _kind(node) == "field"


def _own_label(node: ET.Element) -> str:
    text = " ".join(node.get("text", "").split())
    desc = " ".join(node.get("content-desc", "").split())
    if text and desc and text != desc:
        # A launcher icon: "Play Store" and "Play Store has 1 notification".
        if text in desc:
            return desc
        if desc in text:
            return text
        return f"{text} ({desc})"
    return text or desc


def _kind(node: ET.Element) -> str:
    name = _kind_name(node)
    for ending, kind in _KINDS:
        if name.endswith(ending):
            return kind
    return "item"


def _bounds(node: ET.Element) -> tuple[int, int, int, int]:
    match = _BOUNDS.fullmatch(node.get("bounds", ""))
    if not match:
        return (0, 0, 0, 0)
    left, top, right, bottom = (int(v) for v in match.groups())
    return (left, top, right, bottom)


def _visible(node: ET.Element) -> bool:
    left, top, right, bottom = _bounds(node)
    return right - left >= MIN_SIZE and bottom - top >= MIN_SIZE


def _humanise(resource_id: str) -> str:
    """``com.app:id/search_action_bar`` -> ``search action bar``."""
    name = resource_id.rpartition("/")[2]
    return name.replace("_", " ").strip()
