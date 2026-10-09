# 01 — A list, not a picture

An agent that can drive a browser still can't reach most of a person's
day. Messages, the bank, the food order, the two-factor code: those
live in phone apps, and a phone app has no URL to open and no API to
call. To use one, a program has to do what a person does: look at the
screen, and touch it.

Sparsh is the touching part. It runs on the computer, talks to an
Android phone (or the emulator) through `adb`, and offers five verbs:
look, tap, type, scroll, press a key, plus opening an app. Nothing is
installed on the phone.

## What the model sees

The usual design sends the model a screenshot and asks for
coordinates. That makes the model's eyesight the whole system: a
vision model has to find a 40-pixel switch in a 1080×2400 picture and
say where its middle is. Cloud models do this tolerably. Local ones
mostly don't, and about half of the people who'd run this run a local
model.

Android already has a better description of the screen: the
accessibility tree, the same thing TalkBack reads aloud. `uiautomator
dump` prints it as XML. It's in words, it marks what can be tapped, typed
into, scrolled or switched, and it gives every box's bounds. **THE MODEL
READS WORDS AND ANSWERS WITH A NUMBER.** It never sees a coordinate,
so it can't get one wrong.

The raw tree isn't fit to read, though. The Settings screen in
`tests/screens/settings.xml` has 67 nodes. A single row ("Network &
internet") is a tappable `LinearLayout` with no words of its own,
holding an icon frame, an icon, a text frame, a title and a summary:
five nodes for one thing. `screen.py` folds that down:

* **A tappable box takes its words from inside.** The title and summary
  become its label (`"Network & internet — Mobile, Wi‑Fi, hotspot"`), and
  they don't get lines of their own. The walk inside stops at anything
  that acts on its own: a button inside a row keeps its own line.
* **A switch that can't be tapped by itself is the row's on/off.** In
  Android's Settings, the Airplane mode switch isn't clickable; the row
  is. So the row says `[tap, off]` and the switch disappears into it.
* **Boxes with no size are left out.** A row scrolled half off the
  bottom reports its icon at `[0,2395][147,2337]`, upside down. There's
  nothing there to tap.
* **A list with no label borrows the app's own name for it**
  (`resource-id`), so two scrolling areas on one screen can be told
  apart.

67 nodes become 13 lines. A local model reads 13 lines the way it reads
anything else.

## A number is checked before it is tapped

A number is only good for the screen it was read from, and phones
don't hold still. A page finishes loading, a permission dialog arrives,
a notification shade comes down. The cheap version, remembering
coordinates and tapping them later, is how an agent taps "Delete" when
it meant "Archive".

**NOTHING IS TAPPED THAT WASN'T READ.** `Phone.tap(7)` reads the screen
again first, and looks for the thing that was 7: same kind, same label,
same box. If it's there (even under another number, because something
appeared above it), Sparsh taps its middle. If it isn't, nothing is
tapped, and `ScreenChanged` carries the screen as it is now, so the
agent's next step starts from the truth. On the command line that's
exit 3, with the new screen on stderr.

The price is time. A dump takes about 2.5 seconds on the emulator, and a
tap is a check, the tap, a short wait and a fresh look, about 5 seconds
in all. That's slow for a person at a keyboard, and fine for an agent
that would otherwise spend those seconds recovering from a wrong tap.
If it turns out to hurt, the answer is a faster way to read the
screen (a small helper on the phone), not skipping the check.

**THE LAST LOOK IS ON DISK.** `sparsh look` and a later `sparsh tap 7`
are two separate programs. The screen they agree on is saved per phone
under `~/.sparsh/phones/<serial>/last.xml`. That's also what lets an
agent, or a person, run one command at a time.

## Typing

`input text` on the phone takes one shell word. Sparsh quotes it (`'`
becomes `'\''`) and sends spaces as `%s`, which `input` turns back
into spaces. Tried live with `a b&c;d'e"f(g)h$i<j>k|l*m?n~o#p`: it all
arrived in the search field as typed.

