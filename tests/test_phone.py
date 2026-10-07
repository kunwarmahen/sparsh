"""Numbers back into taps, and the refusal when the screen moved.

The bias these tests encode: NOTHING IS TAPPED THAT WASN'T READ. The
failure guarded against is the cheap one -- remember coordinates from
the last look and tap them blind, so a screen that changed in between
(a dialog, a page that finished loading) takes a tap meant for
something else. Every test checks the actions the phone received, not
only what came back.
"""

import pytest

from sparsh import SparshError
from sparsh.device import KEYBOARD, AdbDevice, typeable
from sparsh.phone import Phone, ScreenChanged


def test_tap_hits_the_middle_of_the_thing_and_shows_where_it_led(phone, fake):
    phone.look()

    def go(f, action):
        if action[0] == "tap":
            f.current = "network"

    fake.after = go
    now = phone.tap(6)  # Network & internet, [0,705][1080,936]
    assert fake.actions == [("tap", 540, 820)]
    assert now.app == "com.android.settings"
    assert any(e.label == "Airplane mode" for e in now.elements)


def test_nothing_is_tapped_when_the_screen_moved(phone, fake):
    phone.look()
    fake.current = "home"
    with pytest.raises(ScreenChanged) as caught:
        phone.tap(6)
    assert fake.actions == []
    assert "Nothing was done" in str(caught.value)
    assert caught.value.screen.app == "com.google.android.apps.nexuslauncher"


def test_the_same_thing_at_a_new_number_is_still_found(phone, fake):
    phone.look()
    # A screen with one more line at the top: everything shifts by one.
    extra = (
        '<node index="0" text="Banner" resource-id="" class="android.widget.TextView" '
        'package="com.android.settings" content-desc="" checkable="false" checked="false" '
        'clickable="false" enabled="true" focusable="false" focused="false" '
        'scrollable="false" long-clickable="false" password="false" selected="false" '
        'bounds="[0,0][1080,40]" />'
    )
    fake.screens["shifted"] = fake.screens["settings"].replace(
        '<hierarchy rotation="0">', '<hierarchy rotation="0">' + extra, 1
    )
    fake.current = "shifted"
    phone.tap(6)
    assert fake.actions == [("tap", 540, 820)]


def test_a_number_needs_a_look_first(phone):
    with pytest.raises(SparshError, match="look first"):
        phone.tap(1)


def test_a_number_not_on_the_screen(phone):
    phone.look()
    with pytest.raises(SparshError, match="no 99"):
        phone.tap(99)


def test_two_programs_agree_on_what_a_number_means(fake, tmp_path):
    Phone(fake, state=tmp_path, settle=0).look()
    Phone(fake, state=tmp_path, settle=0).tap(4)  # Search settings
    assert fake.actions == [("tap", 540, 594)]


def test_type_into_a_field_clearing_it_first(phone, fake):
    fake.current = "settings_search_typed"
    phone.look()
    phone.type("wifi", into=2, clear=True, enter=True)
    tap, clear, text, enter = fake.actions
    assert tap[0] == "tap"
    assert clear[:2] == ("keys", "end") and clear.count("delete") == len("hello world") + 5
    assert text == ("text", "wifi")
    assert enter == ("keys", "enter")


def test_typing_into_something_that_is_not_a_field(phone):
    phone.look()
    with pytest.raises(SparshError, match="not a field"):
        phone.type("x", into=3)


def test_scroll_down_pushes_the_page_up(phone, fake):
    phone.look()
    phone.scroll("down")
    _, x1, y1, x2, y2 = fake.actions[0]
    assert x1 == x2 == 540 and y1 > y2


def test_scroll_one_list(phone, fake):
    phone.look()
    phone.scroll("up", on=5)  # main content, [0,705][1080,2337]
    _, _, y1, _, y2 = fake.actions[0]
    assert 705 < y1 < y2 < 2337


def test_open_an_app_by_its_everyday_name(phone, fake):
    assert phone.which_app("settings") == "com.android.settings"
    assert phone.which_app("Messages") == "com.google.android.apps.messaging"
    assert phone.which_app("com.android.chrome") == "com.android.chrome"
    phone.open_app("youtube")
    assert fake.actions == [("launch", "com.google.android.youtube")]


def test_an_app_that_is_not_there_lists_the_ones_that_are(phone):
    with pytest.raises(SparshError, match="com.android.chrome"):
        phone.which_app("whatsapp")


def test_typing_is_quoted_for_the_phones_shell():
    assert typeable("it's a b&c") == ["'it'\\''s%sa%sb&c'"]
    assert typeable("") == []
    assert len(typeable("x" * 450)) == 3


