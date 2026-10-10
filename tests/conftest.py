from pathlib import Path

import pytest

from sparsh.fake import FakeDevice
from sparsh.phone import Phone

SCREENS = Path(__file__).parent / "screens"

#: Saved from the Android 15 emulator (Medium_Phone_API_35) with
#: ``adb exec-out uiautomator dump /dev/tty``.
APPS = [
    "com.android.chrome",
    "com.android.settings",
    "com.google.android.apps.messaging",
    "com.google.android.gm",
    "com.google.android.youtube",
]


def screen(name: str) -> str:
    return (SCREENS / f"{name}.xml").read_text()


@pytest.fixture
def fake() -> FakeDevice:
    names = [p.stem for p in SCREENS.glob("*.xml")]
    return FakeDevice({n: screen(n) for n in names}, start="settings", apps=APPS)


@pytest.fixture
def phone(fake, tmp_path) -> Phone:
    return Phone(fake, state=tmp_path, settle=0)


def node(cls: str, bounds: str, text: str = "", desc: str = "", tap: bool = False,
         inside: str = "", package: str = "com.google.android.apps.maps") -> str:  # fmt: skip
    """One node of a hand-made dump, for screens no saved one shows."""
    return (
        f'<node index="0" text="{text}" resource-id="" class="android.{cls}" '
        f'package="{package}" content-desc="{desc}" checkable="false" checked="false" '
        f'clickable="{str(tap).lower()}" enabled="true" focusable="false" focused="false" '
        'scrollable="false" long-clickable="false" password="false" selected="false" '
        f'bounds="{bounds}">{inside}</node>'
    )


def hierarchy(*nodes: str, package: str = "com.google.android.apps.maps") -> str:
    inside = "".join(nodes)
    return ("<?xml version='1.0' ?><hierarchy rotation=\"0\">"
            + node("widget.FrameLayout", "[0,0][1440,2392]", inside=inside, package=package)
            + "</hierarchy>")  # fmt: skip


#: Google Maps' results as a real Nexus 6P listed them: a backdrop as big
#: as the screen, the buttons named, each place an unnamed box.
PLACES = hierarchy(
    node("view.View", "[0,0][1440,2392]", tap=True),
    node("widget.Button", "[1230,760][1398,928]", desc="Close", tap=True),
    node("view.View", "[0,1453][1440,1922]", tap=True),
    node("view.View", "[70,1453][567,1922]", tap=True),
    node("view.View", "[595,1453][1092,1922]", tap=True),
    node("view.View", "[512,2286][783,2392]", text="Call", tap=True),
)

#: Chrome straight after a search: the bar named, the page not yet.
CHROME = "com.android.chrome"
BLANK_PAGE = hierarchy(
    node(
        "widget.EditText",
        "[280,95][894,269]",
        text="google.com/search?q=indian",
        tap=True,
        package=CHROME,
    ),
    node("webkit.WebView", "[0,280][1440,2392]", desc="Web View", package=CHROME),
    package=CHROME,
)
#: The same page a moment later, its words in the list.
FILLED_PAGE = BLANK_PAGE.replace('desc="Web View"', 'desc=""').replace(
    'bounds="[0,280][1440,2392]">',
    'bounds="[0,280][1440,2392]">'
    + node(
        "view.View", "[56,1876][987,2233]", text="Haveli Indian Cuisine", tap=True, package=CHROME
    ),
    1,
)
