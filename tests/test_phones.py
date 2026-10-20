"""Several phones in one server, each by a name.

The bias these tests encode: ONE PHONE'S SCREEN NEVER STEERS ANOTHER.
A number read on the Nexus never taps the iPhone; a step held on one
is done on that one, by its id alone; every answer names its phone, so
the model can't mistake whose screen it read. The second: A PHONE THE
SERVER WASN'T GIVEN CAN'T BE REACHED -- a harness that names only a
person's own phones has kept the rest out. The third: UNNAMED IS
TODAY; one named phone needs no name in any call.
"""

import json

import pytest

from sparsh import SparshError, awake, cli, mcp, phones
from sparsh.device import over_wifi
from sparsh.fake import FakeDevice
from sparsh.rules import Rules
from sparsh.status import report

from .conftest import APPS, SCREENS, screen
from .test_mcp import call
from .test_rules import SEND

TWO = {"nexus": "192.168.1.160:5555", "iphone": "http://127.0.0.1:8100"}


def fake(serial: str, start: str) -> FakeDevice:
    screens = {p.stem: screen(p.stem) for p in SCREENS.glob("*.xml")}
    screens["send"] = SEND
    return FakeDevice(screens, start=start, apps=APPS, serial=serial)


@pytest.fixture
def two(tmp_path):
    nexus, iphone = fake(TWO["nexus"], "settings"), fake(TWO["iphone"], "home")
    tools = mcp.Tools(Rules(), state=tmp_path, settle=0, phones=TWO,
                      devices={"nexus": nexus, "iphone": iphone})
    return tools, nexus, iphone


def test_names_are_read_in_order_and_mistakes_are_sentences():
    assert phones.parse("nexus=192.168.1.160:5555, iphone=http://127.0.0.1:8100") == TWO
    assert list(phones.parse("b=1.2.3.4:5,a=x")) == ["b", "a"]
    for raw, said in [("Nexus=x", "lower case"), ("nexus", "NAME=WHERE"),
                      ("a=x,a=y", "named twice"), ("my phone=x", "lower case")]:
        with pytest.raises(SparshError, match=said):
            phones.parse(raw)


def test_a_bare_name_picks_and_a_named_one_adds():
    env = "nexus=192.168.1.160:5555,iphone=http://127.0.0.1:8100"
    assert phones.chosen(None, env) == TWO
    assert phones.chosen(["iphone"], env) == {"iphone": TWO["iphone"]}
    assert phones.chosen(["pixel=emulator-5554"], env) == {**TWO, "pixel": "emulator-5554"}
    with pytest.raises(SparshError, match=r"no phone is called 'pixel' \(nexus: Android, "
                                          r"iphone: iPhone\)"):
        phones.chosen(["pixel"], env)
    assert phones.chosen(None, "") == {}


def test_a_hand_command_needs_one_phone_when_several_are_named():
    env = "nexus=192.168.1.160:5555,iphone=http://127.0.0.1:8100"
    assert phones.one(None, "") is None
    assert phones.one(["nexus"], env) == ("nexus", TWO["nexus"])
    assert phones.one(None, "nexus=emulator-5554") == ("nexus", "emulator-5554")
    with pytest.raises(SparshError, match="which phone"):
        phones.one(None, env)


def test_with_two_phones_every_tool_but_the_holds_must_say_which(two):
    tools, _, _ = two
    listed = {t["name"]: t["inputSchema"] for t in tools.listed()}
    assert listed["tap"]["properties"]["phone"]["enum"] == ["nexus", "iphone"]
    assert "phone" in listed["look"]["required"]
    assert "phone" not in listed["confirm"].get("required", [])
    assert "phone" in listed["confirm"]["properties"]
    text, failed = call(tools, "look")
    assert failed and text == ("Not done: which phone? Say `phone`: nexus (Android), "
                               "iphone (iPhone)")


def test_a_phone_the_server_was_not_given_is_not_reached(two):
    tools, nexus, iphone = two
    text, failed = call(tools, "look", phone="pixel")
    assert failed and "there is no phone 'pixel'" in text
    assert nexus.tries == [] and iphone.tries == []


def test_every_answer_names_its_phone(two):
    tools, _, _ = two
    text, failed = call(tools, "look", phone="nexus")
    assert not failed and text.startswith("Phone: nexus\n") and "Network & internet" in text
    text, failed = call(tools, "look", phone="iphone")
    assert not failed and text.startswith("Phone: iphone\n")


