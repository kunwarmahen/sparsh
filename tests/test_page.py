"""Sparsh's own page: the phones, their screens on request, their steps.

The bias these tests encode: THE PAGE WATCHES, IT NEVER TOUCHES, AND IT
SHOWS NO MORE THAN THE AGENT MAY SEE. A page that taps is a second road
around the person's holds; a peek that keeps its look changes what the
agent's numbers mean mid-task; a picture of an app the rules keep the
agent out of is the very screen the person said no one looks at. And a
phone that stopped answering is the one its person most needs to see on
the page, with why -- so a named phone is listed whether it answers or
not.
"""

import json
import os
import stat
import urllib.error
import urllib.request
from base64 import b64decode

import pytest

from sparsh import page
from sparsh.fake import PNG

TOKEN = "a-test-token-long-enough"


def report(phones=(), named=()):
    return {"version": "test", "adb": "ok", "phones": list(phones), "named": list(named),
            "rules": {"path": "/x/rules.toml", "exists": False, "never": [], "ask": ["send"]},
            "wda": None}


def answering(serial="fake", model="Pixel", name=""):
    return {"serial": serial, "state": "device", "model": model, "note": "", "name": name}


@pytest.fixture
def served(tmp_path, monkeypatch, fake):
    seen = {"report": report([answering()])}
    monkeypatch.setattr(page.status, "report", lambda state: seen["report"])
    monkeypatch.setattr(page, "pick", lambda serial: fake)
    server = page.PageServer(tmp_path, TOKEN, host="127.0.0.1", port=0).start()
    seen["url"] = f"http://127.0.0.1:{server.port}"
    yield seen
    server.close()


def get(served, path, token=TOKEN, method="GET"):
    request = urllib.request.Request(served["url"] + path, method=method,
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_every_api_call_wants_the_token(served):
    assert get(served, "/api/state", token="wrong")[0] == 401
    assert get(served, "/api/peek?serial=fake", token="")[0] == 401


def test_the_page_itself_carries_no_data_and_loads_without_a_token(served):
    with urllib.request.urlopen(served["url"] + "/", timeout=5) as r:
        body = r.read().decode()
        assert "script-src 'self'" in r.headers["Content-Security-Policy"]
    assert "page.js" in body and "#token=" not in body


def test_a_named_phone_that_stopped_answering_is_listed_with_why(served, monkeypatch):
    monkeypatch.setenv("SPARSH_SPARE", "spare-one")
    served["report"] = report(
        [answering("192.168.1.160:5555", "Nexus 6P", name="nexus"), answering("loose")],
        [{"name": "nexus", "where": "192.168.1.160:5555", "kind": "Android"},
         {"name": "spare-one", "where": "http://127.0.0.1:8100", "kind": "iPhone"}])
    code, data = get(served, "/api/state")
    assert code == 200
    shown = {p["serial"]: p for p in data["phones"]}
    assert list(shown) == ["192.168.1.160:5555", "http://127.0.0.1:8100", "loose"]
    assert shown["192.168.1.160:5555"]["name"] == "nexus"
    assert shown["192.168.1.160:5555"]["state"] == "device"
    gone = shown["http://127.0.0.1:8100"]
    assert gone["state"] == "missing" and "WebDriverAgent" in gone["note"]
    assert gone["spare"] is True and shown["loose"]["spare"] is False


def test_steps_are_read_from_the_phones_own_log_whoever_asked(served, tmp_path):
    folder = tmp_path / "phones" / "fake"
    folder.mkdir(parents=True)
    lines = [{"at": "2026-11-05T03:00:00-05:00", "by": "agent", "via": "Samay: Morning brief",
              "action": "open_app",
              "args": {"name": "Maps"}, "outcome": "done"},
             {"at": "2026-11-05T09:12:00-05:00", "by": "agent", "action": "tap",
              "args": {"n": 6}, "outcome": "held", "said": "h1: it says \"send\""}]
    (folder / "actions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    code, data = get(served, "/api/state")
    assert [s["outcome"] for s in data["phones"][0]["steps"]] == ["held", "done"]
    assert data["phones"][0]["steps"][1]["via"] == "Samay: Morning brief"
    code, data = get(served, "/api/steps?serial=fake&n=1")
    assert code == 200 and [s["action"] for s in data["steps"]] == ["tap"]


def test_a_peek_shows_the_screen_and_battery_and_keeps_no_look(served, tmp_path, fake):
    fake.battery, fake.charging = 81, True
    code, data = get(served, "/api/peek?serial=fake")
    assert code == 200
    assert data["screen"]["app"] == "com.android.settings"
    assert data["text"] and data["shot"]
    assert data["battery"] == {"level": 81, "charging": True}
    assert b64decode(data["shot"]) == PNG
    # a peek: the agent's last look, if any, is left as it was
    assert not (tmp_path / "phones" / "fake" / "last.xml").exists()
    assert not [a for a in fake.actions if a[0] in ("tap", "text", "keys", "swipe")]


def test_the_list_only_peek_takes_no_picture(served):
    code, data = get(served, "/api/peek?serial=fake&shot=0")
    assert code == 200 and data["shot"] is None and data["text"]


def test_an_app_the_rules_keep_the_agent_out_of_is_said_not_shown(served, tmp_path):
    (tmp_path / "rules.toml").write_text('never = ["com.android.settings"]\n')
    code, data = get(served, "/api/peek?serial=fake")
    assert code == 200
    assert data["shot"] is None and data["screen"]["elements"] == []
    assert "off limits" in data["screen"]["note"]


def test_a_phone_the_page_doesnt_list_is_not_one_it_peeks_at(served):
    code, data = get(served, "/api/peek?serial=emulator-5554")
    assert code == 404 and "isn't one of the phones" in data["detail"]
    assert get(served, "/api/steps?serial=")[0] == 404


def test_nothing_on_the_page_acts_on_a_phone(served):
    code, data = get(served, "/api/peek?serial=fake", method="POST")
    assert code == 405 and "only watches" in data["detail"]


def test_the_token_is_made_once_and_kept_for_you_alone(tmp_path, monkeypatch):
    monkeypatch.delenv("SPARSH_PAGE_TOKEN", raising=False)
    made = page.page_token(tmp_path)
    assert page.page_token(tmp_path) == made and len(made) >= 16
    mode = stat.S_IMODE(os.stat(tmp_path / "page.token").st_mode)
    assert mode == 0o600


def test_a_short_token_in_the_environment_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARSH_PAGE_TOKEN", "short")
    with pytest.raises(page.SparshError, match="at least 16"):
        page.page_token(tmp_path)
