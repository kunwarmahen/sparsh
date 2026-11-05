"""Sparsh's own page: each phone, whether it answers, and what was done on it.

    GET  /                     the page (static; it carries no data)
    GET  /api/state            every phone (named or answering), why one
                               isn't ready, which are spare, the iPhone's
                               signature, the rules, and each phone's
                               newest steps
    GET  /api/steps?serial=S   one phone's steps, newest first (``n``, 1-200)
    GET  /api/peek?serial=S    one phone's screen now, as the list, with
                               its screenshot (``shot=0``: the list only)
                               and its battery

WHOEVER ASKED. Yantra's chat, Samay's runs, Prahari's watches, Dvara's
people and a voice puck all work a phone through ``sparsh mcp``, and
every step any of them takes lands in that phone's log (log.py). Yantra's
phone panel shows that Yantra's view; this page reads the log itself, so
the step a schedule took at three in the morning is on it beside the
one taken in the chat. The log says ``agent`` or ``you``, not which
program asked: they all start the same server, so it can't.

THE PAGE WATCHES, IT NEVER TOUCHES. There is no tap, no typing, no wake
here. Every act on a phone goes through an agent and the person's rules
and holds (phone.py), or through the person's own hand. A button that
taps would be a second road around them. A peek is ``look(keep=False)``:
it reads the screen without changing what the agent's numbers mean, and
it carries the person's rules, so an app they keep the agent out of is
said, not shown -- no list, no picture.

A TOKEN, ALWAYS, as every page in this family has: any web page you
visit can send a request to 127.0.0.1, so every ``/api`` call carries
``Authorization: Bearer``. It is ``$SPARSH_PAGE_TOKEN``, or one made
once and kept in the state folder (``page.token``, readable by you
alone), which Sarathi reads to open the page already signed in.

A PHONE THE PAGE DOESN'T LIST IS NOT ONE IT PEEKS AT. ``serial`` must be
one of the phones ``/api/state`` lists, so the token opens the phones
this Sparsh was given and no other one adb happens to see.

Standard library only, like the rest of Sparsh.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sparsh import SparshError, log, status
from sparsh.device import pick
from sparsh.phone import Phone, _safe
from sparsh.phones import kind
from sparsh.rules import load

PORT = 8794
TOKEN_FILE = "page.token"
#: Steps each phone carries in ``/api/state``.
STEPS = 30


def page_token(state: Path) -> str:
    """``$SPARSH_PAGE_TOKEN``, or the one kept in the state folder (made once)."""
    named = os.environ.get("SPARSH_PAGE_TOKEN", "").strip()
    if named:
        if len(named) < 16:
            raise SparshError("SPARSH_PAGE_TOKEN must be at least 16 characters")
        return named
    path = state / TOKEN_FILE
    try:
        kept = path.read_text().strip()
        if len(kept) >= 16:
            return kept
    except OSError:
        pass
    made = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        out.write(made + "\n")
    return made


def spare() -> set[str]:
    """The phones ``$SPARSH_SPARE`` names: ones a watch may open a page on
    unasked (Sarathi's ``[phone.NAME] spare``)."""
    return {n.strip() for n in os.environ.get("SPARSH_SPARE", "").split(",") if n.strip()}


def phones(report: dict) -> list[dict]:
    """The phones the page shows: every named one, answering or not, then
    any other that answers. Each is ``{serial, name, kind, state, model,
    note, spare}``; ``serial`` is how it is reached (what ``--serial``
    takes) and what its log folder is named for."""
    seen = {p["serial"]: p for p in report["phones"]}
    extra, out = spare(), []
    for n in report["named"]:
        found = seen.pop(n["where"], None)
        out.append({"serial": n["where"], "name": n["name"], "kind": n["kind"],
                    "state": found["state"] if found else "missing",
                    "model": found["model"] if found else "",
                    "note": found["note"] if found else _missing(n["kind"]),
                    "spare": n["name"] in extra})
    for p in seen.values():
        out.append({"serial": p["serial"], "name": p.get("name", ""), "kind": kind(p["serial"]),
                    "state": p["state"], "model": p["model"], "note": p["note"],
                    "spare": False})
    return out


def _missing(what: str) -> str:
    if what == "iPhone":
        return ("not answering: is WebDriverAgent running? (`sparsh iphone` starts it "
                "with the iPhone on the cable)")
    return ("not answering: is it on, and on the cable or the same Wi-Fi? "
            "(`sparsh devices` says what adb sees)")


class _Folder:
    """Enough of a Phone to read its log: where its folder is."""

    def __init__(self, state: Path, serial: str) -> None:
        self.folder = state / "phones" / _safe(serial)


def steps(state: Path, serial: str, n: int = STEPS) -> list[dict]:
    """One phone's newest steps, newest first, without asking the phone."""
    return log.recent(_Folder(state, serial), n)  # type: ignore[arg-type]


def read_state(state: Path) -> dict:
    """Everything the page draws, read fresh each time."""
    report = status.report(state)
    shown = phones(report)
    for phone in shown:
        phone["steps"] = steps(state, phone["serial"])
    return {"version": report["version"], "adb": report["adb"], "phones": shown,
            "rules": report["rules"], "wda": report["wda"]}


class PageError(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def listed(state: Path, serial: str) -> str:
    """``serial``, when it is one of the page's phones (module docstring)."""
    if serial and any(p["serial"] == serial for p in phones(status.report(state))):
        return serial
    raise PageError(404, f"{serial or 'that'} isn't one of the phones on this page")


def peek(state: Path, serial: str, shot: bool = True) -> dict[str, Any]:
    """The screen now, under the person's rules, never kept as the agent's
    last look; the screenshot as base64 PNG; and the battery."""
    rules, _ = load(state)
    try:
        phone = Phone(pick(serial), state, rules=rules)
        with tempfile.TemporaryDirectory(prefix="sparsh-peek-") as tmp:
            png = Path(tmp) / "screen.png"
            screen = phone.look(shot=png if shot else None, keep=False)
            image = base64.b64encode(png.read_bytes()).decode() if png.exists() else None
    except SparshError as e:
        raise PageError(409, str(e).splitlines()[0]) from None
    try:
        power = phone.device.battery_and_calls()
        battery = {"level": power.get("battery"), "charging": power.get("charging")}
    except SparshError:
        battery = {"level": None, "charging": None}
    return {"serial": serial, "screen": screen.to_json(), "text": screen.text(),
            "shot": image, "battery": battery}


def _static(name: str) -> bytes:
    return files("sparsh").joinpath("static", name).read_bytes()


class PageServer:
    def __init__(self, state: Path, token: str, *, host: str, port: int) -> None:
        self.state, self.token = state, token
        self.httpd = ThreadingHTTPServer((host, port), _handler(self))
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True,
                                        name="sparsh-page")

    def start(self) -> PageServer:
        self._thread.start()
        return self

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


STATIC = {"/page.js": ("page.js", "text/javascript; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
#: Who may load the page's parts: itself, and its pictures as data.
POLICY = ("default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
          "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
          "form-action 'none'; frame-ancestors 'none'")


def _handler(server: PageServer):
    class Handler(BaseHTTPRequestHandler):
        server_version = "sparsh"

        def log_message(self, *_args) -> None:
            pass

        def _send(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", POLICY)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode(), "application/json")

        def _allowed(self) -> bool:
            offered = self.headers.get("Authorization", "")
            offered = offered[7:].strip() if offered.startswith("Bearer ") else ""
            if offered and hmac.compare_digest(offered.encode(), server.token.encode()):
                return True
            self._json(401, {"detail": "missing or wrong token"})
            return False

        def do_GET(self) -> None:  # noqa: N802 -- the stdlib's name
            url = urlparse(self.path)
            asked = {k: v[-1] for k, v in parse_qs(url.query).items()}
            if url.path in ("/", "/index.html"):
                return self._send(200, _static("index.html"), "text/html; charset=utf-8")
            if url.path in STATIC:
                name, what = STATIC[url.path]
                return self._send(200, _static(name), what)
            if url.path not in ("/api/state", "/api/steps", "/api/peek"):
                return self._json(404, {"detail": "not found"})
            if not self._allowed():
                return None
            try:
                if url.path == "/api/state":
                    return self._json(200, read_state(server.state))
                serial = listed(server.state, asked.get("serial", ""))
                if url.path == "/api/steps":
                    n = max(1, min(_int(asked.get("n"), STEPS), 200))
                    return self._json(200, {"serial": serial,
                                            "steps": steps(server.state, serial, n)})
                return self._json(200, peek(server.state, serial,
                                            shot=asked.get("shot", "1") != "0"))
            except PageError as exc:
                return self._json(exc.code, {"detail": str(exc)})
            except SparshError as exc:
                return self._json(500, {"detail": str(exc).splitlines()[0]})

        def do_POST(self) -> None:  # noqa: N802
            # nothing on this page acts on a phone (module docstring)
            self._json(405, {"detail": "this page only watches: nothing here acts on a phone"})

    return Handler


def _int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw else default
    except ValueError:
        return default
