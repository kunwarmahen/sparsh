"""`sparsh`: see a phone's screen as a numbered list, and work it.

    sparsh devices                      phones adb can see, and $SPARSH_WDA
    sparsh pair ADDRESS CODE            trust this computer over Wi-Fi, once
    sparsh connect ADDRESS              reach a paired phone over Wi-Fi
    sparsh tcpip [--port 5555]          the phone on the cable listens over Wi-Fi
    sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
    sparsh look --peek                  the same, leaving the last look as it was
    sparsh tap 7 [--long]               tap 7 from the last look
    sparsh type "hello" [--into 7] [--clear] [--enter]
    sparsh scroll down [--on 4]         down = show what is further down
    sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
    sparsh open settings                open an app by name or package
    sparsh apps [FILTER]                apps that can be opened
    sparsh log [-n 20] [--json]         what was done on the phone, by the agent and by you
    sparsh state [--json]               in use, locked, or asleep: may a schedule use it now
    sparsh wake                         turn the screen on; a lock with no PIN is swiped away
    sparsh mcp                          the agent's tools (MCP, stdio), held by the rules
    sparsh status [--json]              phones, rules, and how a harness starts the tools
    sparsh wda [WDA.ipa]                when the iPhone's WebDriverAgent signature runs out
    sparsh iphone [WDA.ipa] [--background | --stop]
                                        the iPhone on the cable, ready (after an unplug,
                                        a restart or an iOS update too): wdastart.py
    sparsh adb-share [--socket FILE]    this computer's adb, for containers, through a
                                        socket file (adbshare.py)

Every command that does something prints the screen it led to, so the
next number to use is always on the screen. If the screen changed
since the last look, nothing is tapped: the new screen is printed and
the exit code is 3.

Which phone: the one that answers, or ``--serial`` / ``$ANDROID_SERIAL``
(``sparsh devices`` shows the names). An iPhone is named by its
WebDriverAgent's address: ``--serial http://192.168.1.40:8100``.
``$SPARSH_WDA`` says where one would answer; it is used only when it
does, so an Android plugged in in its place is the phone (device.pick).
A phone over Wi-Fi is named by its address, and ``$SPARSH_CONNECT``
reconnects to it whenever phones are looked for.
A phone with no Wireless debugging page (Android 10 and older), or one
that just restarted, is told to listen over the cable: ``sparsh tcpip``
prints the address to use.
The last screen is kept in
``~/.sparsh`` (``--state`` or ``$SPARSH_STATE``), next to the rules
an agent's steps are held by (``rules.toml``, rules.py). These commands
are your own hands and are never held.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sparsh import SparshError, __version__
from sparsh import log, mcp
from sparsh.awake import Awake
from sparsh.awake import mode as awake_mode
from sparsh.device import KEYS, TCPIP_PORT, attached, connect, iphones, pair, pick, tcpip
from sparsh.iphone import remember_apps, remember_signature, signature, signature_note
from sparsh.phone import DIRECTIONS, Phone, ScreenChanged, state_root
from sparsh.rules import load
from sparsh.screen import Screen

#: Exit code when the screen moved under a number (nothing was done).
CHANGED = 3


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    try:
        return args.run(args)
    except ScreenChanged as e:
        print(f"sparsh: {e}", file=sys.stderr)
        return CHANGED
    except SparshError as e:
        print(f"sparsh: {e}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sparsh", description="An agent's hands on a real phone.")
    p.add_argument("--version", action="version", version=f"sparsh {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--serial", help="which phone (default: the only one attached)")
    common.add_argument("--state", help="where the last screen is kept (default ~/.sparsh)")
    common.add_argument("--json", action="store_true", help="print the screen as JSON")
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("devices", parents=[common], help="phones adb can see")
    s.set_defaults(run=_devices)

    s = sub.add_parser(
        "pair",
        parents=[common],
        help="trust this computer over Wi-Fi, once: the address and six-digit "
        "code the phone's 'Pair device with pairing code' shows",
    )
    s.add_argument("address")
    s.add_argument("code")
    s.set_defaults(run=_pair)

    s = sub.add_parser(
        "connect",
        parents=[common],
        help="reach a paired phone over Wi-Fi (the address on its Wireless "
        "debugging page); $SPARSH_CONNECT does it every time",
    )
    s.add_argument("address")
    s.set_defaults(run=_connect)

    s = sub.add_parser(
        "tcpip",
        parents=[common],
        help="the phone on the USB cable listens over Wi-Fi (again after each restart)",
    )
    s.add_argument("--port", type=int, default=TCPIP_PORT, help=f"default {TCPIP_PORT}")
    s.set_defaults(run=_tcpip)

    s = sub.add_parser("look", parents=[common], help="the screen as a numbered list")
    s.add_argument("--shot", metavar="FILE", help="also save a screenshot (PNG)")
    s.add_argument("--peek", action="store_true",
                   help="don't remember this look: an agent's numbers keep meaning "
                        "what they meant")  # fmt: skip
    s.set_defaults(run=_look)

    s = sub.add_parser("tap", parents=[common], help="tap a number from the last look")
    s.add_argument("n", type=int)
    s.add_argument("--long", action="store_true", help="press and hold")
    s.set_defaults(run=_tap)

    s = sub.add_parser("type", parents=[common], help="type text (beyond ASCII: SETUP.md, Part G)")
    s.add_argument("text")
    s.add_argument("--into", type=int, metavar="N", help="tap this field first")
    s.add_argument("--clear", action="store_true", help="empty the field first")
    s.add_argument("--enter", action="store_true", help="press enter after")
    s.set_defaults(run=_type)

    s = sub.add_parser("scroll", parents=[common], help="scroll the screen, or one list on it")
    s.add_argument("direction", choices=DIRECTIONS)
    s.add_argument("--on", type=int, metavar="N", help="scroll this list only")
    s.set_defaults(run=_scroll)

    s = sub.add_parser("key", parents=[common], help=f"press keys: {', '.join(KEYS)}")
    s.add_argument("names", nargs="+")
    s.set_defaults(run=_key)

    s = sub.add_parser("open", parents=[common], help="open an app by name or package")
    s.add_argument("name")
    s.set_defaults(run=_open)

    s = sub.add_parser("apps", parents=[common], help="apps that can be opened")
    s.add_argument("like", nargs="?", default="")
    s.set_defaults(run=_apps)

    s = sub.add_parser("log", parents=[common], help="what was done on the phone, oldest first")
    s.add_argument("-n", type=int, default=20, help="how many steps (default 20)")
    s.set_defaults(run=_log)

    s = sub.add_parser(
        "state",
        parents=[common],
        help="in use, locked or asleep: whether a schedule may use it now",
    )
    s.set_defaults(run=_state)

    s = sub.add_parser("wake", parents=[common], help="turn the screen on")
    s.set_defaults(run=_wake)

    s = sub.add_parser("mcp", parents=[common], help="the agent's tools, as an MCP server")
    s.add_argument(
        "--shots",
        action="store_true",
        help="attach a screenshot when a screen can't be read as a list",
    )
    s.set_defaults(run=_mcp)

    s = sub.add_parser("status", parents=[common], help="phones, rules, and the agent's tools")
    s.set_defaults(run=_status)

    s = sub.add_parser("wda", parents=[common],
                       help="when the iPhone's WebDriverAgent signature runs out; "
                            "given WDA.ipa, remember it")  # fmt: skip
    s.add_argument("ipa", nargs="?", help="the WDA.ipa just built (build-wda-on-mac.sh)")
    s.add_argument("--apps", metavar="FILE",
                   help="remember the apps on the iPhone, from what `ios apps --list` "
                        "printed (- for stdin; `sparsh iphone` does it)")  # fmt: skip
    s.set_defaults(run=_wda)

    s = sub.add_parser("iphone", parents=[common],
                       help="start WebDriverAgent on the iPhone on the cable, and keep it "
                            "running (tunnel, developer image, port 8100)")  # fmt: skip
    s.add_argument("ipa", nargs="?", help="install this WDA.ipa first (just built)")
    s.add_argument("--background", action="store_true",
                   help="run behind; return once the iPhone answers")
    s.add_argument("--stop", action="store_true", help="stop the one running behind")
    s.add_argument("--prefix", help="the PREFIX WDA was built with (default: found on the phone)")
    s.set_defaults(run=_iphone)

    s = sub.add_parser("adb-share", parents=[common],
                       help="hand this computer's adb (the phone on the cable) to containers, "
                            "through a socket file in ~/.sparsh")  # fmt: skip
    s.add_argument("--socket", help="the socket file (default: adb.sock in the state folder)")
    s.set_defaults(run=_adb_share)
    return p


def _phone(args) -> Phone:
    return Phone(pick(args.serial), args.state)


def _show(args, screen: Screen) -> int:
    if args.json:
        print(json.dumps(screen.to_json(), ensure_ascii=False, indent=1))
    else:
        print(screen.text())
    return 0


def _devices(args) -> int:
    found = iphones()
    try:
        phones = attached()
    except SparshError:
        if not found:
            raise
        phones = []
    phones += found
    if not phones:
        print("No phone attached. Plug one in with USB debugging on, or start the emulator.")
    for phone in phones:
        print(phone.line())
    note = signature_note(signature(state_root(args.state))) if found else ""
    if note:
        print(f"Note: {note}.")
    return 0


def _pair(args) -> int:
    print(pair(args.address, args.code))
    print(
        "Now connect to the address on the phone's Wireless debugging page "
        "(not the pairing one): sparsh connect ADDRESS"
    )
    return 0


def _connect(args) -> int:
    said = connect(args.address)
    print(said)
    return 0 if "connected" in said and "cannot" not in said and "failed" not in said else 1


def _tcpip(args) -> int:
    done = tcpip(args.serial, args.port)
    if args.json:
        print(json.dumps(done))
        return 0 if done["connected"] else 1
    if not done["connected"]:
        print(f"{done['serial']} was told to listen at {done['address']}, but didn't "
              f"answer there: {done['said']}")
        print("Is this computer on the same Wi-Fi as the phone? Try "
              f"`sparsh connect {done['address']}` in a moment.")
        return 1
    print(f"{done['serial']} listens over Wi-Fi at {done['address']}, and is connected.")
    print("The cable can come out. A restart of the phone turns this off: plug it in "
          "and run `sparsh tcpip` again.")
    print(f"Elsewhere (a container, another computer): SPARSH_CONNECT={done['address']}, "
          f"or `sarathi phone {done['address']}`.")
    return 0


def _look(args) -> int:
    screen = _phone(args).look(shot=args.shot, keep=not args.peek)
    if args.shot:
        print(f"(screenshot saved to {args.shot})", file=sys.stderr)
    return _show(args, screen)


def _done(args, action: str, asked: dict, run) -> int:
    """Do one act by hand, written down by "you" (log.py)."""
    phone = _phone(args)
    return _show(args, log.recorded(phone, "you", action, asked, lambda: run(phone)))


def _tap(args) -> int:
    return _done(args, "tap", {"n": args.n, **({"long": True} if args.long else {})},
                 lambda p: p.tap(args.n, long=args.long))  # fmt: skip


def _type(args) -> int:
    asked = {"text": args.text, "into": args.into, "clear": args.clear, "enter": args.enter}
    asked = {k: v for k, v in asked.items() if v not in (None, False)}
    return _done(args, "type_text", asked, lambda p: p.type(
        args.text, into=args.into, clear=args.clear, enter=args.enter))  # fmt: skip


def _scroll(args) -> int:
    asked = {"direction": args.direction, **({"on": args.on} if args.on else {})}
    return _done(args, "scroll", asked, lambda p: p.scroll(args.direction, on=args.on))


def _key(args) -> int:
    return _done(args, "press_key", {"keys": args.names}, lambda p: p.key(*args.names))


def _open(args) -> int:
    return _done(args, "open_app", {"name": args.name}, lambda p: p.open_app(args.name))


def _log(args) -> int:
    steps = log.recent(_phone(args), args.n)
    if args.json:
        print(json.dumps(steps, ensure_ascii=False, indent=1))
    elif not steps:
        print("Nothing done on this phone yet.")
    for step in reversed(steps if not args.json else []):
        print(log.line(step))
    return 0


def _state(args) -> int:
    phone = _phone(args)
    found = {"serial": phone.device.serial, **phone.state()}
    if args.json:
        print(json.dumps(found))
        return 0
    words = {"in_use": "in use: the screen is on and unlocked",
             "locked": "locked: only its person can open it",
             "asleep": "asleep: nobody has it, and no PIN stands in the way",
             "unknown": "unknown: the phone didn't say"}  # fmt: skip
    print(f"{found['serial']}: {words[found['state']]}")
    return 0


def _wake(args) -> int:
    phone = _phone(args)
    print(f"{phone.device.serial}: screen on ({phone.wake()['state']})")
    return 0


def _apps(args) -> int:
    for app in _phone(args).apps(args.like):
        print(app)
    return 0


def _mcp(args) -> int:
    state = state_root(args.state)
    rules, _ = load(state)
    keeper = Awake(awake_mode())  # $SPARSH_AWAKE, checked before the first call
    try:
        mcp.serve(mcp.Tools(rules, state=state, serial=args.serial, shots=args.shots, awake=keeper))
    finally:
        keeper.rest()  # the person's own screen timeout back as the server stops
    return 0


def _status(args) -> int:
    from sparsh.status import report

    data = report(state_root(args.state))
    if args.json:
        print(json.dumps(data, indent=1))
        return 0
    print(f"sparsh {data['version']}, state in {data['state']}")
    if data["adb"] != "ok":
        print(f"adb: {data['adb']}")
    for phone in data["phones"]:
        print(f"phone: {phone['serial']}  {phone['model'] or '?'}  {phone['state']}")
    if data["adb"] == "ok" and not data["phones"]:
        print("phone: none attached")
    rules = data["rules"]
    print(f"rules: {rules['path']}" + ("" if rules["exists"] else " (not written; the defaults)"))
    print(f"  never: {', '.join(rules['never']) or '(no app is off limits)'}")
    print(f"  a tap needs a yes when it says: {', '.join(rules['ask'])}")
    print("  typing into a password field always needs a yes")
    print(f"agent's tools: {data['mcp']['command']} {' '.join(data['mcp']['args'])}")
    if data["wda"]:
        print(f"iPhone's WebDriverAgent: {_signed(data['wda'])}")
    return 0


def _wda(args) -> int:
    state = state_root(args.state)
    if args.apps:
        text = sys.stdin.read() if args.apps == "-" else Path(args.apps).read_text()
        try:
            found = remember_apps(state, text)
        except ValueError as e:
            raise SparshError(str(e)) from None
        print(f"remembered {len(found)} apps on the iPhone")
        if not args.ipa:
            return 0
    if args.ipa:
        remember_signature(state, args.ipa)
    sig = signature(state)
    if sig is None:
        print("No WDA.ipa remembered yet. After building it: sparsh wda WDA.ipa")
        return 0
    if args.json:
        print(json.dumps(sig, indent=1))
    else:
        print(f"{sig['ipa']}: {_signed(sig)}")
    if sig["days_left"] <= 0:
        raise SparshError(signature_note(sig))
    return 0


def _iphone(args) -> int:
    from sparsh import wdastart

    state = state_root(args.state)
    ipa = str(Path(args.ipa).resolve()) if args.ipa else None
    if args.stop:
        return wdastart.stop(state)
    if args.background:
        return wdastart.background(state, ipa, args.prefix)
    return wdastart.foreground(state, ipa, args.prefix)


def _adb_share(args) -> int:
    from sparsh import adbshare
    from sparsh.device import adb_path

    path = Path(args.socket).expanduser() if args.socket else adbshare.socket_path(args.state)
    print(f"sharing adb at {path}; in a container: "
          f"ADB_SERVER_SOCKET=localfilesystem:{path}", flush=True)
    import signal

    # systemd stops a unit with SIGTERM: leave by the same door as Ctrl-C,
    # so the socket file goes with it
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        adbshare.serve(path, adb_path())
    except KeyboardInterrupt:
        pass
    return 0


def _signed(sig: dict) -> str:
    when = datetime.fromisoformat(sig["signed_until"]).astimezone().strftime("%a %d %b %H:%M")
    left = sig["days_left"]
    said = f"signed until {when}" + (f" ({left:g} days left)" if left > 0 else " (ran out)")
    note = signature_note(sig)
    return said + (f" -- {note}" if note and left > 0 else "")


if __name__ == "__main__":
    sys.exit(main())
