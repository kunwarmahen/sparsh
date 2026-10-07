"""What an agent may do on the phone by itself, and what waits for a yes.

Most of working a phone is harmless and constant -- open Settings, tap a
row, scroll, go back -- and a person asked about every tap would stop
reading the questions by the tenth. So an agent's steps run by
themselves, and Sparsh holds the few that can't be taken back:

* **a tap on something whose words say it acts**: Send, Pay, Buy,
  Order, Delete, Install, Allow, Post, Call ... (``ASK_WORDS``). Matched
  as whole words, anywhere in the label, so "Place order" and "Delete
  account" are held and "Orders" (a tab) is not. "Send to <someone>" is
  a recipient being chosen -- Messages' picker says it -- and isn't held.
  Other wrong guesses go one way: a tap held that didn't need to be costs
  one yes;
* **typing into a password field**;
* nothing at all in an app on the ``never`` list: it can't be opened,
  touched, or even read -- its screen comes back empty.

A held step isn't done. The agent is told why, with a hold id, and the
person's yes comes through the harness when the agent calls ``confirm``
-- a tool every harness asks about (mcp.py). This module decides only;
phone.py keeps the holds and carries them out.

THE PERSON'S FILE, NOT THE MODEL'S. ``~/.sparsh/rules.toml``::

    ask = ["archive", "unfollow"]      # more words that need a yes
    dont_ask = ["share"]               # built-in words not to ask about
    never = ["com.chase.*", "*bank*"]  # apps the agent may not use at all

No tool changes it. The command line (``sparsh tap``) is the person's
own hands and is never held.
"""

from __future__ import annotations

import fnmatch
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from sparsh import SparshError
from sparsh.screen import Element

#: Words on something to tap that mean it does something hard to undo.
ASK_WORDS = (
    "send", "pay", "buy", "purchase", "order", "checkout", "check out",
    "place", "book", "reserve", "subscribe", "donate", "transfer",
    "confirm", "submit", "post", "publish", "share", "reply", "call",
    "delete", "remove", "erase", "reset", "uninstall", "install",
    "allow", "accept", "sign out", "log out", "logout", "unsubscribe", "block",
)  # fmt: skip

FILE = "rules.toml"


@dataclass(frozen=True)
class Rules:
    ask: tuple[str, ...] = ASK_WORDS
    never: tuple[str, ...] = ()

    def why_tap(self, element: Element) -> str | None:
        """Why tapping this needs a yes, or None."""
        label = element.label.lower()
        for word in self.ask:
            for found in re.finditer(rf"(?<![\w]){re.escape(word)}(?![\w])", label):
                if word == "send" and label[found.end() :].startswith(" to "):
                    continue  # "Send to Asha": choosing who, not sending
                return f'it says "{word}"'
        return None

    def why_type(self, field: Element | None) -> str | None:
        if field is not None and field.password:
            return "it is a password field"
        return None

    def forbidden(self, app: str) -> bool:
        return bool(app) and any(fnmatch.fnmatchcase(app.lower(), p) for p in self.never)


def load(state: Path) -> tuple[Rules, Path]:
    """The person's rules (the defaults when there is no file), and where."""
    path = Path(os.environ.get("SPARSH_RULES") or state / FILE)
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return Rules(), path
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise SparshError(f"{path} could not be read: {e}") from e
    unknown = set(raw) - {"ask", "dont_ask", "never"}
    if unknown:
        raise SparshError(f"{path}: unknown keys {', '.join(sorted(unknown))} "
                          "(known: ask, dont_ask, never)")  # fmt: skip
    words = {*ASK_WORDS, *(_words(raw, "ask", path))} - set(_words(raw, "dont_ask", path))
    never = tuple(_words(raw, "never", path))
    return Rules(ask=tuple(sorted(words)), never=never), path


def _words(raw: dict, key: str, path: Path) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SparshError(f"{path}: {key} is a list of words in quotes")
    return [v.strip().lower() for v in value if v.strip()]
