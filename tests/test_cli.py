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


def test_a_peek_leaves_the_agents_numbers_alone(run, fake):
    # The person's page looks while an agent works: the agent's 6 must
    # still be the 6 it read.
    run("look")
    fake.current = "home"
    code, out, _ = run("look", "--peek")
    assert code == 0 and "nexuslauncher" in out
    fake.current = "settings"
    code, _, _ = run("tap", "6")
    assert code == 0 and fake.actions == [("tap", 540, 820)]


# -- over Wi-Fi ----------------------------------------------------------------


class FakeAdb:
    """`adb` as a little program: devices lists what `connect` added."""

    def __init__(self, tmp_path):
        self.listed = tmp_path / "listed"
        self.listed.write_text("")
        self.calls = tmp_path / "calls"
        self.path = tmp_path / "adb"
        self.path.write_text(f"""#!/bin/sh
echo "$@" >> {self.calls}
case "$1" in
  devices) echo "List of devices attached"; cat {self.listed};;
  connect) echo "$2       device product:p model:Pixel_7 device:d" >> {self.listed}
           echo "connected to $2";;
  pair) echo "Successfully paired to $2 [guid=adb-1]";;
esac
""")
        self.path.chmod(0o755)

    def ran(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []


def test_a_phone_named_for_wifi_is_connected_to_before_listing(tmp_path, monkeypatch):
    from sparsh.device import attached

    adb = FakeAdb(tmp_path)
    monkeypatch.setenv("SPARSH_CONNECT", "192.168.1.23:41234")
    phones = attached(str(adb.path))
    assert [(p.serial, p.model) for p in phones] == [("192.168.1.23:41234", "Pixel_7")]
    assert adb.ran() == ["devices -l", "connect 192.168.1.23:41234", "devices -l"]
    attached(str(adb.path))  # already listed: not connected again
    assert adb.ran()[-1] == "devices -l" and adb.ran().count("connect 192.168.1.23:41234") == 1


def test_without_it_nothing_is_connected_to(tmp_path, monkeypatch):
    from sparsh.device import attached

    adb = FakeAdb(tmp_path)
    monkeypatch.delenv("SPARSH_CONNECT", raising=False)
    assert attached(str(adb.path)) == [] and adb.ran() == ["devices -l"]


def test_pair_and_connect_say_what_adb_said(tmp_path, monkeypatch, capsys):
    adb = FakeAdb(tmp_path)
    monkeypatch.setenv("SPARSH_ADB", str(adb.path))
    assert cli.main(["pair", "192.168.1.23:37000", "123456"]) == 0
    assert "Successfully paired" in capsys.readouterr().out
    assert cli.main(["connect", "192.168.1.23:41234"]) == 0
    assert "connected to 192.168.1.23:41234" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv,said",
    [
        (["pair", "192.168.1.23:37000", "12"], "six digits"),
        (["connect", "not an address"], "not an address and port"),
    ],
)
def test_wifi_mistakes_are_sentences(tmp_path, monkeypatch, capsys, argv, said):
    monkeypatch.setenv("SPARSH_ADB", str(FakeAdb(tmp_path).path))
    assert cli.main(argv) == 1 and said in capsys.readouterr().err
