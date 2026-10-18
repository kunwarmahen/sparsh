"""An iPhone swapped for an Android on the same cable, and the containers
that work whichever one is there.

The bias these tests encode: THE PHONE THAT ANSWERS, NOT THE ONE WRITTEN
DOWN. A person put their iPhone away and plugged in an Android. Sarathi
still had the iPhone's WebDriverAgent address saved, Sparsh took that
as the phone because it was set, and every list said "iPhone, not
answering" with the Android on the cable. So an iPhone address is a
place to ask, not an answer. Two phones that answer are said, not
guessed. And a container reaches the cable through a socket file that
only its owner can open, not a port the house could reach.
"""

import os
import socket
import stat
import threading

import pytest

from sparsh import SparshError, adbshare, device
from sparsh.device import AdbDevice, Attached, pick
from sparsh.iphone import WdaDevice

IPHONE = "http://127.0.0.1:8100"
ANDROID = "84B7N16128001616"


@pytest.fixture
def phones(monkeypatch):
    """Which phones answer: set ``.android`` (adb's list) and ``.iphone``."""

    class Desk:
        android: list[Attached] = []
        iphone = False

    desk = Desk()
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    monkeypatch.setenv("SPARSH_WDA", IPHONE)
    monkeypatch.setattr(device, "attached", lambda adb=None: desk.android)
    monkeypatch.setattr(device, "adb_path", lambda: "adb")
    monkeypatch.setattr(device, "_answers", lambda url: desk.iphone)
    return desk


def test_an_android_in_the_iphones_place_is_the_phone(phones):
    phones.android = [Attached(ANDROID, "device", "Nexus_6P")]
    chosen = pick()
    assert isinstance(chosen, AdbDevice) and chosen.serial == ANDROID


def test_the_iphone_is_the_phone_when_it_answers_and_no_android_does(phones):
    phones.iphone = True
    phones.android = [Attached(ANDROID, "unauthorized")]
    assert isinstance(pick(), WdaDevice)


def test_two_phones_that_answer_are_said_not_guessed(phones):
    phones.iphone = True
    phones.android = [Attached(ANDROID, "device", "Nexus_6P")]
    with pytest.raises(SparshError, match="more than one phone answers") as e:
        pick()
    assert ANDROID in str(e.value) and IPHONE in str(e.value)


def test_nothing_answering_hands_back_the_iphone_so_its_call_says_why(phones):
    chosen = pick()
    assert isinstance(chosen, WdaDevice) and chosen.serial == IPHONE


def test_no_adb_here_still_finds_the_iphone(phones, monkeypatch):
    def no_adb():
        raise SparshError("adb is not installed")

    monkeypatch.setattr(device, "adb_path", no_adb)
    phones.iphone = True
    assert isinstance(pick(), WdaDevice)


def test_a_named_android_is_used_even_with_an_iphone_answering(phones):
    phones.iphone = True
    phones.android = [Attached(ANDROID, "device")]
    assert pick(ANDROID).serial == ANDROID


# -- the socket file ------------------------------------------------------


@pytest.fixture
def short_tmp():
    """A Unix socket's path has to be short (about 100 bytes); pytest's
    own folders can be longer than that."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="/tmp") as d:
        yield d


def _echo_server():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(4)

    def run():
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            with c:
                while data := c.recv(1024):
                    c.sendall(b"adb:" + data)

    threading.Thread(target=run, daemon=True).start()
    return srv


def _share(path, port, adb=None):
    ready = threading.Event()
    threading.Thread(target=adbshare.serve, args=(path, adb, port, ready), daemon=True).start()
    assert ready.wait(5)


def test_a_connection_on_the_file_reaches_adb_and_back(short_tmp):
    srv = _echo_server()
    path = adbshare.socket_path(short_tmp)
    _share(path, srv.getsockname()[1])
    with socket.socket(socket.AF_UNIX) as c:
        c.connect(str(path))
        c.sendall(b"000chost:devices")
        assert c.recv(1024) == b"adb:000chost:devices"
    srv.close()


def test_only_its_owner_can_open_the_file(short_tmp):
    srv = _echo_server()
    path = adbshare.socket_path(short_tmp)
    _share(path, srv.getsockname()[1])
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    srv.close()


def test_a_file_left_by_an_earlier_run_is_replaced(short_tmp):
    path = adbshare.socket_path(short_tmp)
    old = socket.socket(socket.AF_UNIX)
    old.bind(str(path))
    old.close()  # the file stays; nothing listens on it
    srv = _echo_server()
    _share(path, srv.getsockname()[1])
    with socket.socket(socket.AF_UNIX) as c:
        c.connect(str(path))
        c.sendall(b"x")
        assert c.recv(16) == b"adb:x"
    srv.close()


def test_something_else_at_that_path_is_not_removed(short_tmp):
    path = adbshare.socket_path(short_tmp)
    path.write_text("mine")
    with pytest.raises(SparshError, match="isn't a socket"):
        adbshare.listen(path)
    assert path.read_text() == "mine"


def test_adb_is_started_when_nothing_listens_yet(short_tmp):
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    calls = os.path.join(short_tmp, "calls")
    adb = os.path.join(short_tmp, "adb")
    with open(adb, "w") as f:
        f.write(f'#!/bin/sh\necho "$@" >> {calls}\n')
    os.chmod(adb, 0o755)
    path = adbshare.socket_path(short_tmp)
    _share(path, port, adb)
    with socket.socket(socket.AF_UNIX) as c:
        c.connect(str(path))
        c.settimeout(5)
        assert c.recv(16) == b""  # still nothing there: closed, not hung
    with open(calls) as f:
        assert f.read().strip() == "start-server"
