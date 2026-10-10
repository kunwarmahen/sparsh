"""The agent's tools, over the wire a harness speaks.

The bias these tests encode: WHAT A HARNESS ASKS ABOUT IS DECIDED BY
THE KINDS, AND THE KINDS DON'T LIE. Reads say readOnlyHint; every act
says it changes things; confirm -- the one way through a hold -- says
it is destructive, so any harness asks. The second bias: every failure
reaches the model as readable text with isError, never a crash of the
server, and every act hands back the screen it led to. The third: A
PICTURE ONLY WHERE THE LIST FALLS SHORT (nothing, part, or asked for),
only when turned on, and never of an app the person keeps the agent
out of. The fourth: A TAP BY POSITION IS HELD EVERY TIME, only on a
screen that came with a picture. The fifth: A PERSON IS ASKED WITH A
PICTURE AND A SENTENCE, never the model's numbered list, unless no
picture can be had.
"""

import base64
import io
import json

import pytest

from sparsh import SparshError, mcp, picture
from sparsh.rules import AppRule, Rules
from sparsh.status import FORMAT, report

from .conftest import PLACES
from .test_rules import SEND


@pytest.fixture
def tools(fake, tmp_path):
    fake.screens["send"] = SEND
    return mcp.Tools(Rules(), state=tmp_path, device=fake, settle=0)


def call(tools, tool, **args):
    reply = mcp.answer(
        tools,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": tool, "arguments": args}},
    )  # fmt: skip
    result = reply["result"]
    return result["content"][0]["text"], result["isError"]


def test_the_kinds():
    assert mcp.KINDS == {
        "look": "read", "list_apps": "read", "describe_hold": "read",
        "tap": "act", "tap_at": "act", "type_text": "act", "scroll": "act", "press_key": "act",
        "open_app": "act", "confirm": "confirm",
    }  # fmt: skip
    confirm = next(t for t in mcp.TOOLS if t["name"] == "confirm")
    assert confirm["annotations"]["destructiveHint"] is True


def test_look_then_tap_returns_the_next_screen(tools, fake):
    text, failed = call(tools, "look")
    assert not failed and '6 item "Network & internet' in text

    fake.after = lambda f, a: setattr(f, "current", "network")
    text, failed = call(tools, "tap", n=6)
    assert not failed and "Airplane mode" in text


def test_a_held_send_then_its_yes(tools, fake):
    fake.current = "send"
    call(tools, "look")
    text, failed = call(tools, "tap", n=2)
    assert failed and text.startswith("NOT DONE") and fake.actions == []
    hold = text.split('hold "')[1].split('"')[0]

    told, failed = call(tools, "describe_hold", hold=hold)
    assert not failed and "running late" in told

    text, failed = call(tools, "confirm", hold=hold)
    assert not failed and text.startswith("Done:")
    assert fake.actions == [("tap", 990, 2100)]


def test_a_moved_screen_is_an_error_with_the_new_screen(tools, fake):
    call(tools, "look")
    fake.current = "home"
    text, failed = call(tools, "tap", n=6)
    assert failed and "Nothing was done" in text and "nexuslauncher" in text


@pytest.mark.parametrize(
    "name,args,said",
    [
        ("tap", {"n": "six"}, "a number from the screen list"),
        ("tap", {"n": 0}, "1 or more"),
        ("type_text", {}, "missing: text"),
        ("type_text", {"text": "café"}, "can't type"),
        ("press_key", {"keys": ["jump"]}, "no key called"),
        ("open_app", {"name": "whatsapp"}, "no app matches"),
        ("confirm", {"hold": "h000000"}, "no step is waiting"),
        ("nothing", {}, "no tool"),
        ("tap", {"ref": "5"}, "tap has no argument `ref` -- use `n`"),
        ("type_text", {"ref": 4, "text": "hi"}, "no argument `ref` -- use `into`"),
        ("open_app", {"app": "settings"}, "use `name`"),
    ],
)
def test_mistakes_are_sentences(tools, name, args, said):
    call(tools, "look")
    text, failed = call(tools, name, **args)
    assert failed and said in text


