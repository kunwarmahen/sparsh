"""devtools: a page's own words from Chrome on the phone, through adb.

The bias these tests encode: THE WORDS COME FROM THE TAB THAT WAS
OPENED, WHEN IT HAS FINISHED, AND NOTHING IS DONE TO THE PAGE. The tab
list is read to its Content-Length (Chrome keeps the connection open);
the tab is the one showing the address; its text is taken once it has
loaded and stopped growing, never mid-load if it can be helped; and the
one question asked of it is a read. Every failure is a SparshError, so
open_url falls back to the screen list.
"""

from __future__ import annotations

import json
import struct

import pytest

from sparsh import SparshError, devtools

URL = "https://shop.example/p/1"


class FakeStream:
    """One adb stream to Chrome's socket: answers what it is sent."""

    def __init__(self, answer) -> None:
        self.answer = answer          # callable(sent bytes) -> bytes to hand back
        self.sent = b""
        self.out = b""

    def sendall(self, data: bytes) -> None:
        self.sent += data
        self.out += self.answer(data)

    def recv(self, n: int) -> bytes:
        got, self.out = self.out[:n], self.out[n:]
        return got

    def close(self) -> None:
        pass


def http(body: str) -> bytes:
    return (f"HTTP/1.1 200 OK\r\nContent-Length:{len(body.encode())}\r\n"
            f"Content-Type:application/json\r\n\r\n{body}").encode()


def frame(text: str) -> bytes:
    data = text.encode()
    n = len(data)
    head = bytes([0x81, n]) if n < 126 else bytes([0x81, 126]) + struct.pack(">H", n)
    return head + data


TABS = [{"type": "page", "id": "7", "url": "https://other.example/",
         "webSocketDebuggerUrl": "ws://localhost/devtools/page/7"},
        {"type": "page", "id": "9", "url": URL + "#reviews",
         "webSocketDebuggerUrl": "ws://localhost/devtools/page/9"}]


def chrome(monkeypatch, pages):
    """Chrome whose tab 9 answers each question with the next of ``pages``
    ((readyState, text) pairs); records every expression asked."""
    asked: list[tuple[str, str]] = []
    pages = iter(pages)

    def stream(serial):
        def answer(data: bytes) -> bytes:
            if data.startswith(b"GET /json"):
                return http(json.dumps(TABS))
            if data.startswith(b"GET /devtools/page/"):
                path = data.split(b" ")[1].decode()
                asked.append(("open", path))
                return b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
            # a masked client frame: the question
            n = data[1] & 0x7F
            start = 2 + (2 if n == 126 else 0)
            mask, body = data[start:start + 4], data[start + 4:]
            question = json.loads(bytes(b ^ mask[i % 4] for i, b in enumerate(body)))
            asked.append(("ask", question["params"]["expression"]))
            state, text = next(pages)
            return frame(json.dumps({"id": question["id"],
                                     "result": {"result": {"value": [state, text]}}}))
        return FakeStream(answer)
    monkeypatch.setattr(devtools, "open_stream", stream)
    return asked


def test_the_words_of_the_tab_showing_the_address(monkeypatch):
    asked = chrome(monkeypatch, [("complete", "Sale Price\n$5.49"),
                                 ("complete", "Sale Price\n$5.49")])
    text = devtools.page_text("phone", URL, wait=5, settle=0)
    assert text == "Sale Price\n$5.49"
    assert ("open", "/devtools/page/9") in asked      # not the other tab


def test_a_page_still_loading_or_growing_is_waited_for(monkeypatch):
    chrome(monkeypatch, [("loading", "Food Lion"), ("complete", "Food Lion"),
                         ("complete", "Food Lion\nSale Price\n$5.49"),
                         ("complete", "Food Lion\nSale Price\n$5.49")])
    assert "$5.49" in devtools.page_text("phone", URL, wait=5, settle=0)


def test_the_one_question_only_reads(monkeypatch):
    asked = chrome(monkeypatch, [("complete", "x"), ("complete", "x")])
    devtools.page_text("phone", URL, wait=5, settle=0)
    questions = {q for kind, q in asked if kind == "ask"}
    assert questions == {"[document.readyState, document.body ? document.body.innerText : '']"}


def test_no_tab_with_the_address_is_an_error_open_url_survives(monkeypatch):
    chrome(monkeypatch, [])
    with pytest.raises(SparshError, match="never showed"):
        devtools.page_text("phone", "https://nowhere.example/", wait=0, settle=0)


def test_adb_saying_no_is_said(monkeypatch):
    class Refusing(FakeStream):
        pass

    sock = Refusing(lambda data: b"FAIL" + b"0010" + b"device offline!!")
    monkeypatch.setattr(devtools, "_adb_server", lambda: sock)
    with pytest.raises(SparshError, match="device offline"):
        devtools.open_stream("phone")
