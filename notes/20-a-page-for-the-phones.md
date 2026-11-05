# 20 — A page for the phones

Last night a watch opened Harris Teeter's ice-cream page on the Nexus,
twice, at 22:54. Yesterday afternoon it opened Food Lion's, and the day
before that too. Every one of those steps is in the phone's log
(`~/.sparsh/phones/192.168.1.160_5555/actions.jsonl`). None of them
showed up on any page.

The phone panel on Yantra's page shows the steps that Yantra's chat
took, and Sarathi's "Your phones" card opened that page. Most of what
works a phone isn't that chat, though. Samay's scheduled runs, Prahari's
watches on a spare phone, the people on Dvara's door and a voice at the
puck all go through `sparsh mcp`. Their steps land in the same log, and
the only way to read them was `sparsh log` in a terminal.

`sparsh serve` is Sparsh's own page:

```
$ sparsh serve
Sparsh's page: http://127.0.0.1:8794/
  http://127.0.0.1:8794/#token=…
```

For each phone it shows its name, Android or iPhone, whether it answers
(and why not, as a person would fix it) and whether it's spare. Under
that is every step done on it, newest first, with who asked. **Look**
reads the screen on request and shows the list beside a screenshot,
with the battery. **List** gives the list alone. Your rules are at the
bottom.

## The page watches, it never touches

There is no tap button, no typing box and no wake. A page that could tap
would be a second way to work the phone, one that goes around the rules
and the holds (notes/02). Every act on a phone stays where it was: an
agent's step, held for your yes when the rules say so, or your own
finger. The page answers every `POST` with `405 this page only watches`.

A **Look** is a *peek* (`look(keep=False)`, the same read `look --peek`
does). It reads the screen without storing it as the agent's last look,
so if an agent is halfway through a job, its numbers still mean what
they meant. It also carries your rules. If an app is one you keep the
agent out of (`never`), its screen is described, not shown: there's no
list and no screenshot. If the page showed it, the page would be the
one way in to the very screen you said nobody looks at.

## Named phones are listed whether they answer or not

A page that lists only the phones adb can see would drop exactly the
phone you're worried about. So every phone `SPARSH_PHONES` names gets a
card, even when it doesn't answer, with the reason from `sparsh status`
or a sentence of its own: "not answering: is WebDriverAgent running?".
Any other phone that answers is listed after the named ones. A peek or
a step list is only given for a phone on the page. The token opens the
phones this Sparsh was given, not whatever else is on the cable.

## Who asked

Yantra, Samay, Prahari and Dvara all start the same `sparsh mcp`, so
Sparsh can't tell them apart by itself. So whoever starts it says who it
is, in `$SPARSH_ASKED_BY`, and every step that server takes carries that
label in the log's `via` field:

| Who started it | What the step says |
|---|---|
| Yantra's page | `Yantra's page` |
| a Samay schedule run here | `Samay: Tell me my battery and any… (bfaea182)` |
| a Prahari watch looking here | `Prahari: Mayfield ice cream` |
| a turn on Dvara | `Telegram · asha`, `Vaani: kitchen puck · asha`, `Samay: … · mahen` |

Samay and Prahari set `YANTRA_ASKED_BY` for the Yantra runs they start,
and Yantra hands it on. For runs that go through Dvara, they send a
`label` (the schedule's start and id, the watch's name, the puck), and
Dvara adds the way the turn came in and the person. A step done after a
yes says where the yes came from (Dvara's rule: a turn carried on by an
answer is that answer's). **Show steps asked for by** on the page keeps
one program's steps only. Steps logged before this have no `via` and
read *agent*.

Live, on the Nexus over Wi-Fi: Yantra's own link started `sparsh mcp`
with `YANTRA_ASKED_BY="Samay: live check (scratch01)"`, and one Back
press landed in the log as

```
{"at": "2026-11-05T10:59:50-05:00", "by": "agent", "via": "Samay: live check (scratch01)",
 "action": "press_key", "args": {"keys": ["back"]}, "outcome": "done", "app": "com.android.chrome", …}
```

and on the page as *10:59 · Samay: live check (scratch01) · press_key
keys=["back"] → done*, beside a *Telegram · asha* step and one of *you*.

**A label, never a key.** It's what a program said about itself, for
you to read. Anything that can start `sparsh mcp` could write anything
there, and only your own programs do. Nothing is decided by it. It's cut
to 120 characters with control characters taken out, so a label can't
fill the log or forge a line in it.

## A token, always

This works like every page in the family. Any web page you visit can
send a request to 127.0.0.1, so each `/api` call has to carry the token.
The token is `$SPARSH_PAGE_TOKEN`, or one made once and kept in
`~/.sparsh/page.token`, readable by you alone. Sarathi reads that file
to open the page already signed in. The page itself loads its script
from its own address only (`script-src 'self'`), and screenshots arrive
as data.

## Live receipt

The Nexus 6P over Wi-Fi and the iPhone 17 with WebDriverAgent stopped,
named as Sarathi names them:

```
$ SPARSH_PHONES="iphone=http://127.0.0.1:8100,nexus=192.168.1.160:5555" \
  SPARSH_SPARE=nexus sparsh serve --port 18794
$ curl -H "Authorization: Bearer …" http://127.0.0.1:18794/api/state
adb: ok
wda note: the iPhone's WebDriverAgent signature ran out on Sat 24 Oct 14:49:
  rebuild it on the Mac (build-wda-on-mac.sh) and install the new WDA.ipa
iphone iPhone offline iPhone | not answering -- start WebDriverAgent on it
    2026-10-17T19:25 you tap {"n": 25} -> done
nexus Android device Nexus_6P spare |
    2026-11-04T22:54 agent open_url {"url": "https://www.harristeeter.com/p/mayfield-…"} -> done
    2026-11-04T15:51 agent open_url {"url": "https://foodlion.com/product/tillamook-…"} -> done
```

The iPhone's last steps are the ones its person showed the agent on
17 October (notes/17). The Nexus's are Prahari's watches, which no page
had shown until now. A peek of the Nexus, in 5.2 s:

```
app: com.android.systemui  battery: {'level': 100, 'charging': True}  shot bytes: 26808
(The phone is locked: this is its lock screen, not the app asked for. …)
1 image "Google Play services notification: New sign-in on Pixel 8"
```

With the wrong token: `{"detail": "missing or wrong token"}`. A `POST`:
`{"detail": "this page only watches: nothing here acts on a phone"}`.

## What was deliberately not built

* **Changing names, owners and spares here.** Those are Sarathi's
  `[phone]` settings, and Sarathi's Settings page writes them. A second
  place to edit them would be a second file that can disagree.
* **A screen that refreshes itself.** A peek is a real read of the
  phone, a second or more of `uiautomator dump`, so it happens when you
  press Look and never on a timer. The steps and the phones refresh
  every five seconds, from files.
