"""`sparsh iphone`: the iPhone on this computer's cable, ready for Sparsh.

    sparsh iphone [WDA.ipa]       start it and stay running (Ctrl-C stops it)
    sparsh iphone --background    the same, behind; returns once it answers
    sparsh iphone --stop          stop the one running behind

ONE COMMAND, EVERY TIME. WebDriverAgent (WDA) is the app on the iPhone
Sparsh talks to. Unplugging the phone, restarting it, or updating iOS
stops it, and starting it again took several steps that each failed in
its own words. This does all of them, in order, with go-ios (`ios`):

    tunnel   iOS 17 and later reach developer tools through a tunnel.
             One already running (the old script's, under sudo) is used;
             otherwise one is started in "userspace", which needs no sudo,
             so the home page's button can start it too.
    image    each iOS version needs its own developer disk image mounted;
             after an update there is none, and WDA fails with "service
             'com.apple.dt.testmanagerd.remote' is not available in RSD".
             ``ios image auto`` fetches and mounts it, every start (once
             mounted it costs nothing). Apple signs the image from
             gs.apple.com, whose certificate chains to Apple's own root,
             which Linux doesn't carry: Sparsh ships that root
             (apple-root-ca.pem, checked against its published SHA-256
             before use) and hands it to go-ios for this step only.
    install  only when given WDA.ipa (just built: build-wda-on-mac.sh).
    apps     what's installed, for "open WhatsApp" (iphone.py); read again
             every few minutes while this runs.
    forward  port 8100 here reaches WDA on the phone: SPARSH_WDA.
    runwda   WDA itself. Its name comes from the phone (the one app named
             ``*.WebDriverAgentRunner.xctrunner``), so no PREFIX is needed.

IT WAITS FOR THE PHONE. When WDA stops because the phone went away, this
waits for it to come back and starts it all again: plug it back in and
unlock it, nothing else. A WDA that won't start at all (a developer the
phone doesn't trust yet, a signature that ran out) is said and ends it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from sparsh import SparshError
from sparsh.iphone import remember_apps, remember_signature, signature, signature_note

PORT = 8100
URL = f"http://127.0.0.1:{PORT}"

#: Apple Root CA, as https://www.apple.com/certificateauthority/ publishes it.
APPLE_ROOT_SHA256 = "b0b1730ecbc7ff4505142c49f1295e6eda6bcaed7e2c68c5be91b5a11001f024"
_APPLE_ROOT = Path(__file__).with_name("apple-root-ca.pem")
_SYSTEM_ROOTS = ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt",
                 "/etc/ssl/cert.pem")

#: How long WDA may take to answer once started, and how often the apps are read.
START_WAIT = 90.0
APPS_EVERY = float(os.environ.get("SPARSH_APPS_EVERY") or 300)
#: Starts in a row that never answered before giving up.
TRIES = 3

_UNTRUSTED = "could not get pid"
_NO_SERVICE = "is not available in RSD"


def ios_program() -> str:
    found = shutil.which("ios") or str(Path.home() / ".local/bin/ios")
    if not os.access(found, os.X_OK):
        raise SparshError("go-ios isn't installed: npm install -g --prefix ~/.local go-ios "
                          "(SETUP.md, C6)")
    return found


def answers(url: str = URL, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/status", timeout=timeout) as reply:
            return reply.status == 200
    except (OSError, ValueError):
        return False


def cert_bundle(state: Path) -> Path:
    """This computer's roots with Apple's added, for ``ios image auto``."""
    pem = _APPLE_ROOT.read_text()
    if hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest() != APPLE_ROOT_SHA256:
        raise SparshError(f"{_APPLE_ROOT} isn't Apple's root certificate")
    system = ssl.get_default_verify_paths().cafile
    roots = next((p for p in (system, *_SYSTEM_ROOTS) if p and Path(p).is_file()), None)
    out = state / "ios-roots.pem"
    state.mkdir(parents=True, exist_ok=True)
    out.write_text((Path(roots).read_text() if roots else "") + "\n" + pem)
    return out


def _say(*words: object) -> None:
    print(*words, flush=True)


class Starter:
    def __init__(self, state: Path, ipa: str | None = None, prefix: str | None = None,
                 ios: str | None = None) -> None:
        self.state = state
        self.ipa = ipa
        self.prefix = prefix or os.environ.get("PREFIX") or None
        self.ios = ios or ios_program()
        self.children: list[subprocess.Popen] = []
        self.tunnel: subprocess.Popen | None = None
        self.forward: subprocess.Popen | None = None

    # -- go-ios ----------------------------------------------------------------

    def run(self, *argv: str, timeout: float = 120, env: dict | None = None) -> str:
        try:
            done = subprocess.run([self.ios, *argv], capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return ""
        return done.stdout + done.stderr

    def _spawn(self, log: str, *argv: str) -> subprocess.Popen:
        with open(self.state / log, "w") as out:
            proc = subprocess.Popen([self.ios, *argv], stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL)
        self.children.append(proc)
        return proc

    def phone(self) -> str | None:
        for line in self.run("list", timeout=20).splitlines():
            try:
                found = json.loads(line).get("deviceList")
            except (ValueError, AttributeError):
                continue
            if found:
                return found[0]
        return None

    def major(self, udid: str) -> int:
        for line in self.run("info", f"--udid={udid}", timeout=20).splitlines():
            try:
                version = json.loads(line).get("ProductVersion")
            except (ValueError, AttributeError):
                continue
            if version:
                return int(version.split(".")[0])
        return 0

    def tunnelled(self, udid: str) -> bool:
        return f'"{udid}"' in self.run("tunnel", "ls", timeout=10)

    # -- the steps -------------------------------------------------------------

    def ready_tunnel(self, udid: str, fresh: bool = False) -> None:
        if self.major(udid) < 17:
            return
        if fresh and self.tunnel is not None:
            self._stop(self.tunnel)
            self.tunnel = None
        if not fresh and self.tunnelled(udid):
            return
        if self.tunnel is None or self.tunnel.poll() is not None:
            _say("starting the developer tunnel (iOS 17 and later)")
            self.tunnel = self._spawn("ios-tunnel.log", "tunnel", "start", "--userspace")
        for _ in range(30):
            if self.tunnelled(udid):
                return
            time.sleep(1)
        raise SparshError("the developer tunnel didn't come up; its words are in "
                          f"{self.state / 'ios-tunnel.log'} (a tunnel started with sudo "
                          "earlier may hold its port: sudo pkill -f 'ios tunnel start')")

    def mount(self, udid: str) -> None:
        env = {**os.environ, "SSL_CERT_FILE": str(cert_bundle(self.state))}
        said = self.run("image", "auto", f"--basedir={self.state / 'devimages'}",
                        f"--udid={udid}", env=env, timeout=600)
        if "success mounting" in said or "already mounted" in said.lower():
            return
        last = [ln for ln in said.splitlines() if ln.strip()][-1:] or ["(nothing)"]
        _say(f"the developer image wasn't mounted ({_short(last[0])}); trying anyway")

    def apps(self, udid: str) -> str:
        listing = self.run("apps", "--list", f"--udid={udid}", timeout=60)
        try:
            remember_apps(self.state, listing)
        except ValueError:
            pass
        return listing

    def bundle(self, listing: str) -> str:
        if self.prefix:
            return f"{self.prefix}.WebDriverAgentRunner.xctrunner"
        for line in listing.splitlines():
            name = line.split()[0] if line.split() else ""
            if name.endswith(".WebDriverAgentRunner.xctrunner"):
                return name
        raise SparshError("WebDriverAgent isn't on the iPhone: install it once with "
                          "`sparsh iphone WDA.ipa` (SETUP.md, C4-C6)")

    def check_signature(self) -> None:
        if self.ipa:
            remember_signature(self.state, self.ipa)
        sig = signature(self.state)
        if sig and sig["days_left"] <= 0:
            raise SparshError(signature_note(sig))
        if signature_note(sig):
            _say(signature_note(sig))

    # -- the whole of it -------------------------------------------------------

    def serve(self) -> None:
        """Until stopped, or until WDA can't be started; what it started stops with it."""
        try:
            self._serve()
        finally:
            self.close()

    def _serve(self) -> None:
        self.state.mkdir(parents=True, exist_ok=True)
        self.check_signature()
        failed, waiting, fresh = 0, False, False
        while True:
            udid = self.phone()
            if udid is None:
                if not waiting:
                    _say("waiting for the iPhone: plug it into this computer, unlock it, "
                         "and answer Trust")
                    waiting = True
                time.sleep(3)
                continue
            waiting = False
            self.ready_tunnel(udid, fresh)
            fresh = False
            self.mount(udid)
            if self.ipa:
                _say(f"installing {self.ipa}")
                _say(_short(self.run("install", f"--path={self.ipa}", f"--udid={udid}",
                                     timeout=600)))
                self.ipa = None
            bundle = self.bundle(self.apps(udid))
            if self.forward is None or self.forward.poll() is not None:
                self.forward = self._spawn("ios-forward.log", "forward", str(PORT), str(PORT),
                                           f"--udid={udid}")
            _say(f"starting WebDriverAgent ({bundle})")
            wda = self._spawn("ios-wda.log", "runwda", f"--bundleid={bundle}",
                              f"--testrunnerbundleid={bundle}",
                              "--xctestconfig=WebDriverAgentRunner.xctest", f"--udid={udid}")
            if self._came_up(wda):
                failed = 0
                _say(f"the iPhone is ready: SPARSH_WDA={URL}")
                self._hold(wda, udid)
                _say("WebDriverAgent stopped (the iPhone was unplugged, or restarted)")
                continue
            said = (self.state / "ios-wda.log").read_text(errors="replace")
            self._stop(wda)
            if _UNTRUSTED in said:
                raise SparshError(
                    "the iPhone won't open WebDriverAgent from a developer it doesn't trust "
                    "yet: on the iPhone, Settings > General > VPN & Device Management > your "
                    "Apple ID > Trust; then run this again")
            failed += 1
            if failed >= TRIES:
                raise SparshError(f"WebDriverAgent didn't start: {_short(said)} "
                                  f"(all of it: {self.state / 'ios-wda.log'})")
            fresh = _NO_SERVICE in said   # the tunnel predates an update: a new one
            _say(f"WebDriverAgent didn't start ({_short(said)}); trying again")

    def _came_up(self, wda: subprocess.Popen) -> bool:
        end = time.monotonic() + START_WAIT
        while time.monotonic() < end:
            if answers():
                return True
            if wda.poll() is not None:
                return False
            time.sleep(1)
        return False

    def _hold(self, wda: subprocess.Popen, udid: str) -> None:
        apps_at = time.monotonic() + APPS_EVERY
        while wda.poll() is None:
            time.sleep(2)
            if time.monotonic() >= apps_at:
                self.apps(udid)
                apps_at = time.monotonic() + APPS_EVERY
        if self.forward is not None:
            self._stop(self.forward)
            self.forward = None

    def _stop(self, proc: subprocess.Popen) -> None:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if proc in self.children:
            self.children.remove(proc)

    def close(self) -> None:
        for proc in list(self.children):
            self._stop(proc)


