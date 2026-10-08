"""A phone made of saved screens, for tests (and for trying Sparsh out).

    fake = FakeDevice({"home": xml1, "settings": xml2}, start="home")
    fake.after = lambda f, action: ...   # move between screens

Every call is written down in ``fake.actions`` as a tuple --
``("tap", 540, 820)``, ``("text", "hi")``, ``("keys", "back")`` --
(``("keyboard", "café")`` when it went through ADBKeyBoard), and
``after``, if set, is called with each one so a test can change
``fake.current`` the way the real phone would.
"""

from __future__ import annotations

from collections.abc import Callable

from sparsh import SparshError
from sparsh.device import key_code, needs_keyboard, plain
from sparsh.screen import ScreenUnreadable, read

#: Enough of a PNG for anything that only checks the start.
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16


class FakeDevice:
    def __init__(
        self,
        screens: dict[str, str | None],
        start: str,
        apps: list[str] | None = None,
        serial: str = "fake",
        keyboard: bool = False,
    ) -> None:
        self.screens = screens
        self.current = start
        self.installed = sorted(apps or [])
        self.serial = serial
        self.keyboard = keyboard  # ADBKeyBoard installed
        self.front = ""  # the app in front, when a test says so
        self.actions: list[tuple] = []
        self.after: Callable[[FakeDevice, tuple], None] | None = None
        self.tries: list[bool] = []  # each dump's ``retry``
        self.screen_on, self.locked = True, False

    def _did(self, *action) -> None:
        self.actions.append(action)
        if self.after is not None:
            self.after(self, action)

    def dump(self, retry: bool = True) -> str:
        self.tries.append(retry)
        xml = self.screens[self.current]
        if xml is None:  # a screen the phone can't describe (About phone)
            raise ScreenUnreadable("the screen keeps changing")
        return xml

    def screenshot(self) -> bytes:
        return PNG

    def tap(self, x: int, y: int) -> None:
        self._did("tap", x, y)

    def long_press(self, x: int, y: int) -> None:
        self._did("long_press", x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self._did("swipe", x1, y1, x2, y2)

    def check_text(self, text: str) -> None:
        if not plain(text) and not self.keyboard:
            raise needs_keyboard(text)  # refuse what the real phone would refuse

    def type_text(self, text: str) -> None:
        self.check_text(text)
        self._did("text" if plain(text) else "keyboard", text)

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

    def awake(self) -> tuple[bool | None, bool | None]:
        return self.screen_on, self.locked

    def front_app(self) -> str:
        if self.front:
            return self.front
        try:
            return read(self.dump()).app
        except SparshError:
            return ""
