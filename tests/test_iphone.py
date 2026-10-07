"""An iPhone read and worked through WebDriverAgent, without an iPhone.

The bias these tests encode: AN IPHONE IS NOT A SECOND-CLASS PHONE. The
failure guarded against is a backend that "works" in the narrow sense
-- it sends taps -- while quietly dropping what the Android side was
built to keep: a row's words folded into one line, a switch's state, a
password field that hides its letters, a disabled button that says so,
the check that a number still means what it meant. So the screens go
through the same reader and the same Phone, and the HTTP calls are
checked as a stand-in WebDriverAgent received them.

The screens in ``screens/ios`` are written by hand in the shape WDA's
``/source`` prints (XCUIElementType... nodes with label, value, name
and x/y/width/height), not captured from a phone.
"""

import base64
import json
import threading
import zipfile
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sparsh import SparshError
from sparsh.device import pick
from sparsh.cli import main
from sparsh.iphone import (
    WdaDevice,
    as_android,
    remember_signature,
    signature,
    signature_note,
    signed_until,
)
from sparsh.phone import Phone, ScreenChanged
from sparsh.screen import read
from sparsh.status import report

IOS = Path(__file__).parent / "screens" / "ios"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 8


def ios(name: str) -> str:
    return (IOS / f"{name}.xml").read_text()


class FakeWda:
    """Enough of WebDriverAgent's HTTP to drive: it records every call."""

    def __init__(self, source: str, bundle: str = "com.apple.Preferences") -> None:
        self.source = source
        self.bundle = bundle
        self.calls: list[tuple[str, str, object]] = []
        self.session = "S1"
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, value, code=200, **top):
                body = json.dumps({"value": value, **top}).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                fake.calls.append(("GET", self.path, None))
                if self.path.startswith("/source"):
                    self._reply(fake.source)
                elif self.path == "/wda/activeAppInfo":
                    self._reply({"bundleId": fake.bundle})
                elif self.path == "/status":
                    self._reply({"ready": True}, sessionId=fake.session)
                elif self.path == "/screenshot":
                    self._reply(base64.b64encode(PNG).decode())
                elif self.path == "/window/size":
                    self._reply({"width": 390, "height": 844})
                else:
                    self._reply({"error": "unknown command", "message": "no"}, 404)

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size) or b"{}")
                path = self.path
                if path.startswith("/session/") and not path.startswith(f"/session/{fake.session}"):
                    self._reply({"error": "invalid session id", "message": "invalid session id"},
                                404)  # fmt: skip
                    return
                fake.calls.append(("POST", path.replace(f"/session/{fake.session}", ""), body))
                if path == "/session":
                    self._reply({"sessionId": fake.session}, sessionId=fake.session)
                else:
                    self._reply(None)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def posts(self) -> list[tuple[str, object]]:
        return [(path, body) for method, path, body in self.calls if method == "POST"]


@pytest.fixture
def wda():
    fake = FakeWda(ios("settings"))
    yield fake
    fake.server.shutdown()
    fake.server.server_close()


@pytest.fixture
def iphone(wda, tmp_path) -> Phone:
    return Phone(WdaDevice(wda.url), state=tmp_path, settle=0)


# -- reading ------------------------------------------------------------


def test_the_iphone_settings_screen_reads_like_the_android_one():
    screen = read(as_android(ios("settings"), "com.apple.Preferences"))
    assert screen.app == "com.apple.Preferences"
    assert screen.size == (390, 844)
    assert screen.text().splitlines() == [
        "App: com.apple.Preferences",
        '1 text "Settings"',
        '2 field "Search" [type]',
        "3 list [scroll]",
        '4 switch "Airplane Mode" [tap, off]',
        '5 item "Wi-Fi (HomeNet)" [tap]',
        '6 item "Bluetooth — On" [tap]',
    ]


def test_a_row_scrolled_off_screen_gets_no_line():
    screen = read(as_android(ios("settings")))
    assert not any("Privacy" in e.label for e in screen.elements)


