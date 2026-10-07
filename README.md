# sparsh — an agent's hands on a real phone

"Turn on airplane mode." "Open Settings and find the Wi-Fi password
screen." "What's the newest message in my Messages app?"

Lots of what we do every day happens in phone apps, and many of those
apps have no website and no way in for a program. **Sparsh** lets an
agent use an Android phone the way you do: it sees what's on the
screen, taps, types, scrolls, presses Back, and opens apps. It works
with a real phone over USB, or with the Android emulator on your
computer. An iPhone works too, once a Mac has signed the small app
that lets it be driven ([SETUP.md](SETUP.md)).

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
model that can use it or for you. And where the list has nothing to
give, an agent can be handed the picture too (`sparsh mcp --shots`,
below).

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

**[SETUP.md](SETUP.md) walks through all three, step by step:** the
Android emulator (a pretend phone on your computer, nothing at risk),
a real Android phone, and an iPhone.

In short:

* **Android** (phone or emulator) needs only `adb`, Android's own small
  program (`sudo apt install adb`), and *USB debugging* turned on in
  the phone's developer options. Nothing is installed on the phone.
* **An iPhone** needs a Mac once. The way in is
  [WebDriverAgent](https://github.com/appium/WebDriverAgent), a small
  app on the iPhone that takes taps over the network. It has to be
  signed with Xcode, which only runs on a Mac.
  `scripts/build-wda-on-mac.sh` does that, over `ssh` if you like, and
  `scripts/start-wda-from-linux.sh` installs and starts it from Linux.
  With a free Apple ID the signature lasts 7 days; `sparsh wda` reads
  the date from the app, and Sparsh says when two days are left. Not
  yet run on a real iPhone
  ([notes/03](notes/03-an-iphone-through-a-mac.md)).

Either way, check it's there:

```
$ sparsh devices
emulator-5554  sdk_gphone64_x86_64  device
```

An iPhone is named by WebDriverAgent's address
(`SPARSH_WDA=http://127.0.0.1:8100`, or `--serial`). On an iPhone,
`back` is the swipe in from the left edge, and `sparsh apps` lists
Apple's own apps plus any in `$SPARSH_IOS_APPS`, because an iPhone
won't say what's installed.

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
sparsh devices                      phones adb can see, and the iPhone at $SPARSH_WDA
sparsh look [--shot FILE] [--json]  the screen, one numbered line per thing
sparsh look --peek                  the same, leaving an agent's numbers as they were
sparsh tap 7 [--long]               tap 7 from the last look (--long: press and hold)
sparsh type "hello" [--into 7] [--clear] [--enter]
sparsh scroll down [--on 5]         down = show what is further down
sparsh key back [home enter ...]    back, home, enter, recent, delete, tab, ...
sparsh open settings                open an app by name or package
sparsh apps [FILTER]                apps that can be opened
sparsh log [-n 20] [--json]         what was done on the phone, by the agent and by you
sparsh mcp                          the agent's tools (MCP), held by your rules
sparsh status [--json]              phones, rules, and how to start the tools
sparsh wda [WDA.ipa]                when the iPhone's WebDriverAgent signature runs out
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

**Typing.** Plain letters, digits and punctuation work on every phone.
For letters outside plain ASCII (é, नमस्ते, emoji), Android needs the small
ADBKeyBoard app, which you install once ([SETUP.md, Part
G](SETUP.md#part-g--typing-other-languages-optional-android)). Sparsh
switches to it just for that text and then back to your own keyboard.
Without it, such text is refused with a sentence rather than typed
wrong. An iPhone types them as they are.

**Exit codes.** `0` done, `1` something went wrong (one sentence on
stderr), `3` the screen changed since the last look and nothing was
done.

## When the phone can't describe its screen

* **Something that never stops changing:** a video, an animation, or a
  clock ticking every second (Settings' *About phone* page counts its
  "Up time"). The phone waits for the screen to be still before
  describing it, and gives up on one that never is. Sparsh tries twice
  and then says so, names the app in front, and tells an agent to press
  Back and find what it needs another way. You can pause the video, or
  use `look --shot`.
  An app that reopens on such a page (apps reopen where they were left)
  is backed out of it: `open` presses back up to twice and says so above
  the list.
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

### A picture, only where the list has nothing

Some screens give the list nothing: a page that never goes still, or an
app drawn as one picture. Started as `sparsh mcp --shots`, a tool whose
screen comes back empty or unreadable also returns a **screenshot** of
it, as an image the model can look at:

```
App: com.android.settings
(this screen can't be read as a list: the screen keeps changing (...). Press back to leave this page, ...)
(A screenshot of this screen is attached to this result: you can already see it, no tool is needed. Only numbered things can be tapped, ...)
```

Only then. A screen the list can read never comes with a picture, an
app on your `never` list never does, and nor does one whose name can't
be found while you keep the agent out of some. It's **off** unless
whoever starts the server turns it on, because a phone's screen is your
messages, names and codes, and the harness is the one that knows
whether the model can see and whether it runs in the cloud. Yantra
turns it on for a local model that can see, and for a cloud model only
when you say so (`YANTRA_PHONE_SHOTS=on`).

The picture is for reading. Nothing taps by position: what isn't on the
list is reached another way (back, a scroll, a search). On the Android
emulator, `gemma4:26b` read the IMEI off Settings' About page this way,
a page the list can't read at all. Renaming the phone, which needs a tap
on that page, stays out of reach
([notes/05](notes/05-a-picture-where-the-list-has-nothing.md)).

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

**What was done.** Every step taken on the phone is written down: by the
agent through its tools, or by you on the command line. That includes
the ones that were held, refused, or stopped because the screen had moved.
`sparsh log` shows them:

```
10:15:00 you   press_key keys=["home"] -> done (com.google.android.apps.nexuslauncher)
10:15:03 you   open_app name="messages" -> done (com.google.android.apps.messaging)
10:15:07 agent press_key keys=["enter"] -> held (h39b833: enter could do what item "Send SMS — SMS" does (it says "send"))
10:15:07 agent open_app name="whatsapp" -> not_done (no app matches 'whatsapp'. ...)
```

`--json` adds what each step was aimed at and the screen it led to.
Text typed into a password field is `(hidden)` there too. The newest 500
steps per phone are kept, in `~/.sparsh/phones/<serial>/actions.jsonl`.
Looking isn't a step, so it isn't logged.

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

* The phone over Wi-Fi instead of a cable.
* ~~Typing beyond plain ASCII.~~ Built through ADBKeyBoard (SETUP.md,
  Part G); run on the emulator, not yet on a real phone.
* A phone for runs nobody is watching (a schedule): Yantra gives those
  no phone at all for now.
* ~~Screenshots through the agent's tools.~~ Built: `sparsh mcp --shots`
  ([notes/05](notes/05-a-picture-where-the-list-has-nothing.md)), for
  reading only.
* Acting on a screen the list can't read (renaming the phone on the
  About page). The picture shows it; nothing taps by position.
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
├── log.py      every step on the phone, by the agent or by you, however it
│               ended; `sparsh log` (notes/02)
├── rules.py    what waits for a yes (words on a tap, password fields) and
│               which apps are off limits; ~/.sparsh/rules.toml (notes/02)
├── mcp.py      `sparsh mcp`: the agent's tools, a hand-written MCP server;
│               reads, acts and `confirm` (notes/02); `--shots`, a picture
│               where the list has nothing (notes/05)
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