def test_a_number_read_on_one_phone_never_taps_the_other(two):
    tools, nexus, iphone = two
    call(tools, "look", phone="nexus")
    text, failed = call(tools, "tap", phone="iphone", n=6)
    assert failed and iphone.actions == [] and nexus.actions == []
    nexus.after = lambda f, a: setattr(f, "current", "network")
    text, failed = call(tools, "tap", phone="nexus", n=6)
    assert not failed and "Airplane mode" in text and iphone.actions == []


def test_a_held_step_is_done_on_its_own_phone_by_its_id_alone(two):
    tools, nexus, iphone = two
    iphone.current = "send"
    call(tools, "look", phone="iphone")
    call(tools, "look", phone="nexus")
    text, failed = call(tools, "tap", phone="iphone", n=2)
    assert failed and text.startswith("NOT DONE") and iphone.actions == []
    hold = text.split('hold "')[1].split('"')[0]
    told, failed = call(tools, "describe_hold", hold=hold)
    assert not failed and told.startswith("Phone: iphone\n") and "running late" in told
    text, failed = call(tools, "confirm", hold=hold)
    assert not failed and text.startswith("Phone: iphone\nDone:")
    assert iphone.actions == [("tap", 990, 2100)] and nexus.actions == []


def test_each_phone_has_its_own_screen_keeper(two, monkeypatch):
    tools, nexus, iphone = two
    tools.awakes = {"nexus": awake.Awake("always"), "iphone": awake.Awake("off")}
    call(tools, "look", phone="nexus")
    call(tools, "look", phone="iphone")
    assert nexus.timeouts == [awake.NEVER_MS] and iphone.timeouts == []


def test_one_named_phone_needs_no_name_and_says_none(tmp_path):
    only = fake("emulator-5554", "settings")
    tools = mcp.Tools(Rules(), state=tmp_path, settle=0, phones={"pixel": "emulator-5554"},
                      devices={"pixel": only})
    assert tools.listed() is mcp.TOOLS
    text, failed = call(tools, "look")
    assert not failed and "Phone:" not in text
    text, failed = call(tools, "look", phone="pixel")
    assert not failed


def test_the_server_tells_the_model_the_phones(two):
    tools, _, _ = two
    reply = mcp.answer(tools, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {}})  # fmt: skip
    said = reply["result"]["instructions"]
    assert "2 phones: nexus (Android), iphone (iPhone)" in said


def test_awake_says_one_word_per_named_phone(monkeypatch):
    monkeypatch.setenv("SPARSH_PHONES", "nexus=192.168.1.160:5555,iphone=http://x:8100")
    raw = "nexus=always,iphone=off"
    assert awake.mode(raw, phone="nexus") == "always"
    assert awake.mode(raw, phone="192.168.1.160:5555") == "always"  # by where it is
    assert awake.mode(raw, phone="iphone") == "off"
    assert awake.mode(raw, phone="pixel") == "working"
    assert awake.mode("always", phone="iphone") == "always"
    with pytest.raises(SparshError, match="nexus='forever'"):
        awake.mode("nexus=forever")


def test_a_named_android_on_wifi_is_connected_to_like_sparsh_connect(monkeypatch):
    monkeypatch.setenv("SPARSH_CONNECT", "10.0.0.2:5555")
    monkeypatch.setenv("SPARSH_PHONES", "nexus=192.168.1.160:5555,usb=ENU7N15B,"
                                        "iphone=http://127.0.0.1:8100")
    assert over_wifi() == ["10.0.0.2:5555", "192.168.1.160:5555"]


def test_status_names_the_phones_answering_or_not(tmp_path, monkeypatch):
    monkeypatch.setattr("sparsh.status.attached", lambda: [])
    monkeypatch.setattr("sparsh.status.iphones", lambda state=None: [])
    data = report(tmp_path, {"nexus": "192.168.1.160:5555"})
    assert data["named"] == [{"name": "nexus", "where": "192.168.1.160:5555",
                              "kind": "Android"}]  # fmt: skip


def test_serial_and_phone_together_are_refused(capsys, monkeypatch):
    monkeypatch.setenv("SPARSH_PHONES", "nexus=emulator-5554")
    assert cli.main(["look", "--serial", "x", "--phone", "nexus"]) == 1
    assert "not both" in capsys.readouterr().err
    assert json.loads(json.dumps(phones.named())) == {"nexus": "emulator-5554"}