def test_a_password_hides_its_letters_and_a_disabled_button_says_so():
    lines = read(as_android(ios("login"))).text().splitlines()
    assert '1 field "Email" [type]' in lines
    assert '2 field "(hidden)" [type, password]' in lines
    assert '3 button "Sign In" [tap, disabled]' in lines


def test_the_keyboard_is_not_on_the_list():
    screen = read(as_android(ios("login")))
    assert not any(e.label == "q" for e in screen.elements)


def test_with_the_keyboard_up_and_one_field_that_field_has_it():
    one = ios("login").replace(
        '<XCUIElementTypeSecureTextField type="XCUIElementTypeSecureTextField"',
        '<XCUIElementTypeSecureTextField type="XCUIElementTypeSecureTextField" visible="false"',
    ).replace('value="••••••" name="password" label="" placeholderValue="Password" enabled="true" '
              'visible="true"', 'value="" name="password" label="" enabled="true"')  # fmt: skip
    screen = read(as_android(one))
    assert [e.label for e in screen.elements if e.focused] == ["Email"]
    # Two fields and no word on which: none is guessed.
    assert not any(e.focused for e in read(as_android(ios("login"))).elements)


def test_a_switched_on_switch_reads_on():
    on = ios("settings").replace(
        'XCUIElementTypeSwitch" value="0"', 'XCUIElementTypeSwitch" value="1"'
    )
    assert '4 switch "Airplane Mode" [tap, on]' in read(as_android(on)).text()


# -- doing --------------------------------------------------------------


def test_a_tap_is_one_finger_on_the_middle_of_the_row(iphone, wda):
    iphone.look()
    iphone.tap(5)  # Wi-Fi, [0,252][390,304]
    ((path, body),) = wda.posts()
    assert path == "/actions"
    steps = body["actions"][0]["actions"]
    assert steps[0] == {"type": "pointerMove", "duration": 0, "x": 195, "y": 278}
    assert [s["type"] for s in steps] == ["pointerMove", "pointerDown", "pause", "pointerUp"]


def test_nothing_is_tapped_on_an_iphone_when_the_screen_moved(iphone, wda):
    iphone.look()
    wda.source = ios("login")
    with pytest.raises(ScreenChanged):
        iphone.tap(5)
    assert wda.posts() == []


def test_typing_goes_to_the_keyboard_and_enter_rides_along(iphone, wda):
    iphone.look()
    iphone.type("cafe wifi", into=2, enter=True)
    keys = [body for path, body in wda.posts() if path == "/wda/keys"]
    assert keys == [{"value": ["cafe wifi"]}, {"value": ["\n"]}]


def test_back_is_the_swipe_in_from_the_left_edge(iphone, wda):
    iphone.key("back")
    ((path, body),) = wda.posts()
    steps = body["actions"][0]["actions"]
    assert steps[0]["x"] == 2 and steps[-2]["x"] == 260


def test_home_needs_no_session(iphone, wda):
    iphone.key("home")
    assert wda.posts() == [("/wda/homescreen", {})]


def test_a_key_an_iphone_has_not_got_is_refused_in_words(iphone, wda):
    with pytest.raises(SparshError, match="an iPhone has no 'recent' key"):
        iphone.key("recent")
    assert wda.posts() == []


def test_settings_opens_apples_settings_app(iphone, wda):
    iphone.open_app("settings")
    assert ("/wda/apps/launch", {"bundleId": "com.apple.Preferences"}) in wda.posts()


def test_a_lapsed_session_is_opened_again_once(iphone, wda):
    iphone.look()
    iphone.device._session = "old"
    iphone.tap(4)
    assert [p for p, _ in wda.posts()] == ["/actions"]


def test_a_screenshot_is_the_png_wda_sent(iphone, tmp_path):
    shot = tmp_path / "shot.png"
    iphone.look(shot=shot)
    assert shot.read_bytes() == PNG


# -- finding it ---------------------------------------------------------


