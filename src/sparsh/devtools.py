"""A page's own words, from Chrome on the phone, through adb.

The screen list is what a page lets the phone's accessibility read, and
Chrome on a real Nexus 6P let it read a page only for a few seconds: the
header at three, "Web View" again by eight, the price -- which arrived in
between -- mostly never. A watch with no model can't look at a picture,
so it needs the words some other way.

Chrome on Android shares its tabs over adb, the way ``chrome://inspect``
reads them: a socket on the phone, ``@chrome_devtools_remote``. adb can
open a socket on the phone ITSELF (``localabstract:``), so this goes
straight through the adb server Sparsh already uses -- a container's
borrowed one included (``$ADB_SERVER_SOCKET``) -- with no port forward,
which would open on whichever computer runs that server and be out of a
container's reach.

ONLY READS. One question is asked of the tab: ``document.body.innerText``
(and whether it has finished loading). Nothing is clicked, typed or run
on the page beyond that.

STDLIB ONLY, like the rest of Sparsh: adb's own wire (four hex digits of
length, then the request; ``OKAY`` or ``FAIL``), plain HTTP for the tab
list, and the least of a WebSocket for the one question.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time

from sparsh import SparshError

#: Chrome's tab-sharing socket on the phone.
CHROME_SOCKET = "localabstract:chrome_devtools_remote"
#: How long one step of the conversation may take.
TIMEOUT = 15.0


def _adb_server() -> socket.socket:
    """A connection to the adb server: ``$ADB_SERVER_SOCKET`` when set
    (``localfilesystem:/path`` or ``tcp:host:port``), else 127.0.0.1:5037."""
    where = os.environ.get("ADB_SERVER_SOCKET", "").strip()
    try:
        if where.startswith("localfilesystem:"):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(TIMEOUT)
            sock.connect(where.removeprefix("localfilesystem:"))
            return sock
        host, port = "127.0.0.1", 5037
        if where.startswith("tcp:"):
            parts = where.removeprefix("tcp:").rsplit(":", 1)
            if len(parts) == 2:
                host, port = parts[0] or host, int(parts[1])
            else:
                port = int(parts[0])
        return socket.create_connection((host, port), timeout=TIMEOUT)
    except OSError as e:
        raise SparshError(f"could not reach the adb server ({e})") from None


def _ask(sock: socket.socket, request: str) -> None:
    data = request.encode()
    sock.sendall(f"{len(data):04x}".encode() + data)
    status = _exactly(sock, 4)
    if status != b"OKAY":
        size = int(_exactly(sock, 4), 16) if status == b"FAIL" else 0
        why = _exactly(sock, size).decode(errors="replace") if size else status.decode()
        raise SparshError(f"adb refused {request.split(':')[0]}: {why}")


def _exactly(sock: socket.socket, n: int) -> bytes:
    out = b""
    while len(out) < n:
        got = sock.recv(n - len(out))
        if not got:
            raise SparshError("the phone closed the connection")
        out += got
    return out


def open_stream(serial: str) -> socket.socket:
    """A raw stream to Chrome's socket on the phone ``serial``."""
    sock = _adb_server()
    try:
        _ask(sock, f"host:transport:{serial}")
        _ask(sock, CHROME_SOCKET)
    except SparshError:
        sock.close()
        raise
    return sock


def tabs(serial: str) -> list[dict]:
    """Chrome's open tabs, as its ``/json`` lists them."""
    sock = open_stream(serial)
    try:
        sock.sendall(b"GET /json HTTP/1.1\r\nHost: localhost\r\n\r\n")
        # Chrome keeps the connection open, so the answer ends at its length
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += _exactly(sock, 1)
        head, body = raw.split(b"\r\n\r\n", 1)
        length = next((int(line.split(b":", 1)[1]) for line in head.split(b"\r\n")
                       if line.lower().startswith(b"content-length:")), 0)
        body += _exactly(sock, length - len(body)) if length > len(body) else b""
    except OSError as e:
        raise SparshError(f"Chrome on the phone didn't answer ({e})") from None
    finally:
        sock.close()
    try:
        return json.loads(body.decode(errors="replace"))
    except ValueError:
        raise SparshError("Chrome on the phone answered something that isn't its "
                          "tab list") from None


class _Socket:
    """The least of a WebSocket client: one text frame out, text frames in."""

    def __init__(self, serial: str, path: str) -> None:
        self.sock = open_stream(serial)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                           "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += _exactly(self.sock, 1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            self.sock.close()
            raise SparshError("Chrome on the phone wouldn't share that tab")

    def send(self, text: str) -> None:
        data = text.encode()
        mask = os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                                bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                                bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> str:
        parts = b""
        while True:
            b0, b1 = _exactly(self.sock, 2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", _exactly(self.sock, 2))[0]
            elif n == 127:
                n = struct.unpack(">Q", _exactly(self.sock, 8))[0]
            payload = _exactly(self.sock, n)
            if b0 & 0x0F == 0x8:
                raise SparshError("Chrome on the phone closed the tab's connection")
            if b0 & 0x0F in (0x1, 0x0):
                parts += payload
                if b0 & 0x80:
                    return parts.decode(errors="replace")

    def close(self) -> None:
        self.sock.close()


def evaluate(serial: str, tab: dict, expression: str) -> object:
    """``expression``'s value in ``tab`` (a read: see the module docstring)."""
    path = tab.get("webSocketDebuggerUrl", "").split("localhost", 1)[-1] or \
        f"/devtools/page/{tab.get('id', '')}"
    ws = _Socket(serial, path)
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expression, "returnByValue": True}}))
        while True:
            reply = json.loads(ws.recv())
            if reply.get("id") == 1:
                return reply.get("result", {}).get("result", {}).get("value")
    finally:
        ws.close()


def page_text(serial: str, url: str, wait: float = 20.0, settle: float = 1.0) -> str:
    """The words of the tab showing ``url``, once it has loaded and its
    text has stopped growing, or as far as it got in ``wait`` seconds."""
    want = url.split("#", 1)[0]
    deadline = time.monotonic() + wait
    last, text = -1, ""
    while True:
        tab = next((t for t in tabs(serial) if t.get("type") == "page"
                    and str(t.get("url", "")).split("#", 1)[0] == want), None)
        if tab is not None:
            got = evaluate(serial, tab, "[document.readyState, document.body ? "
                                        "document.body.innerText : '']")
            if isinstance(got, list) and len(got) == 2:
                state, text = str(got[0]), str(got[1])
                if state == "complete" and len(text) == last and text.strip():
                    return text
                # only reads after loading count toward "stopped growing"
                last = len(text) if state == "complete" else -1
        if time.monotonic() > deadline:
            if text.strip():
                return text
            raise SparshError("Chrome on the phone never showed that page's words")
        time.sleep(settle)
