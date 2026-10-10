"""Reading the screen: the list a model answers with a number from.

The bias these tests encode: ONE LINE PER THING A PERSON WOULD POINT AT.
The failure guarded against is the raw tree leaking through -- a
Settings row shown as five lines (box, icon, frame, title, summary), its
words shown twice, an upside-down box offered as something to tap. The
screens are real dumps from the Android 15 emulator, not hand-made
XML, except where a case (a password, a quote) needs one.
"""

import pytest

from sparsh.screen import ScreenUnreadable, read

from .conftest import BLANK_PAGE, FILLED_PAGE, PLACES, screen


def lines(name: str) -> list[str]:
    return read(screen(name)).text().splitlines()


def test_a_settings_row_takes_its_words_from_inside():
    shown = lines("settings")
    assert shown[0] == "App: com.android.settings"
    assert '6 item "Network & internet — Mobile, Wi‑Fi, hotspot" [tap]' in shown
    # The words used as the row's label don't get lines of their own.
    assert not any(line.endswith('text "Network & internet"') for line in shown)


def test_a_row_half_off_the_bottom_keeps_its_label_but_not_the_upside_down_parts():
    shown = lines("settings")
    assert shown[-1] == '13 item "Display & touch" [tap]'
    s = read(screen("settings"))
    assert all(e.bounds[3] - e.bounds[1] >= 10 for e in s.elements)


def test_a_switch_inside_a_row_is_the_rows_on_or_off():
    shown = lines("network")
    assert '6 item "Airplane mode" [tap, off]' in shown
    assert not any(" switch" in line for line in shown)


def test_a_field_says_it_takes_typing_and_has_focus():
    assert '2 field "hello world" [tap, type, focused]' in lines("settings_search_typed")


def test_launcher_icons_prefer_the_longer_description():
    shown = lines("home")
    assert '5 text "Play Store has 1 notification" [tap]' in shown
    assert '6 text "Gmail" [tap]' in shown


def test_unlabelled_lists_are_told_apart_by_the_apps_own_names():
    shown = lines("settings")
    assert '1 list "settings homepage container" [scroll]' in shown
    assert '5 list "main content scrollable container" [scroll]' in shown


def test_numbers_run_in_order_from_one():
    s = read(screen("drawer"))
    assert [e.n for e in s.elements] == list(range(1, len(s.elements) + 1))
    assert s.size == (1080, 2400)


def test_the_trailer_adb_prints_after_the_xml_is_ignored():
    xml = screen("network") + "UI hierchary dumped to: /dev/tty\n"
    assert read(xml).app == "com.android.settings"


def _node(**attrs) -> str:
    base = {
        "text": "",
        "resource-id": "",
        "class": "android.widget.EditText",
        "package": "com.bank",
        "content-desc": "",
        "checkable": "false",
        "checked": "false",
        "clickable": "true",
        "enabled": "true",
        "focusable": "true",
        "focused": "false",
        "scrollable": "false",
        "long-clickable": "false",
        "password": "false",
        "selected": "false",
        "bounds": "[0,0][500,100]",
    }
    base.update(attrs)
    return "<node " + " ".join(f'{k}="{v}"' for k, v in base.items()) + " />"


def _xml(*nodes: str) -> str:
    return "<?xml version='1.0' ?><hierarchy rotation=\"0\">" + "".join(nodes) + "</hierarchy>"


def test_what_is_in_a_password_field_is_not_shown():
    s = read(_xml(_node(text="••••••", password="true")))
    assert s.elements[0].line() == '1 field "(hidden)" [tap, type, password]'


def test_a_quote_in_a_label_cannot_end_the_label():
    s = read(_xml(_node(text="say &quot;hi&quot;", **{"class": "android.widget.TextView"})))
    assert s.elements[0].line() == '1 text "say \\"hi\\"" [tap]'


def test_a_switched_off_button_says_so():
    s = read(_xml(_node(text="Pay", enabled="false", **{"class": "android.widget.Button"})))
    assert s.elements[0].line() == '1 button "Pay" [tap, disabled]'


@pytest.mark.parametrize(
    "said",
    ["ERROR: could not get idle state.", "", "<?xml version='1.0' ?><hierarchy><node"],
)
def test_no_screen_is_a_sentence_not_a_crash(said):
    with pytest.raises(ScreenUnreadable):
        read(said)


# -- a list that is there and still says nothing ---------------------------


def test_unnamed_places_make_a_screen_partly_blank_but_a_backdrop_does_not_count():
    s = read(PLACES)
    assert s.blanks == 3  # the three places; not the screen-sized backdrop
    assert s.partly_blank and not s.blank_page


def test_two_unnamed_things_are_not_enough():
    s = read(PLACES.replace('<node index="0" text="" resource-id="" class="android.view.View" '
                            'package="com.google.android.apps.maps" content-desc="" '
                            'checkable="false" checked="false" clickable="true" enabled="true" '
                            'focusable="false" focused="false" scrollable="false" '
                            'long-clickable="false" password="false" selected="false" '
                            'bounds="[595,1453][1092,1922]"></node>', ""))  # fmt: skip
    assert s.blanks == 2 and not s.partly_blank


def test_a_web_page_with_no_words_in_the_list_is_a_blank_page():
    assert read(BLANK_PAGE).blank_page and read(BLANK_PAGE).partly_blank
    assert not read(FILLED_PAGE).blank_page


def test_the_saved_screens_are_not_blank():
    for name in ("settings", "network", "home", "drawer", "settings_search"):
        assert not read(screen(name)).partly_blank, name
