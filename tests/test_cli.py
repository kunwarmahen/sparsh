"""The command line: what a person types, and what a script reads.

The bias these tests encode: A MOVED SCREEN IS LOUD AND HARMLESS --
exit 3, the new screen on stderr, nothing done -- and every other
failure is one sentence and exit 1, never a traceback.
"""

import json

import pytest

from sparsh import cli
from sparsh.device import Attached
from sparsh.phone import Phone


@pytest.fixture
def run(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "pick", lambda serial: fake)
    monkeypatch.setattr(cli, "Phone", lambda device, state: Phone(device, state, settle=0))

    def go(*argv):
        code = cli.main([*argv[:1], "--state", str(tmp_path), *argv[1:]])
        out = capsys.readouterr()
        return code, out.out, out.err

    return go


def test_look_then_tap(run, fake):
    code, out, _ = run("look")
    assert code == 0 and '6 item "Network & internet' in out
    code, out, _ = run("tap", "6")
    assert code == 0 and fake.actions == [("tap", 540, 820)]


def test_a_moved_screen_is_exit_3_and_prints_the_new_one(run, fake):
    run("look")
    fake.current = "home"
    code, out, err = run("tap", "6")
    assert code == cli.CHANGED and out == ""
    assert "Nothing was done" in err and "nexuslauncher" in err
    assert fake.actions == []


def test_look_as_json(run):
    code, out, _ = run("look", "--json")
    data = json.loads(out)
    assert data["app"] == "com.android.settings"
    assert data["elements"][5]["label"].startswith("Network")
    assert data["elements"][5]["bounds"] == [0, 705, 1080, 936]


def test_a_screenshot_is_saved(run, tmp_path):
    shot = tmp_path / "s.png"
    code, _, err = run("look", "--shot", str(shot))
    assert code == 0 and shot.read_bytes().startswith(b"\x89PNG")
    assert "screenshot saved" in err


def test_errors_are_sentences_and_exit_1(run):
    code, out, err = run("type", "café")
    assert code == 1 and err.startswith("sparsh: can't type")


def test_devices_explains_a_phone_waiting_for_permission(monkeypatch, capsys):
    monkeypatch.setattr(cli, "attached", lambda: [Attached("R58M", "unauthorized", "")])
    assert cli.main(["devices"]) == 0
    assert "allow USB debugging" in capsys.readouterr().out
