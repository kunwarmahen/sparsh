"""`sparsh iphone`: the steps that bring an unplugged, restarted or updated
iPhone back, run against `ios` as a little program.

The bias these tests encode: ONE COMMAND BRINGS IT BACK. A real iPhone 17
was unplugged and updated to iOS 27.0.1; WDA then failed with "service
'com.apple.dt.testmanagerd.remote' is not available in RSD", and mounting
the new developer image failed again, because Apple's signing server
chains to a root Linux doesn't carry. So every start mounts the image,
with Apple's root handed to go-ios; and a failure that names a step says
the one thing to do, rather than go-ios's words.
"""

import ssl

import pytest

from sparsh import SparshError, wdastart
from sparsh.wdastart import Starter, _short, cert_bundle

UDID = "00008150-000C236C36C0C01C"
BUNDLE = "com.someone.sparsh.WebDriverAgentRunner.xctrunner"


class Ios:
    """go-ios: one iPhone on iOS 27, its tunnel listed or not, and a WDA
    that prints what ``wda_says`` holds and exits."""

    def __init__(self, tmp_path, tunnelled=True, wda_says="", apps=True):
        self.calls = tmp_path / "calls"
        self.tunnel = tmp_path / "tunnel-up"
        if tunnelled:
            self.tunnel.write_text("")
        self.path = tmp_path / "ios"
        listing = (f"com.openai.chat ChatGPT 1.2\n{BUNDLE} WebDriverAgentRunner-Runner 1.0"
                   if apps else "")
        self.path.write_text(f"""#!/bin/sh
echo "$@ cert=${{SSL_CERT_FILE:-}}" >> {self.calls}
case "$1" in
  list) echo '{{"deviceList":["{UDID}"]}}';;
  info) echo '{{"ProductVersion":"27.0.1"}}';;
  tunnel) case "$2" in
            ls) echo '{{"msg":"no udid specified using first device in list","udid":"{UDID}"}}'
                [ -e {self.tunnel} ] && echo '[{{"udid":"{UDID}","address":"fd00::1"}}]' \
                  || {{ echo '{{"level":"ERROR","msg":"failed to get tunnel infos"}}'; exit 1; }};;
            start) touch {self.tunnel}; sleep 30;;
          esac;;
  image) echo '{{"msg":"success mounting image"}}';;
  apps) printf '%s\\n' "{listing}";;
  forward) sleep 30;;
  runwda) echo '{wda_says}';;
esac
""")
        self.path.chmod(0o755)

    def said(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []


@pytest.fixture(autouse=True)
def nothing_answers(monkeypatch):
    # A real WDA may be answering on this computer's 8100.
    monkeypatch.setattr(wdastart, "answers", lambda *a, **k: False)
    monkeypatch.setattr(wdastart, "START_WAIT", 2.0)


def test_apple_root_is_checked_and_added_to_this_computers(tmp_path):
    made = cert_bundle(tmp_path).read_text()
    assert made.rstrip().endswith(wdastart._APPLE_ROOT.read_text().rstrip())
    assert made.count("BEGIN CERTIFICATE") > 1


def test_a_changed_root_is_refused(tmp_path, monkeypatch):
    other = tmp_path / "other.pem"
    other.write_text(ssl.DER_cert_to_PEM_cert(b"\x30\x03\x02\x01\x01"))
    monkeypatch.setattr(wdastart, "_APPLE_ROOT", other)
    with pytest.raises(SparshError, match="isn't Apple's root"):
        cert_bundle(tmp_path)


def test_the_image_is_mounted_with_apples_root_every_start(tmp_path):
    ios = Ios(tmp_path, wda_says='{"error":"could not get pid from response"}')
    with pytest.raises(SparshError, match="VPN & Device Management"):
        Starter(tmp_path / "state", ios=str(ios.path)).serve()
    mount = next(c for c in ios.said() if c.startswith("image auto"))
    assert f"--basedir={tmp_path / 'state' / 'devimages'}" in mount
    assert f"cert={tmp_path / 'state' / 'ios-roots.pem'}" in mount
    assert not any(c.startswith("tunnel start") for c in ios.said())   # one was running


def test_the_runner_is_found_on_the_phone_not_asked_for(tmp_path):
    ios = Ios(tmp_path, wda_says='{"error":"could not get pid from response"}')
    with pytest.raises(SparshError):
        Starter(tmp_path / "state", ios=str(ios.path)).serve()
    wda = next(c for c in ios.said() if c.startswith("runwda"))
    assert f"--bundleid={BUNDLE}" in wda and f"--udid={UDID}" in wda


def test_no_runner_on_the_phone_says_install_it(tmp_path):
    ios = Ios(tmp_path, apps=False)
    with pytest.raises(SparshError, match="sparsh iphone WDA.ipa"):
        Starter(tmp_path / "state", ios=str(ios.path)).serve()


def test_no_tunnel_starts_one_without_sudo(tmp_path):
    ios = Ios(tmp_path, tunnelled=False, wda_says='{"error":"could not get pid"}')
    starter = Starter(tmp_path / "state", ios=str(ios.path))
    try:
        with pytest.raises(SparshError):
            starter.serve()
    finally:
        starter.close()
    assert any(c.startswith("tunnel start --userspace") for c in ios.said())


def test_a_log_line_naming_the_phone_is_not_a_tunnel(tmp_path):
    """go-ios names the phone in a log line with no tunnel running; read
    as one, WDA was started into nothing three times (iOS 27.0.1)."""
    ios = Ios(tmp_path, tunnelled=False)
    assert not Starter(tmp_path, ios=str(ios.path)).tunnelled(UDID)
    ios.tunnel.write_text("")
    assert Starter(tmp_path, ios=str(ios.path)).tunnelled(UDID)


def test_a_tunnel_from_before_the_update_is_started_again(tmp_path):
    said = ("{\\\"error\\\":\\\"service com.apple.dt.testmanagerd.remote is not available "
            "in RSD\\\"}")
    ios = Ios(tmp_path, wda_says=said)
    starter = Starter(tmp_path / "state", ios=str(ios.path))
    try:
        with pytest.raises(SparshError, match="didn't start: .*not available in RSD"):
            starter.serve()
    finally:
        starter.close()
    assert sum(c.startswith("runwda") for c in ios.said()) == wdastart.TRIES
    assert any(c.startswith("tunnel start --userspace") for c in ios.said())


def test_a_prefix_still_names_it(tmp_path):
    assert Starter(tmp_path, prefix="com.x.sparsh", ios="ios").bundle("") == \
        "com.x.sparsh.WebDriverAgentRunner.xctrunner"


def test_go_ios_words_without_their_json():
    assert _short('{"level":"ERROR","msg":"Failed running WDA","error":"no pid"}') == "no pid"
    assert _short('{"msg":"downloading image"}') == "downloading image"
    assert _short("plain words\n") == "plain words"


def test_stop_with_nothing_behind(tmp_path, capsys):
    assert wdastart.stop(tmp_path) == 0
    assert "nothing running" in capsys.readouterr().out
