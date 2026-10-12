"""A phone over Wi-Fi that stopped listening, and the cable that turns it on.

The bias these tests encode: A PHONE THAT WAS NAMED IS NEVER SILENTLY
GONE. A real Nexus 6P was switched off and on again: it stopped
listening over Wi-Fi, its address moved, and every list said "no phone
yet" with the phone on the desk. So an address in ``$SPARSH_CONNECT``
that doesn't answer is listed, offline, with the one thing that brings
it back; and that thing is one command, which reads the address while
the cable still answers, so the person never has to look it up.
"""

import json

import pytest

from sparsh import SparshError, cli
from sparsh.device import Attached, pick, tcpip

CABLED = "84B7N16128001616"
IP = "192.168.1.160"


class Adb:
    """`adb` as a little program: a phone on a cable, which listens over
    Wi-Fi once told to (``tcpip``), and an address that answers only then."""

    def __init__(self, tmp_path, cabled=f"{CABLED}       device usb:1-9 model:Nexus_6P",
                 wlan=f"8: wlan0    inet {IP}/24 brd 192.168.1.255 scope global wlan0"):
        self.calls = tmp_path / "calls"
        self.on = tmp_path / "listening"
        self.listed = tmp_path / "listed"
        self.listed.write_text(cabled + "\n" if cabled else "")
        self.path = tmp_path / "adb"
        self.path.write_text(f"""#!/bin/sh
echo "$@" >> {self.calls}
case "$1" in
  devices) echo "List of devices attached"; cat {self.listed};;
  connect) if [ -e {self.on} ]; then
             echo "$2       device product:angler model:Nexus_6P" >> {self.listed}
             echo "connected to $2"
           else echo "failed to connect to '$2': Connection refused"; fi;;
  -s) case "$3" in
        tcpip) touch {self.on}; echo "restarting in TCP mode port: $4";;
        shell) case "$*" in
                 *addr*) echo "{wlan}";;
                 *route*) echo "";;
               esac;;
      esac;;
esac
""")
        self.path.chmod(0o755)

    def ran(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []


def test_an_address_that_does_not_answer_is_listed_offline_with_why(tmp_path, monkeypatch):
    from sparsh.device import attached

    adb = Adb(tmp_path, cabled="")
    monkeypatch.setenv("SPARSH_CONNECT", f"{IP}:5555")
    phones = attached(str(adb.path))
    assert phones == [Attached(f"{IP}:5555", "offline")]
    assert "sparsh tcpip" in phones[0].note() and "address may have changed" in phones[0].note()
    assert "sparsh tcpip" in phones[0].line()


def test_the_cable_turns_listening_on_and_connects(tmp_path, monkeypatch):
    adb = Adb(tmp_path)
    monkeypatch.delenv("SPARSH_CONNECT", raising=False)
    done = tcpip(adb=str(adb.path), wait=0)
    assert done == {"serial": CABLED, "address": f"{IP}:5555", "connected": True,
                    "said": f"connected to {IP}:5555"}
    ran = adb.ran()
    # the address is read BEFORE the phone's adb restarts in TCP mode
    assert ran.index(f"-s {CABLED} shell ip -4 -o addr show wlan0") < \
        ran.index(f"-s {CABLED} tcpip 5555") < ran.index(f"connect {IP}:5555")


def test_another_port_is_used_when_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("SPARSH_CONNECT", raising=False)
    assert tcpip(port=5556, adb=str(Adb(tmp_path).path), wait=0)["address"] == f"{IP}:5556"


@pytest.mark.parametrize(
    "kw,said",
    [
        ({"cabled": ""}, "no phone is on a USB cable here"),
        ({"cabled": "emulator-5554  device model:sdk"}, "no phone is on a USB cable here"),
        ({"cabled": f"{CABLED}  unauthorized usb:1-9"}, "allow USB debugging"),
        ({"wlan": ""}, "no Wi-Fi address"),
    ],
)
def test_what_stops_it_is_a_sentence(tmp_path, monkeypatch, kw, said):
    monkeypatch.delenv("SPARSH_CONNECT", raising=False)
    with pytest.raises(SparshError, match=said):
        tcpip(adb=str(Adb(tmp_path, **kw).path), wait=0)


def test_the_command_prints_the_address_to_give_elsewhere(tmp_path, monkeypatch, capsys):
    adb = Adb(tmp_path)
    monkeypatch.setenv("SPARSH_ADB", str(adb.path))
    monkeypatch.delenv("SPARSH_CONNECT", raising=False)
    monkeypatch.setattr("sparsh.device.time.sleep", lambda s: None)
    assert cli.main(["tcpip"]) == 0
    out = capsys.readouterr().out
    assert f"listens over Wi-Fi at {IP}:5555" in out and "run `sparsh tcpip` again" in out
    assert f"sarathi phone {IP}:5555" in out
    (tmp_path / "calls").unlink()
    (tmp_path / "listening").unlink()
    assert cli.main(["tcpip", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["address"] == f"{IP}:5555"


def test_the_phone_on_its_cable_is_picked_over_its_silent_address(tmp_path, monkeypatch):
    adb = Adb(tmp_path)
    monkeypatch.setenv("SPARSH_CONNECT", f"{IP}:5555")
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.delenv("SPARSH_WDA", raising=False)
    assert pick(adb=str(adb.path)).serial == CABLED


def test_status_carries_the_note(tmp_path, monkeypatch):
    from sparsh.status import report

    adb = Adb(tmp_path, cabled="")
    monkeypatch.setenv("SPARSH_ADB", str(adb.path))
    monkeypatch.setenv("SPARSH_CONNECT", f"{IP}:5555")
    monkeypatch.delenv("SPARSH_WDA", raising=False)
    phones = report(tmp_path)["phones"]
    assert phones[0]["state"] == "offline" and "sparsh tcpip" in phones[0]["note"]