What it can't do is type outside plain ASCII. `adb` has no way to send
é or नमस्ते. **REFUSED, NOT MANGLED**: those are turned down with a
sentence before anything reaches the phone. A keyboard app on the phone
can fix it later. (Later: [note 04](04-typing-other-languages.md).)

## What was deliberately not built

* **No coordinates in the interface.** A person debugging can read
  them in `look --json`, but no command takes an x and y. An agent
  that can only say numbers can only tap things that were on the list.
* **Nothing on the phone.** Faster screen reading and typing beyond
  ASCII both need a helper app installed on the phone. Not yet: the
  first version works on any phone with USB debugging on, and nothing
  is left behind on it.
* **No asking-first on the command line.** Sparsh does what it's told
  there. Holding a tap on "Send", "Pay" or "Delete" for a person's yes
  belongs with the agent's tools, where there's someone to ask
  ([note 02](02-held-for-a-yes.md)).
* **No iPhone.** Driving an iPhone needs WebDriverAgent, built and
  signed with Xcode, which only runs on a Mac. From Linux, the open
  tools can take an iPhone screenshot but can't tap.

## Live receipt

The Android 15 emulator (`Medium_Phone_API_35`), started headless with
`-no-window -no-snapshot-save`:

```
$ sparsh devices
emulator-5554  sdk_gphone64_x86_64  device

$ sparsh open settings | grep Network
6 item "Network & internet — Mobile, Wi‑Fi, hotspot" [tap]
$ sparsh tap 6 | grep -i airplane
6 item "Airplane mode" [tap, off]
$ sparsh tap 6 | grep -i airplane
4 item "Internet — Airplane mode is on" [tap]
6 item "Airplane mode" [tap, on]
$ sparsh tap 6 | grep -i airplane
6 item "Airplane mode" [tap, off]
```

Then the refusal: `look`, then Back pressed with `adb` directly (so
Sparsh didn't know), then `tap 6`:

```
sparsh: the screen changed since it was read: 6 (item "Airplane mode") is
not there any more. Nothing was done. The screen now:
App: com.android.settings
1 list "settings homepage container" [scroll]
2 image "Profile picture, double tap to open Google Account" [tap]
rc=3
```

And typing into a field, after clearing what was already there:

```
$ sparsh type "wifi" --into 2 --clear
App: com.google.android.settings.intelligence
1 button "Back" [tap]
2 field "wifi" [tap, type, focused]
3 button "Clear text" [tap]
```

A tap, wait included, took 5.3 seconds.

## What is not here yet

* ~~The agent's tools: `sparsh mcp`, with taps on Send / Pay / Buy /
  Delete and typing into password fields held for a person's yes.~~
  Done: [note 02](02-held-for-a-yes.md).
* ~~A trial: the same phone tasks on a local model reading this list
  and a cloud model reading screenshots.~~ The local half is done:
  thirteen tasks, `qwen3.8:latest` and `gemma4:26b` reading this list,
  12 of 13 each ([Yantra's note 120](https://github.com/kunwarmahen/yantra/blob/main/notes/120-thirteen-tasks-on-a-phone.md)). The cloud model reading
  screenshots is parked.
* ~~The phone over Wi-Fi (`adb pair`), so a container can reach it with
  no USB cable.~~ `sparsh pair`, `sparsh connect`, and `SPARSH_CONNECT`
  to find it again by itself (SETUP.md, B4); Sarathi's containers reach
  it that way; a real Nexus 6P too ([note 08](08-a-real-phone.md)). ~~Typing
  beyond ASCII~~: [note 04](04-typing-other-languages.md).
* ~~The trial repeated.~~ Three times each: 34 of 39 and 32 of 39
  ([Yantra's note 120](https://github.com/kunwarmahen/yantra/blob/main/notes/120-thirteen-tasks-on-a-phone.md)).
* An iPhone. Built: [note 03](03-an-iphone-through-a-mac.md), read
  through the same list.
