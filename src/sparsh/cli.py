"""`sparsh`: see a phone's screen as a numbered list, and work it.

    sparsh devices                      phones adb can see
    sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
    sparsh tap 7 [--long]               tap 7 from the last look
    sparsh type "hello" [--into 7] [--clear] [--enter]
    sparsh scroll down [--on 4]         down = show what is further down
    sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
    sparsh open settings                open an app by name or package
    sparsh apps [FILTER]                apps that can be opened
    sparsh mcp                          the agent's tools (MCP, stdio), held by the rules
    sparsh status [--json]              phones, rules, and how a harness starts the tools

Every command that does something prints the screen it led to, so the
next number to use is always on the screen. If the screen changed
since the last look, nothing is tapped: the new screen is printed and
the exit code is 3.

Which phone: the only one attached, or ``--serial`` / ``$ANDROID_SERIAL``
(``sparsh devices`` shows the names). The last screen is kept in
``~/.sparsh`` (``--state`` or ``$SPARSH_STATE``), next to the rules
an agent's steps are held by (``rules.toml``, rules.py). These commands
are your own hands and are never held.
"""

from __future__ import annotations

import argparse
import json
import sys

from sparsh import SparshError, __version__
from sparsh import mcp
from sparsh.device import KEYS, attached, pick
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
    s.set_defaults(run=_look)

    s = sub.add_parser("tap", parents=[common], help="tap a number from the last look")
    s.add_argument("n", type=int)
    s.add_argument("--long", action="store_true", help="press and hold")
    s.set_defaults(run=_tap)

    s = sub.add_parser("type", parents=[common], help="type text (plain ASCII for now)")
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

    s = sub.add_parser("mcp", parents=[common], help="the agent's tools, as an MCP server")
    s.set_defaults(run=_mcp)

    s = sub.add_parser("status", parents=[common], help="phones, rules, and the agent's tools")
    s.set_defaults(run=_status)
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
    phones = attached()
    if not phones:
        print("No phone attached. Plug one in with USB debugging on, or start the emulator.")
    for phone in phones:
        print(phone.line())
    return 0


def _look(args) -> int:
    screen = _phone(args).look(shot=args.shot)
    if args.shot:
        print(f"(screenshot saved to {args.shot})", file=sys.stderr)
    return _show(args, screen)


def _tap(args) -> int:
    return _show(args, _phone(args).tap(args.n, long=args.long))


def _type(args) -> int:
    phone = _phone(args)
    return _show(args, phone.type(args.text, into=args.into, clear=args.clear, enter=args.enter))


def _scroll(args) -> int:
    return _show(args, _phone(args).scroll(args.direction, on=args.on))


def _key(args) -> int:
    return _show(args, _phone(args).key(*args.names))


def _open(args) -> int:
    return _show(args, _phone(args).open_app(args.name))


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
