# 12 — A real iPhone

*[Note 03](03-an-iphone-through-a-mac.md) built the iPhone side against
screens written by hand and a stand-in WebDriverAgent, and said the
first real run would bring a correction or two. It brought five, all
in how a screen is read, and one in how a finger moves.*

## The road, end to end

An iPhone 17 on iOS 26.6.2, a free Apple ID, a Mac reached over `ssh`
from Linux. WebDriverAgent was built and signed on the Mac with
`scripts/build-wda-on-mac.sh`, copied to Linux, installed and started
there with go-ios through `scripts/start-wda-from-linux.sh`. After the
build the Mac played no part.

The build hit three walls before it worked, and each is now in SETUP's
table (Part C, C4):

* *"Your team has no devices from which to generate a provisioning
  profile."* Tapping Trust on the phone doesn't add it to the Apple
  team. Picking it as the device to build for, in any Xcode project,
  does.
* *"errSecInternalComponent"* on CodeSign, with the keychain already
  unlocked. macOS wanted someone at the Mac to click Allow for the
  signing key; over `ssh` nobody is there. `security
  set-key-partition-list` grants it once.
* Neither of those was visible at first: the script filtered Xcode's
  output for lines starting with `error`, and Xcode starts its error
  lines with a path. Worse, a failed build went on to pack the app an
  earlier run had left. The script now keeps the whole log, shows every
  `error:` line, and stops on a failed build.

On Linux, the first `start-wda` installed the app and then failed with
*"could not get pid from response"*: the phone won't launch an app from
a developer it hasn't been told to trust (Settings → General → VPN &
Device Management). After that it started, and:

```
$ sparsh look --serial http://127.0.0.1:8100
App: com.apple.springboard
1 item "Google Calendar (Widget, Stack)" [tap]
2 list [scroll]
3 text "Google Calendar"
4 text "Sunday, September 27"
...
38 text "Saturday, October 31"
39 button [tap]
40 text "Task, 4 pending tasks"
...
45 text "Horizontal scroll bar, 1 page (0%)"
46 text "Horizontal scroll bar, 1 page (0%)"
47 item "Coinbase (Widget)" [tap]
...
55 text "Oct 17, 2026 at 00:37 to Oct 17, 2026 at 00:44, coreSleep, coreSleep (7 min)"
...
104 item "WebDriverAgentRunner-Runner" [tap]
105 text "Page 4 of 4"
106 text "Page 4 of 4"
107 text "Dock"
...
116 text "100% battery power (Charging)"
```

It read. It also read 116 lines for a home screen with eleven things on
it. A locked phone, a minute later, was said as one:

```
App: com.apple.springboard
(The phone is locked: this is its lock screen, not the app asked for. Ask its person to unlock it, then look again.)
```

## What the hand-written screens didn't have

**A widget's insides are in the widget's own coordinates.** Line 39 is a
button inside the Calendar widget. WDA places it at (193, 11): measured
from the widget's corner, not the screen's. As a screen place that is
the status bar. Every line inside a widget was a tap that would land
somewhere else. So a widget is one line, which opens its app, and
nothing inside it gets one. That also took the dates, the sleep
entries and most of the scroll bars.

**Scroll bars are boxes with names.** iOS lists each scroll indicator
as an adjustable box called *"Vertical scroll bar, 4 pages"*, often
twice, sometimes marked visible. It is a picture of where a list is,
not a thing to act on. It gets no line. The name is matched in English,
the only words it has.

**A box and the dots inside it both say "Page 4 of 4".** A line that only
repeats what the node around it already said is dropped.

The home screen after:

```
App: com.apple.springboard
1 item "Google Calendar (Widget, Stack)" [tap]
2 item "Coinbase (Widget)" [tap]
3 item "Sleep (Widget)" [tap]
4 item "Home MP3 Hub - YouTube Downloader" [tap]
5 item "ntfy" [tap]
6 item "Find My (Widget)" [tap]
7 item "Amtrak" [tap]
8 item "WebDriverAgentRunner-Runner" [tap]
9 text "Page 4 of 4"
10 text "Dock"
11 item "Phone" [tap]
...
19 text "100% battery power (Charging)"
```

Then `sparsh tap` on Settings, which opened it, and showed that iOS 26
builds its rows in a way note 03 didn't guess:

```
2 item [tap]
3 button "Asha Rao, Apple Account, iCloud, and more" [tap]
4 item [tap]
5 button "Family" [tap]
6 switch "Airplane Mode" [tap, off]
7 switch [tap, off]
8 item [tap]
9 button "Wi-Fi, HomeNet" [tap]
```

**A row that is only a frame steps aside.** Each row is a Cell with no
words, holding a Button as big as itself that has them. Both are
tappable, so each row was an unnamed item and then a button. When a
Cell has no words of its own and holds one tappable thing about its
own size, that thing is the row. A Cell with words, or with a smaller
button inside (an info button), keeps its line.

**A switch inside a switch is its knob.** The row-sized Switch called
"Airplane Mode" holds the small unnamed one that slides. One switch, one
line: the knob's place, under the row's name. Note 03 already chose the
knob over the row on purpose, because on an iPhone the knob is what a
tap flips.

**What VoiceOver hears as one is one.** In General each row is a Cell
called "About", marked accessible, holding a Button also called
"About" and a greyed-out "chevron" arrow, both marked not accessible.
Three lines per row. The `accessible` flag is iOS's own answer to
which of these is the thing a person means: it's what VoiceOver reads
out. Tappable things inside an accessible tappable one are its parts.

**Twins are one.** The search field's microphone is listed as two
Buttons side by side, with the same name in the same place. The second
is left out.

Settings and General after, live:

```
App: com.apple.Preferences
1 text "Settings"
2 button "Asha Rao, Apple Account, iCloud, and more" [tap]
3 button "Family" [tap]
4 switch "Airplane Mode" [tap, off]
5 button "Wi-Fi, HomeNet" [tap]
...
11 button "General" [tap]
12 button "Accessibility" [tap]
13 field "Search" [type]
14 button "Dictate" [tap]

$ sparsh tap 11
App: com.apple.Preferences
1 button "Settings" [tap]
2 text "General"
3 list [scroll]
4 item "General — Manage your overall setup and preferences for iPhone, ..." [tap]
5 item "About" [tap]
6 item "Software Update" [tap]
...
```

(The person's name and Wi-Fi network are replaced here and in the test
screens.)

## Back, without resting first

`sparsh tap 5` opened About. `sparsh key back` did nothing. Back on an
iPhone is the swipe in from the left edge, and Sparsh sent it as one
finger that rested 50 ms, then moved. Sent again with no rest, it went
back at once. iOS 26 takes a finger that rests first as a press and
drag, which is not the back gesture. `back` now moves without resting.
A scroll keeps its rest, since a scroll doesn't mind.

## The screens are real now

`tests/screens/ios` keeps the hand-written `settings` and `login`, and
adds three captured from this phone: `home`, `settings26`, `general26`.
The personal words in them (calendar entries, sleep times, a street,
amounts, the person's name, the network) are replaced, and the hidden
home-screen pages (every folder and app name) are taken out. Seven
tests read them, and all seven fail on the reader as note 03 left it.

233 tests pass (227 before).

## What is not here yet

* An agent's task done on the iPhone through Yantra, local model first
  (SETUP Part F's prompts).
* Typing, scrolling a long list, and a held step's yes, on the real
  phone.
* Scroll bars named in other languages: only the English name is
  matched.
* The iPhone over Wi-Fi instead of the cable's forwarded port.
