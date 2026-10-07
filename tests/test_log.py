"""The log: what was done on the phone, as the phone saw it.

The bias these tests encode: THE LOG IS THE PHONE'S ACCOUNT, NOT THE
AGENT'S. Every act is written down however it ended -- held, refused,
the screen moved -- because those are the steps a person reading it
afterwards most needs; a log of successes only would read as if
nothing was ever stopped. And it keeps no secret: what was typed into
a password field is "(hidden)" in the log as everywhere else.
"""

import json

import pytest

from sparsh import cli, log, mcp
from sparsh.phone import Phone
from sparsh.rules import Rules

from .test_rules import SEND


@pytest.fixture
def tools(fake, tmp_path):
    fake.screens["send"] = SEND
    return mcp.Tools(Rules(), state=tmp_path, device=fake, settle=0)


def steps(tools):
    return list(reversed(log.recent(tools.phone(), 50)))


def call(tools, tool, **args):
    return mcp.answer(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                              "params": {"name": tool, "arguments": args}})  # fmt: skip


def test_a_done_tap_says_what_it_was_on_and_where_it_led(tools, fake):
    call(tools, "look")
    fake.after = lambda f, a: setattr(f, "current", "network")
    call(tools, "tap", n=6)
    (step,) = steps(tools)
    assert step["by"] == "agent" and step["action"] == "tap" and step["outcome"] == "done"
    assert step["on"].startswith('6 item "Network & internet')
    assert step["app"] == "com.android.settings" and "Airplane mode" in step["after"]


def test_held_then_confirmed_are_two_steps(tools, fake):
    fake.current = "send"
    call(tools, "look")
    said = call(tools, "tap", n=2)["result"]["content"][0]["text"]
    hold = said.split('hold "')[1].split('"')[0]
    call(tools, "confirm", hold=hold)
    held, confirmed = steps(tools)
    assert held["outcome"] == "held" and held["said"].startswith(hold)
    assert confirmed["action"] == "confirm" and confirmed["outcome"] == "done"
    assert 'tap button "Send SMS"' in confirmed["on"]


def test_a_moved_screen_and_a_refusal_are_written_down_too(tools, fake):
    call(tools, "look")
    fake.current = "home"
    call(tools, "tap", n=6)
    call(tools, "open_app", name="whatsapp")
    moved, refused = steps(tools)
    assert moved["outcome"] == "changed"
    assert refused["outcome"] == "not_done" and "no app matches" in refused["said"]


def test_looking_is_not_a_step(tools):
    call(tools, "look")
    call(tools, "list_apps")
    assert steps(tools) == []


def test_a_password_is_hidden_in_the_log(tools, fake):
    fake.current = "send"
    call(tools, "look")
    said = call(tools, "type_text", text="hunter2", into=3)["result"]["content"][0]["text"]
    hold = said.split('hold "')[1].split('"')[0]
    call(tools, "confirm", hold=hold)
    raw = (tools.phone().folder / log.FILE).read_text()
    assert "hunter2" not in raw and log.HIDDEN in raw


def test_the_log_is_cut_back_not_left_to_grow(tools, monkeypatch):
    monkeypatch.setattr(log, "KEEP", 3)
    call(tools, "look")
    for _ in range(7):
        call(tools, "press_key", keys=["back"])
    lines = (tools.phone().folder / log.FILE).read_text().splitlines()
    assert 3 <= len(lines) < 6


def test_your_own_hands_are_written_as_you(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "pick", lambda serial: fake)
    monkeypatch.setattr(cli, "Phone", lambda device, state: Phone(device, state, settle=0))
    state = ["--state", str(tmp_path)]
    cli.main(["look", *state])
    cli.main(["key", "back", *state])
    capsys.readouterr()
    assert cli.main(["log", *state]) == 0
    printed = capsys.readouterr().out
    assert ' you   press_key keys=["back"]' in printed and "-> done" in printed
    cli.main(["log", "--json", *state])
    (step,) = json.loads(capsys.readouterr().out)
    assert step["by"] == "you"
