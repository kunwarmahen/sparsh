"""This computer's adb, handed to its containers through a file: ``sparsh adb-share``.

A phone on the USB cable belongs to one adb server, the one on this
computer. A container can't see the cable, so until now it reached an
Android only over Wi-Fi (``$SPARSH_CONNECT``): Wireless debugging on, an
address that moves, and a phone that stops listening after every
restart. An iPhone plugged into the same cable was already reachable
from inside, because WebDriverAgent's port is forwarded here. So
swapping an iPhone for an Android on the cable left the containers with
no phone.

A SOCKET FILE, NOT A PORT. adb's own client takes
``ADB_SERVER_SOCKET=localfilesystem:/path``, a Unix socket, as well as a
TCP port. This listens on such a file, ``adb.sock`` in Sparsh's state
folder (``~/.sparsh``, already mounted into the containers that work
the phone), and passes each connection through to the adb server here
on ``127.0.0.1:5037``. A port would do the same, but whoever reached it
could work the phone, and from a container the host is reached at its
house address, so the port would be open to the house too. A file
belongs to its owner, mode 0600, and nobody on the network sees it.

The server here stays the one every program on this computer already
uses, so ``adb devices`` and Sparsh on this computer keep working as
they did. When nothing is listening on 5037, ``adb start-server`` is
run once and the connection tried again. adb would start its own server
the same way.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from pathlib import Path

from sparsh import SparshError

#: adb's own default, and its environment variable for another.
ADB_PORT = 5037


def socket_path(state: str | Path | None = None) -> Path:
    base = state or os.environ.get("SPARSH_STATE") or Path.home() / ".sparsh"
    return Path(base).expanduser() / "adb.sock"


def adb_port() -> int:
    raw = os.environ.get("ANDROID_ADB_SERVER_PORT", "")
    return int(raw) if raw.isdigit() else ADB_PORT


def _reach_adb(adb: str | None, port: int) -> socket.socket:
    for attempt in (1, 2):
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=10)
        except OSError:
            if attempt == 2 or not adb:
                raise
            subprocess.run([adb, "start-server"], capture_output=True, timeout=30)
    raise AssertionError("unreachable")


def _pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while chunk := src.recv(65536):
            dst.sendall(chunk)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _serve_one(client: socket.socket, adb: str | None, port: int) -> None:
    try:
        upstream = _reach_adb(adb, port)
    except OSError:
        client.close()
        return
    upstream.settimeout(None)
    back = threading.Thread(target=_pipe, args=(upstream, client), daemon=True)
    back.start()
    _pipe(client, upstream)
    back.join()
    client.close()
    upstream.close()


def listen(path: Path) -> socket.socket:
    """The socket file, made fresh (one left by an earlier run is
    removed: it is ours, and nothing listens on it any more)."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_socket():
        path.unlink()
    elif path.exists():
        raise SparshError(f"{path} is there and isn't a socket; move it out of the way")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(old)
    os.chmod(path, 0o600)
    server.listen(16)
    return server


def serve(path: Path, adb: str | None, port: int | None = None,
          ready: threading.Event | None = None) -> None:  # fmt: skip
    """Pass every connection on ``path`` through to adb, until stopped."""
    port = port or adb_port()
    server = listen(path)
    if ready is not None:
        ready.set()
    try:
        while True:
            client, _ = server.accept()
            threading.Thread(target=_serve_one, args=(client, adb, port), daemon=True).start()
    finally:
        server.close()
        try:
            path.unlink()
        except OSError:
            pass