def test_the_wire(tools):
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list"},
    ]  # fmt: skip
    out = io.StringIO()
    mcp.serve(tools, io.StringIO("\n".join(json.dumps(m) for m in lines) + "\nnot json\n"), out)
    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert replies[0]["result"]["protocolVersion"] == "2024-11-05"
    assert len(replies[1]["result"]["tools"]) == 10
    assert replies[2]["error"]["code"] == -32601
    assert replies[3]["error"]["code"] == -32700


def test_status_names_the_contract_the_tools_and_the_rules(tmp_path, monkeypatch):
    monkeypatch.setattr("sparsh.status.attached", lambda: [])
    (tmp_path / "rules.toml").write_text('never = ["*bank*"]\n')
    data = report(tmp_path)
    assert data["format"] == FORMAT
    assert data["tools"] == mcp.KINDS
    assert data["mcp"]["args"] == ["mcp", "--state", str(tmp_path)]
    assert data["shots"] == "--shots"  # added to args only when allowed
    assert data["rules"]["never"] == ["*bank*"] and data["rules"]["exists"]
    assert data["phones"] == [] and data["adb"] == "ok"


# -- a picture only where the list has nothing (--shots) ----------------


def answer(tools, tool, **args):
    reply = mcp.answer(
        tools,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": tool, "arguments": args}},
    )  # fmt: skip
    return reply["result"]["content"]


def unreadable(fake, app="com.android.settings"):
    fake.screens["about"] = None  # a page that never goes still
    fake.current, fake.front = "about", app


def shots(fake, tmp_path, never=()):
    return mcp.Tools(Rules(never=never), state=tmp_path, device=fake, settle=0, shots=True)


def test_an_unreadable_screen_is_an_answer_with_its_app_not_a_failure(tools, fake):
    unreadable(fake)
    text, failed = call(tools, "look")
    assert not failed
    assert text.startswith("App: com.android.settings")
    assert "can't be read as a list" in text and "screen keeps changing" in text


def test_without_shots_no_picture_is_sent(tools, fake):
    unreadable(fake)
    assert [b["type"] for b in answer(tools, "look")] == ["text"]


def test_with_shots_an_unreadable_screen_comes_with_its_picture(fake, tmp_path):
    unreadable(fake)
    text, image = answer(shots(fake, tmp_path), "look")
    assert image["type"] == "image" and image["mimeType"] == "image/png"
    assert base64.b64decode(image["data"]).startswith(b"\x89PNG")
    assert "screenshot of this screen is attached" in text["text"]
    assert "tap_at its position" in text["text"]


def test_with_shots_a_readable_screen_is_still_only_the_list(fake, tmp_path):
    content = answer(shots(fake, tmp_path), "look")
    assert [b["type"] for b in content] == ["text"]


def test_an_act_that_leads_to_an_unreadable_screen_says_done_and_shows_it(fake, tmp_path):
    tools = shots(fake, tmp_path)
    call(tools, "look")
    fake.after = lambda f, action: unreadable(f)
    text, image = answer(tools, "tap", n=6)
    assert text["text"].startswith("App: com.android.settings")
    assert "Done. But the screen it led to can't be read" in text["text"]
    assert image["type"] == "image"


def test_no_picture_of_an_app_the_rules_keep_out(fake, tmp_path):
    unreadable(fake, app="com.chase.sig.android")
    content = answer(shots(fake, tmp_path, never=("com.chase.*",)), "look")
    assert [b["type"] for b in content] == ["text"]
    assert "off limits" in content[0]["text"]


def test_no_picture_of_an_app_that_cant_be_named_while_some_are_kept_out(fake, tmp_path):
    unreadable(fake, app="")
    kept = answer(shots(fake, tmp_path, never=("com.chase.*",)), "look")
    assert [b["type"] for b in kept] == ["text"]
    free = answer(shots(fake, tmp_path), "look")
    assert [b["type"] for b in free] == ["text", "image"]


# -- a tap by position: only on a screen with a picture, held every time --


def a_png(width=100, height=200, colour=(0, 0, 0), dot=False):
    rows = [bytearray(colour * width) for _ in range(height)]
    if dot:  # a few pixels change, as a ticking clock's do
        rows[0][0:12] = bytes([255] * 12)
    return picture._encode(width, height, rows)


