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

A HARNESS MAY ADD RULES FOR AN APP, NEVER TAKE ANY AWAY.
``$SPARSH_APP_RULES`` is JSON, by app package, from whoever starts the
agent's tools -- Yantra, from Setu's phone connections (an X app used at
"Read only")::

    {"com.twitter.android": {"refuse": ["post", "like", "buy"],
                             "ask": [], "pace": 3.0,
                             "why": "Setu: X (x:personal) is Read only"}}

``refuse``: a tap on these words is not done at all, with a sentence --
no yes gets through it, as a level below it would need changing first.
``ask``: held for a yes, like ``ask`` above. ``pace``: seconds between
steps in that app, at least (X locks accounts that tap too fast). Each
only adds to the person's file: nothing here can make a step run that
the person's rules would hold, or open an app they keep out.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
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
class AppRule:
    """What a harness added for one app (``$SPARSH_APP_RULES``)."""

    refuse: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()
    pace: float = 0.0
    why: str = ""


@dataclass(frozen=True)
class Rules:
    ask: tuple[str, ...] = ASK_WORDS
    never: tuple[str, ...] = ()
    apps: dict[str, AppRule] = field(default_factory=dict)

    def why_tap(self, element: Element, app: str = "") -> str | None:
        """Why tapping this needs a yes, or None."""
        word = _says(element.label, self.ask)
        if word is None and app in self.apps:
            word = _says(element.label, self.apps[app].ask)
        return f'it says "{word}"' if word else None

    def refused(self, element: Element, app: str) -> str | None:
        """Why tapping this in ``app`` is not done at all, or None."""
        rule = self.apps.get(app)
        word = _says(element.label, rule.refuse) if rule else None
        if word is None:
            return None
        return (
            f'{element.kind} "{element.label}" says "{word}", which is not done here: '
            f"{rule.why or 'the rules for this app refuse it'}. REFUSED, NOT HELD: there "
            "is no hold and nothing to confirm. Stop and tell the person; it is theirs "
            "to do on the phone, or to allow by changing the level"
        )

    def pace(self, app: str) -> float:
        rule = self.apps.get(app)
        return rule.pace if rule else 0.0

    def why_type(self, field: Element | None) -> str | None:
        if field is not None and field.password:
            return "it is a password field"
        return None

    def forbidden(self, app: str) -> bool:
        return bool(app) and any(fnmatch.fnmatchcase(app.lower(), p) for p in self.never)


def _says(label: str, words: tuple[str, ...]) -> str | None:
    """The first of ``words`` in ``label``, as a whole word, or None."""
    label = label.lower()
    for word in words:
        for found in re.finditer(rf"(?<![\w]){re.escape(word)}(?![\w])", label):
            if word == "send" and label[found.end() :].startswith(" to "):
                continue  # "Send to Asha": choosing who, not sending
            return word
    return None


def app_rules(raw: str | None = None) -> dict[str, AppRule]:
    """``$SPARSH_APP_RULES``, checked. A harness that sends something
    unreadable is told so, rather than its rules being dropped quietly:
    rules that went missing would make the phone looser, not tighter."""
    raw = os.environ.get("SPARSH_APP_RULES", "") if raw is None else raw
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SparshError(f"SPARSH_APP_RULES is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise SparshError("SPARSH_APP_RULES is an object, by app package")
    found = {}
    for app, spec in data.items():
        if not isinstance(spec, dict) or set(spec) - {"refuse", "ask", "pace", "why"}:
            raise SparshError(f"SPARSH_APP_RULES[{app!r}] takes refuse, ask, pace and why")
        words = {}
        for key in ("refuse", "ask"):
            value = spec.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise SparshError(f"SPARSH_APP_RULES[{app!r}].{key} is a list of words")
            words[key] = tuple(v.strip().lower() for v in value if v.strip())
        try:
            pace = max(0.0, float(spec.get("pace", 0) or 0))
        except (TypeError, ValueError):
            raise SparshError(f"SPARSH_APP_RULES[{app!r}].pace is seconds") from None
        found[str(app)] = AppRule(
            refuse=words["refuse"], ask=words["ask"], pace=pace, why=str(spec.get("why") or "")
        )
    return found


def load(state: Path) -> tuple[Rules, Path]:
    """The person's rules (the defaults when there is no file), and where."""
    path = Path(os.environ.get("SPARSH_RULES") or state / FILE)
    try:
        raw = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return Rules(apps=app_rules()), path
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise SparshError(f"{path} could not be read: {e}") from e
    unknown = set(raw) - {"ask", "dont_ask", "never"}
    if unknown:
        raise SparshError(f"{path}: unknown keys {', '.join(sorted(unknown))} "
                          "(known: ask, dont_ask, never)")  # fmt: skip
    words = {*ASK_WORDS, *(_words(raw, "ask", path))} - set(_words(raw, "dont_ask", path))
    never = tuple(_words(raw, "never", path))
    return Rules(ask=tuple(sorted(words)), never=never, apps=app_rules()), path


def _words(raw: dict, key: str, path: Path) -> list[str]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SparshError(f"{path}: {key} is a list of words in quotes")
    return [v.strip().lower() for v in value if v.strip()]