def _short(text: str) -> str:
    """go-ios's last words, without its JSON wrapping."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except ValueError:
            return line.strip()[:300]
        if isinstance(data, dict) and (data.get("error") or data.get("err")):
            return str(data.get("error") or data.get("err"))[:300]
    if lines:
        try:
            data = json.loads(lines[-1])
            return str(data.get("msg", lines[-1]))[:300] if isinstance(data, dict) else lines[-1]
        except ValueError:
            return lines[-1][:300]
    return "nothing said"


# -- behind: started, stopped, asked about -----------------------------------


def _pid_file(state: Path) -> Path:
    return state / "iphone.pid"


def running(state: Path) -> int | None:
    try:
        pid = int(_pid_file(state).read_text().split()[0])
        os.kill(pid, 0)
    except (OSError, ValueError, IndexError):
        return None
    return pid


def foreground(state: Path, ipa: str | None, prefix: str | None) -> int:
    if running(state) and running(state) != os.getpid():
        _say(f"already running behind (pid {running(state)}); `sparsh iphone --stop` stops it")
        return 0
    if answers():
        _say(f"WebDriverAgent already answers at {URL}")
        return 0
    starter = Starter(state, ipa, prefix)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    _pid_file(state).parent.mkdir(parents=True, exist_ok=True)
    _pid_file(state).write_text(f"{os.getpid()}\n")
    try:
        starter.serve()
    except KeyboardInterrupt:
        return 0
    finally:
        starter.close()
        if running(state) == os.getpid():
            _pid_file(state).unlink(missing_ok=True)
    return 0


def background(state: Path, ipa: str | None, prefix: str | None) -> int:
    """Start it behind, and wait until the phone answers or it gives up."""
    if answers():
        _say(f"the iPhone is ready: SPARSH_WDA={URL}")
        return 0
    if running(state) is None:
        ios_program()   # said here, not in a log nobody reads
        state.mkdir(parents=True, exist_ok=True)
        argv = [sys.executable, "-m", "sparsh.cli", "iphone", "--state", str(state)]
        argv += [ipa] if ipa else []
        argv += ["--prefix", prefix] if prefix else []
        with open(state / "iphone.log", "w") as log:
            subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        _say(f"starting the iPhone behind (what it says: {state / 'iphone.log'})")
    began = time.monotonic()
    while time.monotonic() < began + START_WAIT * 2:
        if answers():
            _say(f"the iPhone is ready: SPARSH_WDA={URL}")
            return 0
        time.sleep(1)
        if running(state) is None and time.monotonic() > began + 3:
            break
    try:
        said = (state / "iphone.log").read_text(errors="replace").strip().splitlines()
    except OSError:
        said = []
    last = said[-1].removeprefix("sparsh: ") if said else "it said nothing"
    if running(state) is not None:
        raise SparshError(f"not ready yet, still trying behind: {last}")
    raise SparshError(last)


def stop(state: Path) -> int:
    pid = running(state)
    if pid is None:
        _say("nothing running behind")
        return 0
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        os.kill(pid, signal.SIGTERM)
    _pid_file(state).unlink(missing_ok=True)
    _say("stopped")
    return 0
