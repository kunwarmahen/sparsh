"""The agent's tools, over the wire a harness speaks.

The bias these tests encode: WHAT A HARNESS ASKS ABOUT IS DECIDED BY
THE KINDS, AND THE KINDS DON'T LIE. Reads say readOnlyHint; every act
says it changes things; confirm -- the one way through a hold -- says
it is destructive, so any harness asks. The second bias: every failure
reaches the model as readable text with isError, never a crash of the
server, and every act hands back the screen it led to. The third: A
PICTURE ONLY WHERE THE LIST HAS NOTHING, only when turned on, and never
of an app the person keeps the agent out of.
"""

import base64
import io
import json

import pytest

from sparsh import mcp
from sparsh.rules import Rules
from sparsh.status import FORMAT, report

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
        "tap": "act", "type_text": "act", "scroll": "act", "press_key": "act",
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
    assert not failed and text.startswith("Done.")
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
    assert len(replies[1]["result"]["tools"]) == 9
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
    assert "Only numbered things can be tapped" in text["text"]


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