def test_a_web_address_for_a_serial_is_an_iphone(monkeypatch):
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    assert isinstance(pick("http://192.168.1.40:8100"), WdaDevice)
    monkeypatch.setenv("SPARSH_WDA", "http://iphone.local:8100")
    assert pick().serial == "http://iphone.local:8100"


def test_an_iphone_that_isnt_running_wda_says_so():
    device = WdaDevice("http://127.0.0.1:9", timeout=2)
    with pytest.raises(SparshError, match="Is WebDriverAgent running on it"):
        device.dump()


def test_a_switch_row_is_tapped_on_the_switch_itself(iphone, wda):
    iphone.look()
    iphone.tap(4)  # Airplane Mode's switch, [309,210][374,242]
    ((path, body),) = wda.posts()
    assert body["actions"][0]["actions"][0]["x"] == 341
    assert body["actions"][0]["actions"][0]["y"] == 226


# -- how long the signature lasts ----------------------------------------


def make_ipa(folder: Path, until: datetime) -> Path:
    """A WDA.ipa as build-wda-on-mac.sh packs it: the profile is a signed
    blob (bytes either side) with the plist's dates in the middle."""
    stamp = until.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    profile = (b"\x30\x82\x01\x00signed..<plist><dict><key>CreationDate</key><date>"
               b"2026-10-01T00:00:00Z</date><key>ExpirationDate</key>\n\t<date>" + stamp +
               b"</date></dict></plist>..signature\x00")  # fmt: skip
    ipa = folder / "WDA.ipa"
    with zipfile.ZipFile(ipa, "w") as packed:
        app = "Payload/WebDriverAgentRunner-Runner.app/"
        packed.writestr(app + "embedded.mobileprovision", profile)
        packed.writestr(app + "PlugIns/WebDriverAgentRunner.xctest/embedded.mobileprovision", b"")
    return ipa


def test_the_date_is_read_from_inside_the_signed_app(tmp_path):
    until = datetime(2026, 10, 14, 16, 2, tzinfo=UTC)
    assert signed_until(make_ipa(tmp_path, until)) == until


def test_a_week_left_says_nothing_and_two_days_says_rebuild(tmp_path):
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    remember_signature(tmp_path, make_ipa(tmp_path, now + timedelta(days=7)))
    assert signature_note(signature(tmp_path, now)) == ""
    soon = signature(tmp_path, now + timedelta(days=5, hours=12))
    assert soon["days_left"] == 1.5
    assert "runs out" in signature_note(soon) and "rebuild it on the Mac" in signature_note(soon)


def test_a_run_out_signature_is_refused_before_anything_starts(tmp_path, capsys):
    ipa = make_ipa(tmp_path, datetime.now(UTC) - timedelta(hours=1))
    assert main(["wda", str(ipa), "--state", str(tmp_path)]) == 1
    assert "signature ran out" in capsys.readouterr().err
    assert main(["wda", "--state", str(tmp_path)]) == 1


def test_status_and_devices_carry_the_reminder(tmp_path, monkeypatch, capsys):
    remember_signature(tmp_path, make_ipa(tmp_path, datetime.now(UTC) + timedelta(days=1)))
    wda = report(tmp_path)["wda"]
    assert wda["days_left"] < 2 and "runs out" in wda["note"]
    monkeypatch.setenv("SPARSH_WDA", "http://127.0.0.1:9")
    monkeypatch.setattr("sparsh.cli.attached", lambda: [])
    main(["devices", "--state", str(tmp_path)])
    assert "Note: the iPhone's WebDriverAgent signature runs out" in capsys.readouterr().out


def test_an_ipa_with_no_profile_says_what_it_is_not(tmp_path):
    ipa = tmp_path / "other.ipa"
    with zipfile.ZipFile(ipa, "w") as packed:
        packed.writestr("Payload/Other.app/Info.plist", b"")
    with pytest.raises(SparshError, match="carries no signing profile"):
        signed_until(ipa)