def test_a_tap_by_position_is_held_and_shown_ringed_then_done_on_yes(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, failed = call(tools, "tap_at", x=500, y=250)
    assert failed and text.startswith("NOT DONE") and fake.actions == []
    assert "tap the spot ringed on the picture (x 500, y 250 of 1000)" in text
    hold = text.split('hold "')[1].split('"')[0]

    told, shown = answer(tools, "describe_hold", hold=hold)
    assert "tap by position" in told["text"] and "in Settings" in told["text"]
    ringed = base64.b64decode(shown["data"])
    assert picture.size(ringed) == (100, 200) and ringed != a_png()

    text, failed = call(tools, "confirm", hold=hold)
    assert not failed and text.startswith("Done:")
    assert fake.actions == [("tap", 49, 49)]  # the same share of the screen


def test_no_tap_by_position_where_the_list_has_something(tools, fake):
    text, failed = call(tools, "tap_at", x=500, y=500)
    assert failed and "tap by number" in text and fake.actions == []


def test_a_tap_by_position_is_not_done_if_the_app_changed(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, _ = call(tools, "tap_at", x=10, y=10)
    hold = text.split('hold "')[1].split('"')[0]
    fake.front = "com.google.android.youtube"
    text, failed = call(tools, "confirm", hold=hold)
    assert failed and "nothing was tapped" in text and fake.actions == []


def test_a_tap_by_position_is_not_done_on_a_screen_unlike_its_picture(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, _ = call(tools, "tap_at", x=10, y=10)
    hold = text.split('hold "')[1].split('"')[0]
    fake.screenshot = lambda: a_png(colour=(255, 255, 255))  # a dialog opened, say
    text, failed = call(tools, "confirm", hold=hold)
    assert failed and "not the one in the picture" in text and fake.actions == []


def test_a_clock_ticking_on_the_screen_is_still_its_picture(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, _ = call(tools, "tap_at", x=10, y=10)
    hold = text.split('hold "')[1].split('"')[0]
    fake.screenshot = lambda: a_png(dot=True)
    text, failed = call(tools, "confirm", hold=hold)
    assert not failed and fake.actions == [("tap", 0, 1)]


def test_no_tap_by_position_in_an_app_whose_words_are_refused(fake, tmp_path):
    unreadable(fake, app="com.twitter.android")
    rules = Rules(apps={"com.twitter.android": AppRule(refuse=("post",), why="Setu: read only")})
    tools = mcp.Tools(rules, state=tmp_path, device=fake, settle=0, shots=True)
    text, failed = call(tools, "tap_at", x=10, y=10)
    assert failed and "no words to check" in text and "Setu: read only" in text


def test_a_spot_off_the_picture_is_a_sentence(fake, tmp_path):
    unreadable(fake)
    text, failed = call(shots(fake, tmp_path), "tap_at", x=1200, y=10)
    assert failed and "0 to 1000" in text


def test_typing_on_a_screen_with_no_list_is_held_with_its_picture(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, failed = call(tools, "type_text", text="Asha's phone", enter=True)
    assert failed and text.startswith("NOT DONE") and fake.actions == []
    assert "where the keyboard is, on the screen in the picture" in text
    hold = text.split('hold "')[1].split('"')[0]
    told, shown = answer(tools, "describe_hold", hold=hold)
    assert "Asha's phone" in told["text"] and base64.b64decode(shown["data"]) == a_png()
    text, failed = call(tools, "confirm", hold=hold)
    assert not failed
    assert fake.actions == [("text", "Asha's phone"), ("keys", "enter")]


def test_a_yes_on_a_screen_with_no_list_comes_back_with_its_picture(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png()
    tools = shots(fake, tmp_path)
    text, _ = call(tools, "tap_at", x=10, y=10)
    hold = text.split('hold "')[1].split('"')[0]
    said, shown = answer(tools, "confirm", hold=hold)
    assert said["text"].startswith("Done:") and shown["type"] == "image"


# -- a list that falls short: a picture with it, or one asked for ------------


def places(fake):
    fake.screens["places"] = PLACES
    fake.current = "places"


def test_a_partly_blank_screen_comes_with_its_picture_and_says_why(fake, tmp_path):
    places(fake)
    text, image = answer(shots(fake, tmp_path), "look")
    assert image["type"] == "image"
    assert "3 things on it to tap have no words" in text["text"]
    assert "Tap by number whatever the list has" in text["text"]


def test_a_lock_screen_with_unnamed_notifications_comes_without_a_picture(fake, tmp_path):
    fake.screens["places"] = PLACES.replace("com.google.android.apps.maps", "com.android.systemui")
    fake.current, fake.locked = "places", True
    content = answer(shots(fake, tmp_path), "look")
    assert [b["type"] for b in content] == ["text"] and "locked" in content[0]["text"]


def test_a_partly_blank_screen_without_shots_is_only_the_list(tools, fake):
    places(fake)
    assert [b["type"] for b in answer(tools, "look")] == ["text"]


def test_a_picture_can_be_asked_for_on_any_screen(fake, tmp_path):
    text, image = answer(shots(fake, tmp_path), "look", picture=True)
    assert image["type"] == "image" and "you asked for it" in text["text"]


def test_a_picture_asked_for_without_shots_says_there_is_none(tools, fake):
    content = answer(tools, "look", picture=True)
    assert [b["type"] for b in content] == ["text"]
    assert "No picture" in content[0]["text"]


def test_a_tap_by_position_is_for_a_screen_that_came_with_a_picture(fake, tmp_path):
    tools = shots(fake, tmp_path)
    call(tools, "look", picture=True)
    text, failed = call(tools, "tap_at", x=500, y=500)
    assert failed and text.startswith("NOT DONE") and fake.actions == []
    call(tools, "look")  # the next look, no picture with it
    text, failed = call(tools, "tap_at", x=500, y=500)
    assert failed and "look with picture first" in text and fake.actions == []


def test_a_tap_by_position_on_a_partly_blank_screen_is_held(fake, tmp_path):
    places(fake)
    fake.screenshot = lambda: a_png()
    text, failed = call(shots(fake, tmp_path), "tap_at", x=300, y=700)
    assert failed and text.startswith("NOT DONE") and fake.actions == []


# -- what the person is shown for a held step --------------------------------


def test_a_held_tap_is_shown_as_its_picture_ringed_not_the_list(tools, fake):
    fake.current = "send"
    fake.screenshot = lambda: a_png(1080, 2400)
    call(tools, "look")
    text, _ = call(tools, "tap", n=2)
    hold = text.split('hold "')[1].split('"')[0]
    told, shown = answer(tools, "describe_hold", hold=hold)
    assert 'tap button "Send SMS"' in told["text"]
    assert 'On the screen: field "running late"' in told["text"]
    assert "The screen when it was asked for" not in told["text"]
    ringed = base64.b64decode(shown["data"])
    assert picture.size(ringed)[0] <= picture.WIDTH and ringed != a_png(1080, 2400)


def test_with_no_screenshot_the_held_step_is_said_with_the_list(tools, fake):
    fake.current = "send"

    def broken():
        raise SparshError("screencap failed")

    fake.screenshot = broken
    call(tools, "look")
    text, _ = call(tools, "tap", n=2)
    hold = text.split('hold "')[1].split('"')[0]
    content = answer(tools, "describe_hold", hold=hold)
    assert [b["type"] for b in content] == ["text"]
    assert "The screen when it was asked for" in content[0]["text"]


def test_a_yes_comes_back_as_done_with_the_phones_own_answer(tools, fake):
    fake.current = "send"
    call(tools, "look")
    text, _ = call(tools, "tap", n=2)
    hold = text.split('hold "')[1].split('"')[0]
    text, failed = call(tools, "confirm", hold=hold)
    assert not failed and text.startswith("Done: the step was carried out.")


def test_the_models_picture_is_made_smaller(fake, tmp_path):
    unreadable(fake)
    fake.screenshot = lambda: a_png(1440, 2560)
    _, image = answer(shots(fake, tmp_path), "look")
    assert picture.size(base64.b64decode(image["data"])) == (720, 1280)


def test_a_held_step_names_the_phone_not_its_address(tools, fake):
    fake.current = "send"
    fake.name = lambda: "Nexus 6P"
    call(tools, "look")
    text, _ = call(tools, "tap", n=2)
    hold = text.split('hold "')[1].split('"')[0]
    told, failed = call(tools, "describe_hold", hold=hold)
    assert told.startswith('On your phone (Nexus 6P): tap button "Send SMS" in Messages --')
    assert "fake" not in told.split(":")[0]  # the serial, not shown
