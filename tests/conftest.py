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
