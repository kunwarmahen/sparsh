"""An iPhone read and worked through WebDriverAgent, without an iPhone.

The bias these tests encode: AN IPHONE IS NOT A SECOND-CLASS PHONE. The
failure guarded against is a backend that "works" in the narrow sense
-- it sends taps -- while quietly dropping what the Android side was
built to keep: a row's words folded into one line, a switch's state, a
password field that hides its letters, a disabled button that says so,
the check that a number still means what it meant. So the screens go
through the same reader and the same Phone, and the HTTP calls are
checked as a stand-in WebDriverAgent received them.

The screens in ``screens/ios`` are in the shape WDA's ``/source``
prints (XCUIElementType... nodes with label, value, name and
x/y/width/height). ``settings`` and ``login`` are written by hand;
``home`` is a real iPhone's home screen on iOS 26, its personal words
(calendar entries, sleep, a street, amounts) replaced and its hidden
home-screen pages taken out.
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
#: ``spotlight`` is written by hand in the shape of the others: the home
#: screen's search, after "WhatsApp" was typed.
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
        self.after_tap = None  # called once a finger has been put down
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
                    if path.endswith("/actions") and fake.after_tap is not None:
                        fake.after_tap(body)
                    self._reply(None)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def posts(self) -> list[tuple[str, object]]:
        """What was done, leaving out the reading settings sent once a session."""
        return [
            (path, body)
            for method, path, body in self.calls
            if method == "POST" and path != "/appium/settings"
        ]

    def tunings(self) -> list[object]:
        return [body for method, path, body in self.calls if path == "/appium/settings"]


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


def test_a_real_home_screen_is_its_icons_and_widgets_one_line_each():
    screen = read(as_android(ios("home"), "com.apple.springboard"))
    assert screen.text().splitlines() == [
        "App: com.apple.springboard",
        '1 item "Google Calendar (Widget, Stack)" [tap]',
        '2 item "Coinbase (Widget)" [tap]',
        '3 item "Sleep (Widget)" [tap]',
        '4 item "Home MP3 Hub - YouTube Downloader" [tap]',
        '5 item "ntfy" [tap]',
        '6 item "Find My (Widget)" [tap]',
        '7 item "Amtrak" [tap]',
        '8 item "WebDriverAgentRunner-Runner" [tap]',
        '9 text "Page 4 of 4"',
        '10 text "Dock"',
        '11 item "Phone" [tap]',
        '12 item "Messages" [tap]',
        '13 item "Brave" [tap]',
        '14 item "Settings" [tap]',
        '15 text "15:09"',
        '16 image "Grinning face"',
        '17 text "Cellular (4 of 4 bars, signal strength)"',
        '18 text "SSID, 3 of 3 Wi-Fi bars"',
        '19 text "100% battery power (Charging)"',
    ]


def test_nothing_inside_a_widget_gets_a_line_because_its_places_are_the_widgets_own():
    # The Calendar widget's event buttons sit at y=11..63 in the widget's
    # own coordinates: as screen places they would be the status bar.
    screen = read(as_android(ios("home"), "com.apple.springboard"))
    assert not any("Entry" in e.label or "October" in e.label for e in screen.elements)
    assert not any(e.kind == "list" for e in screen.elements)


def test_ios_26_settings_is_one_line_a_row_not_a_frame_and_a_button():
    screen = read(as_android(ios("settings26"), "com.apple.Preferences"))
    assert screen.text().splitlines() == [
        "App: com.apple.Preferences",
        '1 text "Settings"',
        '2 button "Asha Rao, Apple Account, iCloud, and more" [tap]',
        '3 button "Family" [tap]',
        '4 switch "Airplane Mode" [tap, off]',
        '5 button "Wi-Fi, HomeNet" [tap]',
        '6 button "Bluetooth, On" [tap]',
        '7 button "Cellular" [tap]',
        '8 button "Personal Hotspot, Off" [tap]',
        '9 button "Battery" [tap]',
        '10 button "VPN, Not Connected" [tap]',
        '11 button "General" [tap]',
        '12 button "Accessibility" [tap]',
        '13 field "Search" [type]',
        '14 button "Dictate" [tap]',
    ]


def test_an_ios_26_switch_is_tapped_on_its_knob_not_the_middle_of_its_row():
    screen = read(as_android(ios("settings26")))
    [switch] = [e for e in screen.elements if e.kind == "switch"]
    assert switch.label == "Airplane Mode"
    assert switch.bounds == (309, 366, 372, 395)  # the knob, at the row's right end


def test_a_row_voiceover_reads_as_one_is_one_line_not_row_button_and_arrow():
    lines = read(as_android(ios("general26"))).text().splitlines()
    assert lines[5:9] == [
        '5 item "About" [tap]',
        '6 item "Software Update" [tap]',
        '7 item "iPhone Storage" [tap]',
        '8 item "AppleCare & Warranty" [tap]',
    ]
    assert not any("chevron" in line for line in lines)


def test_a_scroll_bar_gets_no_line_even_when_it_says_it_is_visible():
    bar = ios("settings").replace(
        "</XCUIElementTypeTable>",
        '<XCUIElementTypeOther type="XCUIElementTypeOther" value="0%" '
        'label="Vertical scroll bar, 4 pages" enabled="true" visible="true" '
        'x="360" y="100" width="30" height="600" traits="Adjustable"/>'
        "</XCUIElementTypeTable>",
    )
    assert bar != ios("settings")
    assert "scroll bar" not in read(as_android(bar)).text()


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
    # No resting before the move: iOS 26 takes a finger that rests first
    # as a press and drag, and doesn't go back (seen on a real iPhone 17).
    assert not any(s["type"] == "pause" for s in steps)


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
    from sparsh import device

    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.setattr(device, "attached", lambda adb=None: [])
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


# -- an app that never goes still (WhatsApp, on a real iPhone) -----------


def test_the_reading_settings_go_once_a_session_and_again_after_one_lapses(iphone, wda):
    iphone.look()
    iphone.look()
    assert wda.tunings() == [
        {
            "settings": {
                "waitForIdleTimeout": 0,
                "animationCoolOffTimeout": 0,
                "snapshotMaxChildren": 30,
            }
        }
    ]
    iphone.device._session, iphone.device._tuned = "old", True
    iphone.tap(4)  # the lapsed session is opened again
    iphone.look()
    assert len(wda.tunings()) == 2


def test_the_childrens_cap_can_be_changed(monkeypatch):
    from sparsh.iphone import _tuning

    monkeypatch.setenv("SPARSH_IOS_MAX_CHILDREN", "60")
    assert _tuning()["snapshotMaxChildren"] == 60
    monkeypatch.setenv("SPARSH_IOS_MAX_CHILDREN", "lots")
    assert _tuning()["snapshotMaxChildren"] == 30


def test_the_apps_go_ios_listed_are_kept_and_opened_by_name(tmp_path, monkeypatch):
    from sparsh.iphone import installed_apps, remember_apps

    listing = (
        "net.whatsapp.WhatsApp \u200eWhatsApp 26.40.77\n"
        "com.google.Gmail Gmail 6.0.261005\n"
        "com.delta.iphone.ver1 Fly Delta 7.16.1\n"
    )
    assert remember_apps(tmp_path, listing)["net.whatsapp.WhatsApp"] == "WhatsApp"
    assert installed_apps(tmp_path)["com.delta.iphone.ver1"] == "Fly Delta"
    monkeypatch.setenv("SPARSH_STATE", str(tmp_path))
    device = WdaDevice("http://127.0.0.1:1")
    assert "net.whatsapp.WhatsApp" in device.apps()
    phone = Phone(device, tmp_path)
    assert phone.which_app("whatsapp") == "net.whatsapp.WhatsApp"
    assert phone.which_app("Fly Delta") == "com.delta.iphone.ver1"
    with pytest.raises(ValueError):
        remember_apps(tmp_path, "nothing useful here")


def test_a_scroll_rests_the_finger_before_lifting_it_so_the_page_does_not_coast(iphone, wda):
    # A finger lifted mid-move is a flick: on a real iPhone 17 one scroll
    # down Amazon's Completed refunds coasted past the five newest.
    iphone.look()
    iphone.scroll("down")
    ((path, body),) = wda.posts()
    steps = body["actions"][0]["actions"]
    assert [s["type"] for s in steps[-3:]] == ["pointerMove", "pause", "pointerUp"]
    assert steps[-2]["duration"] >= 150


def _box(
    label: str, inside: str = "", kind: str = "Other", y: int = 100, shown: bool = True
) -> str:
    seen = "true" if shown else "false"
    tag = f"XCUIElementType{kind}"
    return (f'<{tag} type="{tag}" label="{label}" x="0" y="{y}" width="390" '
            f'height="40" visible="{seen}">{inside}</{tag}>')  # fmt: skip


#: Amazon's menu as a real iPhone 17 described it, cut down: every box
#: around the links is named with all the words inside it, "Lists" is a
#: shortcut scrolled off to the right, and the header box holds its text.
AMAZON_MENU = (
    '<XCUIElementTypeApplication type="XCUIElementTypeApplication" label="Amazon" '
    'x="0" y="0" width="390" height="844" visible="true">'
    + _box("Your shortcuts Orders Account Lists",
           _box("Your shortcuts", _box("Your shortcuts", kind="StaticText"))
           + _box("Orders Account Lists",
                  _box("Orders", _box("Orders", _box("Orders", kind="Link", y=150), y=150), y=150)
                  + _box("Account", _box("Account", kind="Link", y=200), y=200)
                  + _box("Lists", _box("Lists", kind="Link", y=250, shown=False), y=250,
                         shown=False)))
    + _box("Seen today", _box("", _box("Today", kind="StaticText", y=400), y=400), y=400)
    + "</XCUIElementTypeApplication>"
)  # fmt: skip


def test_a_box_named_with_its_insides_words_says_nothing_of_its_own():
    # On a real iPhone 17 Amazon's menu came back as five long lines of the
    # same words, and a text "Orders" beside the item "Orders" to tap.
    lines = [e.line().split(" ", 1)[1] for e in read(as_android(AMAZON_MENU, "x")).elements]
    assert lines == [
        'text "Your shortcuts"',
        'item "Orders" [tap]',
        'item "Account" [tap]',
        'text "Seen today"',
        'text "Today"',
    ]


# -- an app not on the list: Spotlight ----------------------------------
# An app installed since the list was read over the cable (or with no
# cable to read it) was "no app matches". A person would swipe down on the
# home screen and type its name; so does Sparsh, and taps only a result
# that is that name, word for word.


@pytest.fixture
def spotlight(wda, tmp_path, monkeypatch):
    from sparsh import iphone as iphone_mod

    for pause in ("_SPOTLIGHT_OPENS", "_SPOTLIGHT_SETTLES"):
        monkeypatch.setattr(iphone_mod, pause, 0)
    monkeypatch.setenv("SPARSH_STATE", str(tmp_path))
    wda.source, wda.bundle = ios("spotlight"), "com.apple.springboard"
    return wda


def _finger_at(body) -> tuple[int, int]:
    first = body["actions"][0]["actions"][0]
    return first["x"], first["y"]


def test_an_app_not_on_the_list_is_found_in_spotlight_and_opened(spotlight, tmp_path):
    taps = []

    def opened(body):
        taps.append(_finger_at(body))
        if len(taps) == 2:          # the swipe, then the tap on the result
            spotlight.bundle, spotlight.source = "net.whatsapp.WhatsApp", ios("settings")

    spotlight.after_tap = opened
    phone = Phone(WdaDevice(spotlight.url), state=tmp_path, settle=0)
    screen = phone.open_app("WhatsApp")
    assert taps[1] == (52, 172)     # the icon, not the field, the key or "WhatsApp Business"
    assert ("/wda/keys", {"value": ["WhatsApp"]}) in spotlight.posts()
    assert "found by name in Spotlight: net.whatsapp.WhatsApp" in screen.text()
    kept = json.loads((tmp_path / "iphone-apps.json").read_text())
    assert kept == {"net.whatsapp.WhatsApp": "WhatsApp"}
    # the next open finds it on the list, with no search
    assert phone.which_app("whatsapp") == "net.whatsapp.WhatsApp"


def test_a_near_match_is_not_tapped(spotlight, tmp_path):
    phone = Phone(WdaDevice(spotlight.url), state=tmp_path, settle=0)
    with pytest.raises(SparshError, match="no app called 'WhatsApp Busi' on this iPhone"):
        phone.open_app("WhatsApp Busi")
    assert [p for p, _ in spotlight.posts()][-1] == "/wda/homescreen"   # left as found
    assert not (tmp_path / "iphone-apps.json").exists()


def test_return_is_never_pressed_so_no_name_becomes_a_web_search(spotlight, tmp_path):
    phone = Phone(WdaDevice(spotlight.url), state=tmp_path, settle=0)
    with pytest.raises(SparshError):
        phone.open_app("Nothing Like It")
    typed = [b["value"] for p, b in spotlight.posts() if p.endswith("/wda/keys")]
    assert typed == [["Nothing Like It"]]


def test_an_app_the_rules_keep_out_is_left_for_home_at_once(spotlight, tmp_path):
    from sparsh.rules import Rules

    def opened(body):
        spotlight.bundle = "net.whatsapp.WhatsApp"

    spotlight.after_tap = opened
    phone = Phone(WdaDevice(spotlight.url), state=tmp_path, settle=0,
                  rules=Rules(never=("net.whatsapp.*",)))
    with pytest.raises(SparshError, match="off limits"):
        phone.open_app("WhatsApp")
    assert [p for p, _ in spotlight.posts()][-1] == "/wda/homescreen"
