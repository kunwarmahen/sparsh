"""Several phones at once, each by a name.

    SPARSH_PHONES="nexus=192.168.1.160:5555,iphone=http://127.0.0.1:8100"
    sparsh mcp --phone nexus=192.168.1.160:5555 --phone iphone=http://...
    sparsh look --phone nexus

A name is the person's own word for a phone (``nexus``, ``asha-iphone``):
lower case, digits and dashes. What follows ``=`` is how the phone is
reached -- an Android's adb serial or Wi-Fi address, or an iPhone's
WebDriverAgent address -- the same words ``--serial`` takes.

ONE SERVER, MANY PHONES. Not one server per phone: the tools stay
``look``, ``tap``..., so a harness's allow list, its tool picker and
its rule that asks before ``confirm`` keep working unchanged. Every
tool takes ``phone`` once more than one is named; with one it is never
needed. A phone the server wasn't given is not a phone it can reach:
a harness that names only a person's own phones has kept every other
phone out of that person's agent.

UNNAMED IS TODAY. With no ``SPARSH_PHONES`` and no ``--phone``, the
phone is the one that answers (device.pick), as it always was.

``--phone`` on the command line: ``NAME=WHERE`` names a phone (over
``$SPARSH_PHONES`` when the name is in both); a bare ``NAME`` picks from
the ones named, so ``sparsh mcp --phone nexus`` serves only the Nexus
of the phones ``$SPARSH_PHONES`` lists.
"""

from __future__ import annotations

import os
import re

from sparsh import SparshError
from sparsh.iphone import is_wda

NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")


def parse(raw: str) -> dict[str, str]:
    """``nexus=ADDR,iphone=URL`` as {name: where}, in the order written."""
    found: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        name, eq, where = part.partition("=")
        name, where = name.strip(), where.strip()
        if not eq or not where:
            raise SparshError(f"{part!r} names no phone: write NAME=WHERE "
                              "(nexus=192.168.1.160:5555, iphone=http://127.0.0.1:8100)")
        _check(name)
        if name in found:
            raise SparshError(f"the phone {name!r} is named twice")
        found[name] = where
    return found


def named(raw: str | None = None) -> dict[str, str]:
    """The phones ``$SPARSH_PHONES`` names ({} when it names none)."""
    return parse(os.environ.get("SPARSH_PHONES", "") if raw is None else raw)


def chosen(given: list[str] | None, env: str | None = None) -> dict[str, str]:
    """The phones a command works with: ``--phone`` over ``$SPARSH_PHONES``
    (the module docstring). {} means unnamed: the phone that answers."""
    phones = named(env)
    picked: list[str] = []
    for item in given or []:
        if "=" in item:
            phones.update(parse(item))
            picked.append(item.partition("=")[0].strip())
        else:
            _check(item)
            if item not in phones:
                raise SparshError(f"no phone is called {item!r}" + _among(phones))
            picked.append(item)
    if picked and any("=" not in item for item in given or []):
        return {name: phones[name] for name in dict.fromkeys(picked)}
    return phones


def one(given: list[str] | None, env: str | None = None) -> tuple[str, str] | None:
    """The one phone a hand command works: (name, where), or None when no
    phone is named (then it is the phone that answers)."""
    phones = chosen(given, env)
    if not phones:
        return None
    if len(phones) > 1:
        raise SparshError("which phone? choose with --phone" + _among(phones))
    return next(iter(phones.items()))


def kind(where: str) -> str:
    return "iPhone" if is_wda(where) else "Android"


def android_addresses(env: str | None = None) -> list[str]:
    """The named Androids reached over Wi-Fi: connected to like
    ``$SPARSH_CONNECT``'s, so a phone named by its address is found again
    after adb forgets it."""
    try:
        phones = named(env)
    except SparshError:
        return []
    return [w for w in phones.values()
            if not is_wda(w) and re.fullmatch(r"[A-Za-z0-9.\-\[\]:]+:\d{1,5}", w)]


def _check(name: str) -> None:
    if not NAME.fullmatch(name):
        raise SparshError(f"{name!r} can't name a phone: lower case letters, digits and "
                          "dashes (nexus, asha-iphone)")


def _among(phones: dict[str, str]) -> str:
    if not phones:
        return " (none are named: SPARSH_PHONES or --phone NAME=WHERE)"
    return " (" + ", ".join(f"{n}: {kind(w)}" for n, w in phones.items()) + ")"
