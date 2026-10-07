"""A phone made of saved screens, for tests (and for trying Sparsh out).

    fake = FakeDevice({"home": xml1, "settings": xml2}, start="home")
    fake.after = lambda f, action: ...   # move between screens

Every call is written down in ``fake.actions`` as a tuple --
``("tap", 540, 820)``, ``("text", "hi")``, ``("keys", "back")`` -- and
``after``, if set, is called with each one so a test can change
``fake.current`` the way the real phone would.
"""

from __future__ import annotations

from collections.abc import Callable

from sparsh import SparshError
from sparsh.device import _typeable, key_code

#: Enough of a PNG for anything that only checks the start.
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


class FakeDevice:
    def __init__(
        self,
        screens: dict[str, str],
        start: str,
        apps: list[str] | None = None,
        serial: str = "fake",
    ) -> None:
        self.screens = screens
        self.current = start
        self.installed = sorted(apps or [])
        self.serial = serial
        self.actions: list[tuple] = []
        self.after: Callable[[FakeDevice, tuple], None] | None = None

    def _did(self, *action) -> None:
        self.actions.append(action)
        if self.after is not None:
            self.after(self, action)

    def dump(self) -> str:
        return self.screens[self.current]

    def screenshot(self) -> bytes:
        return PNG

    def tap(self, x: int, y: int) -> None:
        self._did("tap", x, y)

    def long_press(self, x: int, y: int) -> None:
        self._did("long_press", x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self._did("swipe", x1, y1, x2, y2)

    def type_text(self, text: str) -> None:
        _typeable(text)  # refuse what the real phone would refuse
        self._did("text", text)

    def keys(self, *names: str) -> None:
        for name in names:
            key_code(name)
        self._did("keys", *names)

    def launch(self, package: str) -> None:
        if package not in self.installed:
            raise SparshError(f"{package} has no app to open on this phone")
        self._did("launch", package)

    def apps(self) -> list[str]:
        return list(self.installed)
