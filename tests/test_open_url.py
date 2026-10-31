"""open_url: an address in the phone's own browser, read as a screen.

The bias these tests encode: A PAGE OPENED ON THE PHONE IS STILL A
SCREEN UNDER THE PERSON'S RULES, AND NEVER A GUESS. The address goes to
the phone whole (an & in it must not end the command on the phone's
shell); a page still filling in is read again rather than handed back
blank; a browser the person keeps the agent out of is left for home
before anything on it is read; and only a web address opens. The tool
says it is the kind a harness asks about every time ("ask").
"""

from __future__ import annotations

import pytest

from sparsh import SparshError, mcp
from sparsh.device import AdbDevice
from sparsh.phone import Phone
from sparsh.rules import Rules

from .conftest import BLANK_PAGE, CHROME, FILLED_PAGE

URL = "https://shop.example/p/1?fulfillment=PICKUP&searchType=default"


def opened_on(fake, page="filled"):
    """After open_url, the browser shows ``page``."""
    fake.screens.update(blank=BLANK_PAGE, filled=FILLED_PAGE)

    def after(f, action):
        if action[0] == "open_url":
            f.current = page
    fake.after = after


def test_the_address_opens_and_the_page_comes_back_as_a_screen(fake, tmp_path):
    opened_on(fake)
    seen = Phone(fake, state=tmp_path, settle=0).open_url(URL)
    assert ("open_url", URL) in fake.actions
    assert any(e.label == "Haveli Indian Cuisine" for e in seen.elements)
    assert "phone's own browser" in seen.text()


def test_a_page_still_filling_in_is_read_again(fake, tmp_path):
    opened_on(fake, page="blank")
    reads = []

    def dump(retry=True, _dump=fake.dump):
        reads.append(1)
        if len(reads) >= 3:
            fake.current = "filled"
        return _dump(retry)
    fake.dump = dump
    seen = Phone(fake, state=tmp_path, settle=0.001).open_url(URL)
    assert any(e.label == "Haveli Indian Cuisine" for e in seen.elements)


def test_only_a_web_address_opens(fake, tmp_path):
    with pytest.raises(SparshError, match="only a web address"):
        Phone(fake, state=tmp_path, settle=0).open_url("intent://call/911")
    assert not any(a[0] == "open_url" for a in fake.actions)


def test_a_browser_the_rules_keep_out_is_left_for_home(fake, tmp_path):
    opened_on(fake)
    phone = Phone(fake, state=tmp_path, settle=0, rules=Rules(never=(CHROME,)))
    with pytest.raises(SparshError, match="off limits"):
        phone.open_url(URL)
    assert ("keys", "home") in [a[:2] for a in fake.actions]


def test_the_whole_address_reaches_the_phones_shell(monkeypatch):
    sent = []
    device = AdbDevice("serial", adb="adb")
    monkeypatch.setattr(device, "_shell", lambda *a, **k: sent.append(a) or "Starting")
    device.open_url(URL)
    assert sent[0][-1] == f"'{URL}'"            # quoted: & would end the command


def test_the_tool_is_the_kind_that_is_asked_about():
    assert mcp.KINDS["open_url"] == "ask"
    tool = next(t for t in mcp.TOOLS if t["name"] == "open_url")
    assert tool["annotations"]["readOnlyHint"] is False


def test_the_tool_needs_an_address(fake, tmp_path):
    tools = mcp.Tools(Rules(), state=tmp_path, device=fake, settle=0)
    reply = mcp.answer(tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": "open_url", "arguments": {}}})
    assert reply["result"]["isError"] and "missing: url" in reply["result"]["content"][0]["text"]
