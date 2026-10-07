"""`sparsh`: see a phone's screen as a numbered list, and work it.

    sparsh devices                      phones adb can see, and $SPARSH_WDA
    sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
    sparsh look --peek                  the same, leaving the last look as it was
    sparsh tap 7 [--long]               tap 7 from the last look
    sparsh type "hello" [--into 7] [--clear] [--enter]
    sparsh scroll down [--on 4]         down = show what is further down
    sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
    sparsh open settings                open an app by name or package
    sparsh apps [FILTER]                apps that can be opened
    sparsh log [-n 20] [--json]         what was done on the phone, by the agent and by you
    sparsh mcp                          the agent's tools (MCP, stdio), held by the rules
    sparsh status [--json]              phones, rules, and how a harness starts the tools
    sparsh wda [WDA.ipa]                when the iPhone's WebDriverAgent signature runs out

Every command that does something prints the screen it led to, so the
next number to use is always on the screen. If the screen changed
since the last look, nothing is tapped: the new screen is printed and
the exit code is 3.

Which phone: the only one attached, or ``--serial`` / ``$ANDROID_SERIAL``
(``sparsh devices`` shows the names). An iPhone is named by its
WebDriverAgent's address: ``--serial http://192.168.1.40:8100``, or
``$SPARSH_WDA``. The last screen is kept in
``~/.sparsh`` (``--state`` or ``$SPARSH_STATE``), next to the rules
an agent's steps are held by (``rules.toml``, rules.py). These commands
are your own hands and are never held.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from sparsh import SparshError, __version__
from sparsh import log, mcp
from sparsh.device import KEYS, attached, iphones, pick
from sparsh.iphone import remember_signature, signature, signature_note
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

    s = sub.add_parser("mcp", parents=[common], help="the agent's tools, as an MCP server")
    s.set_defaults(run=_mcp)

    s = sub.add_parser("status", parents=[common], help="phones, rules, and the agent's tools")
    s.set_defaults(run=_status)

    s = sub.add_parser("wda", parents=[common],
                       help="when the iPhone's WebDriverAgent signature runs out; "
                            "given WDA.ipa, remember it")  # fmt: skip
    s.add_argument("ipa", nargs="?", help="the WDA.ipa just built (build-wda-on-mac.sh)")
    s.set_defaults(run=_wda)
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


def _apps(args) -> int:
    for app in _phone(args).apps(args.like):
        print(app)
    return 0


def _mcp(args) -> int:
    state = state_root(args.state)
    rules, _ = load(state)
    mcp.serve(mcp.Tools(rules, state=state, serial=args.serial))
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


def _signed(sig: dict) -> str:
    when = datetime.fromisoformat(sig["signed_until"]).astimezone().strftime("%a %d %b %H:%M")
    left = sig["days_left"]
    said = f"signed until {when}" + (f" ({left:g} days left)" if left > 0 else " (ran out)")
    note = signature_note(sig)
    return said + (f" -- {note}" if note and left > 0 else "")


if __name__ == "__main__":
    sys.exit(main())
