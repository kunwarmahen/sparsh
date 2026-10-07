# sparsh — an agent's hands on a real phone

"Turn on airplane mode." "Open Settings and find the Wi-Fi password
screen." "What's the newest message in my Messages app?"

Lots of what we do every day happens in phone apps, and many of those
apps have no website and no way in for a program. **Sparsh** lets an
agent use an Android phone the way you do: it sees what's on the
screen, taps, types, scrolls, presses Back, and opens apps. It works
with a real phone over USB, or with the Android emulator on your
computer. An iPhone works too, once a Mac has signed the small app
that lets it be driven (see [An iPhone](#an-iphone)).

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

## An iPhone

An iPhone can be driven too, with one difference: it needs a Mac once.
Apple doesn't let a computer work an iPhone the way `adb` works an
Android phone. The way in is
[WebDriverAgent](https://github.com/appium/WebDriverAgent) (WDA), a
small app that runs on the iPhone and takes taps over the network. It
has to be built and signed with Xcode, and Xcode only runs on a Mac.
After that, everything happens from Linux.

**On the Mac (once; again every 7 days with a free Apple ID).** Install
Xcode, open it, and add your Apple ID under *Xcode → Settings →
Accounts*. Plug the iPhone into the Mac once and tap *Trust*. Then,
at the Mac or over SSH from Linux (turn on *System Settings → General
→ Sharing → Remote Login* first):

```
scp scripts/build-wda-on-mac.sh mac.local:
ssh -t mac.local ./build-wda-on-mac.sh
```

It makes `~/sparsh-wda/WDA.ipa` on the Mac and prints the `PREFIX` it
used. Over SSH it asks for the Mac user's password to unlock the
keychain, which signing needs.

**On Linux.** Install [go-ios](https://github.com/danielpaulus/go-ios)
(`npm install -g go-ios`) and `usbmuxd`, plug the iPhone in, and:

```
scp mac.local:sparsh-wda/WDA.ipa .
PREFIX=com.you.sparsh scripts/start-wda-from-linux.sh WDA.ipa
```

The first time, the iPhone asks you to trust the developer (*Settings
→ General → VPN & Device Management*) and to turn on *Developer Mode*
(*Settings → Privacy & Security*). Leave the script running. In
another terminal:

```
$ sparsh look --serial http://127.0.0.1:8100
App: com.apple.Preferences
1 text "Settings"
2 field "Search" [type]
3 list [scroll]
4 switch "Airplane Mode" [tap, off]
5 item "Wi-Fi (HomeNet)" [tap]
```

or set `SPARSH_WDA=http://127.0.0.1:8100` and leave `--serial` off.
The phone's Wi-Fi address works in place of `127.0.0.1` from any
machine on the same network.

If you'd rather keep the iPhone plugged into the Mac,
`./build-wda-on-mac.sh --run` builds WDA and runs it from there, and
Sparsh reaches it over Wi-Fi.

What's different on an iPhone ([notes/03](notes/03-an-iphone-through-a-mac.md)):
`back` is the swipe in from the left edge, since there's no Back key.
`recent`, `search` and the arrow keys don't exist. `sparsh apps` lists
Apple's own apps plus any you name in `$SPARSH_IOS_APPS`, because WDA
can't list what's installed. `open settings`, `open messages` and the
other Apple apps work by name.

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
sparsh devices                      phones adb can see, and the iPhone at $SPARSH_WDA
sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
sparsh look --peek                  the same, leaving an agent's numbers as they were
sparsh tap 7 [--long]               tap 7 from the last look (--long: press and hold)
sparsh type "hello" [--into 7] [--clear] [--enter]
sparsh scroll down [--on 5]         down = show what is further down
sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
sparsh open settings                open an app by name or package
sparsh apps [FILTER]                apps that can be opened
sparsh mcp                          the agent's tools (MCP), held by your rules
sparsh status [--json]              phones, rules, and how to start the tools
```

Every command that does something prints the screen it led to. Every
command takes `--serial` when more than one phone is attached (or set
`ANDROID_SERIAL`), and `--json` for a script. For an iPhone, the serial
is WebDriverAgent's address, like `http://127.0.0.1:8100`.

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

## Letting an agent use it

`sparsh mcp` gives an agent the same hands, as an MCP server: `look`,
`tap`, `type_text`, `scroll`, `press_key`, `open_app` and `list_apps`.
Every one of them hands back the screen it led to, so the agent always
has the next numbers in front of it.

**[Yantra](https://github.com/kunwarmahen/yantra) finds it by itself.**
With `sparsh` on your `PATH` and a phone attached, a Yantra session
starts the tools and says so in one line:

```
sparsh: 9 tool(s); phone emulator-5554 (sdk_gphone64_x86_64) -- via /home/you/sparsh/.venv/bin/sparsh
```

Then ask for something on the phone in plain words: "turn on airplane
mode", "text 5554 saying running late". `YANTRA_SPARSH=/path/to/sparsh`
names it when it isn't on `PATH`.

**Other harnesses** (Claude Code, Cursor, …) take it like any MCP server:

```json
{"mcpServers": {"sparsh": {"command": "/home/you/sparsh/.venv/bin/sparsh", "args": ["mcp"]}}}
```

They'll ask you before each tap unless you allow the tools. Allow them
all except `confirm` (below), and you get what Yantra does.

### What it asks you first

Most of working a phone is harmless: open Settings, tap a row, scroll,
go back. Being asked about every tap would mean not reading the
questions by the tenth one. So an agent's steps run by themselves, and
Sparsh **holds** the few that can't be taken back:

* a tap on something whose words say it acts: **Send, Pay, Buy, Order,
  Place, Book, Confirm, Submit, Post, Share, Reply, Call, Delete,
  Remove, Install, Uninstall, Allow, Accept, Sign out, Block**, and a few
  more. These are matched as whole words, so "Place order" is held and
  the "Orders" tab is not. "Send to Asha" (choosing who a message goes
  to) isn't held; the Send button after it is;
* typing into a **password** field;
* **Enter**, while the screen shows something that would be held: in a
  chat app with "Enter to send" on, Enter is the Send button.

A held step isn't done. The agent is told so, and asks you through its
`confirm` tool. That is the one tool Yantra asks about every time, even
when you've told it to stop asking (`--yolo`). The question says what
will happen, with the screen it will happen on:

```
╭─ approve mcp__sparsh__confirm()? ────────────────────────────────────────────╮
│ Do this on the phone?                                                        │
│ On the phone emulator-5554: tap image "Send SMS" in                          │
│ com.google.android.apps.messaging -- held because it says "send".            │
│ The screen when it was asked for:                                            │
│ App: com.google.android.apps.messaging                                       │
│ 1 text "Message list"                                                        │
│ 2 item "7:59 AM — Texting with 5554 (SMS/MMS) ..."                           │
│ 3 image "Expand attachment buttons"                                          │
│ 4 field "running late, be there at 7"                                        │
│ 5 image "Explore emoji"                                                      │
│ 6 image "Send SMS"                                                           │
│ ...                                                                          │
╰──────────────────────────────────────────────────────────────────────────────╯
run it? [y/n/e/s] (n):
```

If the screen has changed by the time you say yes, nothing is tapped.
A held step waits 10 minutes, then lapses.

### Your rules

`~/.sparsh/rules.toml` is yours. No tool can change it:

```toml
ask = ["archive", "unfollow"]      # more words that need a yes
dont_ask = ["share"]               # built-in words not to ask about
never = ["com.chase.*", "*bank*"]  # apps the agent may not use at all
```

An app on the `never` list can't be opened, and if the agent ends up in
it anyway (a notification, a link), nothing on its screen is shown.
Back and Home always work, so the agent can leave. `sparsh status`
prints the rules in force.

The `sparsh` commands you type yourself are never held: they're your
own hands.

**Watching an agent work.** Sparsh remembers each look as the screen an
agent's numbers refer to. To see the phone while an agent is using it,
use `sparsh look --peek` (with `--shot` for a picture): it reads the
screen and leaves that memory alone. A plain `sparsh look` would
renumber the screen under the agent. Yantra's phone panel peeks this
way.

### Settings

| | |
|---|---|
| `ANDROID_SERIAL` | which phone, when more than one is attached (or `--serial`) |
| `SPARSH_STATE` | where the last screen of each phone and `rules.toml` live (default `~/.sparsh`; or `--state`) |
| `SPARSH_RULES` | a rules file somewhere else |
| `SPARSH_ADB` | the `adb` to use, when it isn't on `PATH` or in `~/Android/Sdk` |
| `SPARSH_WDA` | an iPhone's WebDriverAgent address (`http://127.0.0.1:8100`), used when no `--serial` is given |
| `SPARSH_IOS_APPS` | more iPhone apps for `sparsh apps` and `open`, as bundle ids separated by commas |

## Not here yet

* The phone over Wi-Fi instead of a cable, and typing beyond plain
  ASCII.
* A phone for runs nobody is watching (a schedule): Yantra gives those
  no phone at all for now.
* ~~iPhones.~~ Built: [notes/03](notes/03-an-iphone-through-a-mac.md),
  with a Mac needed once to sign WebDriverAgent. Not yet run on a real
  iPhone.

## How it's built

```
src/sparsh/
├── screen.py   the phone's description of its screen -> the numbered list;
│               a row takes its words (and its switch) from inside
│               (notes/01)
├── device.py   the phone itself, through adb: dump, screenshot, tap,
│               swipe, type, keys, open an app. Nothing installed on it
├── iphone.py   an iPhone, through WebDriverAgent over HTTP; its screen
│               rewritten in Android's words so one reader serves both
│               (notes/03)
├── phone.py    numbers in, taps out: the last look is kept, and a number
│               is checked against the screen now before anything is done
│               (notes/01)
├── rules.py    what waits for a yes (words on a tap, password fields) and
│               which apps are off limits; ~/.sparsh/rules.toml (notes/02)
├── mcp.py      `sparsh mcp`: the agent's tools, a hand-written MCP server;
│               reads, acts and `confirm` (notes/02)
├── status.py   `sparsh status --json` (sparsh.status.v1): what a harness
│               reads to find the phone, the rules and each tool's kind
├── fake.py     a phone made of saved screens, for tests
└── cli.py      `sparsh`
tests/screens/  real screens from the Android 15 emulator; ios/ holds
                screens written in WDA's shape
scripts/        build WDA on a Mac; install and start it from Linux
```

Why it is shaped this way: [notes/01](notes/01-a-list-not-a-picture.md)
(the list, and the check before a tap) and
[notes/02](notes/02-held-for-a-yes.md) (what an agent may do by itself).

## Licence

Apache-2.0.