@pytest.mark.parametrize("text", ["café", "नमस्ते", "🙂", "100%sure"])
def test_what_input_cannot_type_is_refused_in_words(text, phone, fake):
    with pytest.raises(SparshError, match="can't type"):
        typeable(text)
    with pytest.raises(SparshError, match="ADBKeyBoard"):
        phone.type(text, into=2)
    assert fake.actions == []  # refused before the field was tapped


def test_with_the_keyboard_app_anything_is_typed(phone, fake):
    fake.keyboard = True
    phone.type("नमस्ते 🙂")
    phone.type("plain")
    assert fake.actions == [("keyboard", "नमस्ते 🙂"), ("text", "plain")]


class Shell(AdbDevice):
    """An AdbDevice that writes down what it would run on the phone."""

    def __init__(self, answers):
        self.serial, self.adb, self._keyboard = "fake", "adb", False
        self.answers, self.ran = answers, []

    def _shell(self, *args, timeout=30):
        self.ran.append(" ".join(args))
        return next(
            (out for start, out in self.answers.items() if self.ran[-1].startswith(start)), ""
        )


LATIN = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"


def test_the_keyboard_app_is_used_and_the_persons_own_put_back(monkeypatch):
    monkeypatch.setattr("sparsh.device.time.sleep", lambda s: None)
    phone = Shell(
        {
            "pm list": f"package:{KEYBOARD.split('/')[0]}\n",
            "settings get": LATIN + "\n",
            "ime list": LATIN + "\n",
        }
    )
    phone.type_text("café")
    assert phone.ran == [
        "pm list packages com.android.adbkeyboard",
        "settings get secure default_input_method",
        "ime list -s",
        f"ime enable {KEYBOARD}",
        f"ime set {KEYBOARD}",
        "am broadcast -a ADB_INPUT_B64 --es msg Y2Fmw6k=",  # café
        f"ime set {LATIN}",
        f"ime disable {KEYBOARD}",  # off the list again: it wasn't on it
    ]
    phone.ran.clear()
    phone.type_text("it's plain")
    assert phone.ran == ["input text 'it'\\''s%splain'"]


def test_without_the_keyboard_app_nothing_is_run_but_the_check():
    phone = Shell({"pm list": ""})
    with pytest.raises(SparshError, match="ADBKeyBoard"):
        phone.type_text("100%sure")
    assert phone.ran == ["pm list packages com.android.adbkeyboard"]


def test_an_unknown_key(phone):
    with pytest.raises(SparshError, match="no key called 'jump'"):
        phone.key("jump")


def test_a_page_that_never_goes_still_says_to_leave_it(monkeypatch):
    from sparsh.device import AdbDevice
    from sparsh.screen import ScreenUnreadable

    class Done:
        stdout = b"ERROR: could not get idle state.\n"
        stderr = b""

    monkeypatch.setattr("sparsh.device._run", lambda *a, **k: Done())
    monkeypatch.setattr("sparsh.device.time.sleep", lambda s: None)
    with pytest.raises(ScreenUnreadable, match="Press back to leave this page"):
        AdbDevice("emulator-5556", adb="adb").dump()


def test_a_tap_that_lands_on_an_unreadable_page_says_it_was_done(phone, fake):
    phone.look()
    fake.screens["ticking"] = "ERROR: could not get idle state."

    def go(f, action):
        if action[0] == "tap":
            f.current = "ticking"

    fake.after = go
    now = phone.tap(6)
    assert fake.actions == [("tap", 540, 820)]
    assert now.text().startswith("App: (unknown)\nDone. But the screen it led to can't be read")
    # The last look is the one the agent read, so a number from it is
    # checked against a screen that can't be found -- and refused.
    with pytest.raises(SparshError):
        phone.tap(6)
    assert fake.actions == [("tap", 540, 820)]


def test_an_app_that_reopens_on_an_unreadable_page_is_backed_out_of_it(phone, fake):
    # Settings reopens where it was left -- here, a page whose clock ticks.
    fake.screens["ticking"] = "ERROR: could not get idle state."
    fake.current = "home"

    def go(f, action):
        if action[0] == "launch":
            f.current = "ticking"
        elif action == ("keys", "back"):
            f.current = "settings"

    fake.after = go
    now = phone.open_app("settings")
    assert fake.actions == [("launch", "com.android.settings"), ("keys", "back")]
    assert "back was pressed once" in now.text()
    assert any(e.label == "Search settings" for e in now.elements)


def test_an_app_that_opens_readable_is_left_alone(phone, fake):
    fake.current = "home"
    fake.after = lambda f, action: setattr(f, "current", "settings")
    now = phone.open_app("settings")
    assert fake.actions == [("launch", "com.android.settings")]
    assert "back was pressed" not in now.text()
