# sparsh — an agent's hands on a real phone

"Turn on airplane mode." "Open Settings and find the Wi-Fi password
screen." "What's the newest message in my Messages app?"

Lots of what we do every day happens in phone apps, and many of those
apps have no website and no way in for a program. **Sparsh** lets an
agent use an Android phone the way you do: it sees what's on the
screen, taps, types, scrolls, presses Back, and opens apps. It works
with a real phone over USB, or with the Android emulator on your
computer.

## The name

**sparsh** — स्पर्श (Sanskrit *sparśa*; said roughly *spursh*).

In Hindi, *sparsh* means **touch**. A phone is the one computer we
work only by touching, and touch is all Sparsh does: it doesn't
decide anything, it carries out a tap someone else chose, and only
when that thing is still where it was.

## What it looks like

```
$ sparsh open settings
App: com.android.settings
1 list "settings homepage container" [scroll]
2 image "Profile picture, double tap to open Google Account" [tap]
3 text "Settings"
4 item "Search settings" [tap]
5 list "main content scrollable container" [scroll]
6 item "Network & internet — Mobile, Wi‑Fi, hotspot" [tap]
7 item "Connected devices — Bluetooth, pairing" [tap]
...

$ sparsh tap 6
App: com.android.settings
...
6 item "Airplane mode" [tap, off]
...

$ sparsh tap 6
...
4 item "Internet — Airplane mode is on" [tap]
6 item "Airplane mode" [tap, on]
```

Every line is one thing on the screen, with a number. You (or an agent)
answer with a number. Sparsh turns it back into a tap in the middle of
that thing, then shows the screen it led to.

## Why a list and not a picture

Most tools that let an AI work a phone send it a **screenshot** and ask
where to tap. That needs a model that can see pictures, and seeing
pictures well is still the hardest thing for a model running on your
own computer.

Android already describes every screen in words. It's what the phone's
screen reader (TalkBack) reads aloud to people who can't see the
screen. Sparsh reads that description and folds it into the list
above. A small local model like `qwen3.8:latest` on Ollama reads lines
of text well, so it can work a phone without seeing it. A screenshot is
still there when you want one (`sparsh look --shot screen.png`), for a
model that can use it or for you.

## It never taps something that moved

Phones change on their own: a page finishes loading, a pop-up arrives,
a list shifts. If an agent read "6 is Airplane mode" and the screen
changed before it tapped, a blind tap would land on something else.

So before every tap, Sparsh reads the screen again and checks that 6 is
**the same thing in the same place**. If it isn't, nothing is tapped,
and you get the screen as it is now:

```
$ sparsh tap 6
sparsh: the screen changed since it was read: 6 (item "Airplane mode") is
not there any more. Nothing was done. The screen now:
App: com.android.settings
1 list "settings homepage container" [scroll]
...
$ echo $?
3
```

If the thing only moved (the same item, now numbered 7 because
something appeared above it), Sparsh still finds it, as long as it's
still in the same place on the screen.

## Getting a phone ready

You need `adb`, Android's small program for talking to phones:

```
sudo apt install adb          # Debian / Ubuntu
sudo dnf install android-tools  # Fedora
```

Then pick one of these two.

**The emulator (no phone needed).** Install
[Android Studio](https://developer.android.com/studio), open
*Device Manager*, and create a phone (any recent one; we test with a
"Medium Phone" on Android 15). You can then start it without Android
Studio:

```
~/Android/Sdk/emulator/emulator -list-avds
~/Android/Sdk/emulator/emulator -avd Medium_Phone_API_35 -no-snapshot-save
```

Add `-no-window` to run it with no window at all. `-no-snapshot-save`
means anything the agent changes is thrown away when the emulator
stops.

**A real phone.** On the phone: *Settings → About phone*, tap *Build
number* seven times to unlock *Developer options*, then turn on *USB
debugging* in there. Plug the phone in and accept the question it asks
on its screen.

Either way, check it's there:

```
$ sparsh devices
emulator-5554  sdk_gphone64_x86_64  device
```

If it says `unauthorized`, unlock the phone and accept the USB
debugging question.

> **What an agent can see.** Anything on the phone's screen can be read:
> messages, emails, names, codes. While you're trying this out, use the
> emulator or a spare phone, not the phone you live on.

## Install

```
git clone https://github.com/kunwarmahen/sparsh
cd sparsh
uv sync
uv run sparsh --help
```

Sparsh needs Python 3.12 or newer and has no other dependencies.

## Commands

```
sparsh devices                      phones adb can see
sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
sparsh tap 7 [--long]               tap 7 from the last look (--long: press and hold)
sparsh type "hello" [--into 7] [--clear] [--enter]
sparsh scroll down [--on 5]         down = show what is further down
sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
sparsh open settings                open an app by name or package
sparsh apps [FILTER]                apps that can be opened
```

Every command that does something prints the screen it led to. Every
command takes `--serial` when more than one phone is attached (or set
`ANDROID_SERIAL`), and `--json` for a script.

What the end of each line means:

| | |
|---|---|
| `[tap]` | can be tapped |
| `[long-press]` | only does something when held |
| `[type]` | a field you can type into (`type --into N`) |
| `[scroll]` | a list that scrolls (`scroll down --on N`) |
| `[on]` / `[off]` | a switch, and which way it is now |
| `[focused]` | the field the keyboard is typing into |
| `[password]` | a password field; what's in it is never shown |
| `[disabled]` | greyed out on the phone; tapping it is refused |

An empty field shows its hint as its text (`field "Search settings"`):
Android reports it that way. `--clear` empties a field before typing.

**Typing.** Plain letters, digits and punctuation work. Letters outside
plain ASCII (é, नमस्ते, emoji) are refused with a sentence rather than
typed wrong, because `adb` can't type them.

**Exit codes.** `0` done, `1` something went wrong (one sentence on
stderr), `3` the screen changed since the last look and nothing was
done.

## When the phone can't describe its screen

* **A video or animation playing.** The phone waits for the screen to
  be still before describing it, and gives up on one that keeps
  moving. Sparsh tries twice and then says so. Pause the video, or use
  `look --shot`.
* **Apps that don't describe themselves.** Some games, and some apps
  built with tools that skip the accessibility description, show up as
  a few unlabelled lines. A screenshot is the way in there.
* **Banking and password screens** often come back black in
  screenshots. The phone does that on purpose.

## Not here yet

* An agent's own tools for this (an MCP server, so Yantra, Claude Code
  or any other harness can use it), with a yes from you before
  anything that sends, pays, buys or deletes.
* The phone over Wi-Fi instead of a cable, and typing beyond plain
  ASCII.
* iPhones. Driving an iPhone needs a Mac (Apple's tools only run there),
  and Sparsh runs on Linux.

## How it's built

```
src/sparsh/
├── screen.py   the phone's description of its screen -> the numbered list;
│               a row takes its words (and its switch) from inside
│               (notes/01)
├── device.py   the phone itself, through adb: dump, screenshot, tap,
│               swipe, type, keys, open an app. Nothing installed on it
├── phone.py    numbers in, taps out: the last look is kept, and a number
│               is checked against the screen now before anything is done
│               (notes/01)
├── fake.py     a phone made of saved screens, for tests
└── cli.py      `sparsh`
tests/screens/  real screens from the Android 15 emulator
```

Why it is shaped this way: [notes/01](notes/01-a-list-not-a-picture.md).

## Licence

Apache-2.0.
