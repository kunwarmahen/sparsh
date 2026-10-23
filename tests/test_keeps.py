"""`sparsh keeps`: where your phone rules and adb's key are, for a backup.

The bias: A NEW COMPUTER THE PHONE DOESN'T TRUST. The phone trusts adb's
key and nothing else, so a backup that left it out would bring the house
back with "Allow USB debugging?" waiting on every phone. And the rules
(what is never touched) must come from the folder Sparsh reads, not a
default it would not.
"""

from __future__ import annotations

import json

from sparsh.cli import main


def _ask(capsys, *more):
    assert main(["keeps", "--json", *more]) == 0
    said = json.loads(capsys.readouterr().out)
    assert said["format"] == "sparsh.keeps.v1"
    return {p["id"]: p for p in said["keeps"]}


def test_the_state_folder_is_the_one_sparsh_reads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SPARSH_STATE", str(tmp_path / "s"))
    assert _ask(capsys)["state"]["path"] == str(tmp_path / "s")
    assert _ask(capsys, "--state", str(tmp_path / "t"))["state"]["path"] == \
        str(tmp_path / "t")


def test_adbs_key_both_halves_where_adb_keeps_them(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANDROID_USER_HOME", str(tmp_path / "android"))
    (tmp_path / "android").mkdir()
    (tmp_path / "android" / "adbkey").write_text("private")
    places = _ask(capsys)
    assert places["adbkey"]["path"] == str(tmp_path / "android" / "adbkey")
    assert places["adbkey"]["exists"] and not places["adbkey.pub"]["exists"]


def test_what_is_made_again_is_left_out_and_the_rules_are_not(capsys):
    leave_out = set(_ask(capsys)["state"]["leave_out"])
    assert {"*.log", "*.sock", "devimages"} <= leave_out
    assert not {"rules.toml", "phones", "wda.json", "iphone-apps.json"} & leave_out
