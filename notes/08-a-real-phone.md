# 08 — A real phone

Everything before this note ran on the Android 15 emulator. An emulator
has no lock, no keyboard it has to share the screen with, no Wi-Fi that
dozes, and settings laid out the way Google lays them out this year.
This note is the same work on a real phone: a Nexus 6P on Android 8.1,
seven years older than the emulator, on a USB cable and then over Wi-Fi,
driven by local models on Ollama.

It found five things the emulator never could. All five are fixed.

## A locked phone said it was Settings

**THE LOCK SCREEN SAYS IT IS ONE.** Asked to open Settings on a locked
phone, Sparsh printed what was in front:

```
App: com.android.systemui
1 text "Charged"
2 image "Voice Assist"
3 image "Unlock" [tap]
...
```

and nothing more. An agent reads that as Settings, or as a screen to
tap through. Now, when the screen comes from the system's own app and
the phone says it is locked, the list starts with one line:

```
App: com.android.systemui
(The phone is locked: this is its lock screen, not the app asked for. Ask its person to unlock it, then look again.)
```

It proved itself by accident. The phone locked itself mid-test (its
screen goes off after 30 seconds), and `gemma4:26b`, asked for the
Battery row, read that line and answered: *"The phone is currently
locked. Please unlock it so I can open the Settings and check the
Battery status for you."* The question is asked only on the system's
own screens (`com.android.systemui`, an iPhone's `com.apple.springboard`),
so an ordinary look costs nothing extra.

## The keyboard hid what the list showed

**A TARGET UNDER THE KEYBOARD GETS THE KEYBOARD PUT AWAY FIRST.**
Android's description of the screen leaves the keyboard out. A field
the keyboard covers is still listed, with its place on the screen, and
a tap there lands on a key. Adding a contact, `qwen3.8:latest` typed
into first name, last name and phone, and every word went into the
first name, with a stray letter from each tap that hit Gboard:

```
8 field "Kumar5550199umar" [tap, type, focused]
9 field "Last name" [tap, type]
12 field "+1" [tap, type]
```

The model saw the mess, tried again, and ran out of turns. Android does
say where its keyboard is (`dumpsys input_method` says whether it is up,
`dumpsys window` gives its window's touchable region). When a field has
the keyboard and the thing to tap lies under it, Sparsh presses back
once (with a keyboard up, back only closes it), reads the screen again,
finds the same thing there, and taps that. Asked only while a field has
the keyboard, so a plain tap pays nothing. The same task afterwards: 8
steps, done, Ravi Kumar saved with 555-0199.

## Do Not Disturb lived where no tap could reach

**THE PANELS AT THE TOP OPEN BY NAME.** On Android 8 Do Not Disturb's
switch is only in the quick-settings panel, pulled down from the top
edge. Settings has its preferences, not its switch. `qwen3.8:latest`
worked that out and said so, honestly: *"the actual on/off switch is in
the quick-settings shade, which opens only by a physical swipe from the
very top of a lit screen."* No key opens it, but Android's own
`cmd statusbar` does, so `press_key` takes two more names,
`quick_settings` and `notifications`. The panel reads like any screen:

```
12 switch "On (Do not disturb on, alarms only.)" [tap, on]
```

Afterwards: off in 6 steps, on again in 4. An iPhone has no such
panel to open from outside and says so, as for any key it lacks.

## A Wi-Fi link went stale while the screen was off

**A WI-FI PHONE THAT SAYS "CLOSED" IS RECONNECTED ONCE.** With the
phone locked and its screen off, its Wi-Fi dozes. adb still lists it as
a `device`, and the first command says `error: closed`. A schedule asked
whether the phone was free and got that, so the run was skipped as a
phone it couldn't reach:

```
skipped: the phone couldn't be reached (adb said: error: closed)
```

Run again a minute later, the same schedule reached it, found it
locked, and Dvara asked its person on Telegram. Unlocked in time, the
run worked the phone and answered *"Battery — 99% · charging"* (Dvara's
note 33). Now a phone
named by its Wi-Fi address that answers "closed" or "offline" is
disconnected, connected again, and asked once more. A phone on a cable
that says "closed" is reported as before: there is nothing to reconnect.

## A lock with no PIN is no one's to open

**ASLEEP, NOT LOCKED.** The 6P had only a swipe lock, and `sparsh state`
called it `locked`: Dvara asked its person on Telegram to unlock a phone
anything could have swiped. Android says whether its lock needs the
person (`secure=` in the window manager's keyguard, Android 8 to 15;
`deviceLocked=` in the trust service as well). A lock that doesn't is
now `asleep`, with `"pin": false` in `--json`; `sparsh wake` turns the
screen on and swipes it away (`wm dismiss-keyguard`, which Android
refuses for a lock with a PIN), and `open_app` does the same before it
opens an app. A PIN, pattern or password is `locked` as before, and
still asked about.

```
$ sparsh state --json
{"serial": "84B7N16128001616", "screen": "off", "locked": true, "pin": false, "state": "asleep"}
$ sparsh wake
84B7N16128001616: screen on (in_use)
```

Dvara's check before a scheduled run, unchanged, then woke the phone
and let the run go, and nobody was asked.

## Older Android over Wi-Fi

Android 10 and older have no *Wireless debugging* page to pair from.
Plugged in once, `adb tcpip 5555` makes the phone's adb listen on its
Wi-Fi address, and `sparsh connect 192.168.1.161:5555` reaches it with
the key already allowed over the cable (SETUP.md, B4). From there it is
the same road: `sarathi phone 192.168.1.161:5555` handed it to the
containers, and from inside Yantra's container `qwen3.8-64k:latest`
answered *"Battery — 98% - charging"* with no cable in the picture.

## What the phone did

| | on the Nexus 6P |
|---|---|
| read Settings, open apps, tap by number | as on the emulator |
| a text, with a no at Send | held at Send, nothing sent |
| é, नमस्ते, 👋 through ADBKeyBoard | typed, the phone's own keyboard back afterwards |
| over Wi-Fi, from a container | read the Battery row |
| the About page | reads fine; the emulator's ticks every second and can't be read |
| `sparsh state` | `in_use`, `locked`, `asleep` read right on 8.1 (`mDreamingLockscreen`) |
| a schedule on the locked phone | its person asked on Telegram; unlocked, the run went |

The trial's tasks, `qwen3.8:latest`, once each, on the fixed Sparsh
(Yantra's note 120 has the table): the switches, the Android version,
a web page's heading, an alarm and a contact were done. The phone's
name couldn't be: Android 8.1 has no device-name setting, so the model
renamed the phone's Quick Share name instead and said it was done.

## What the tests hold

`tests/test_rules.py`: the 6P's own lock screen, saved, says it is one
when the phone is locked, and nothing when it isn't or the screen isn't
the system's. `tests/test_phone.py`: a tap and a typed field under the
keyboard put it away first, and nothing is asked while no field has the
keyboard; the keyboard's place read from its own window; the panels
open by name, in order with keys; a stale Wi-Fi phone reconnected once,
a cable one never; a lock with no PIN asleep, swiped by `wake` and
`open_app`, a PIN still locked. 166 tests before, 177 after.

## Not here yet

* ~~**A screen that goes dark mid-task.**~~ A rename from Telegram stopped
  at the lock screen after the model's long pauses; the screen is now
  kept on while an agent works ([note 09](09-the-screen-kept-on.md)).

* A phone from another maker. A Samsung or Xiaomi lays out Settings
  its own way, and may describe its keyboard's window differently.
* The keyboard on an iPhone. WDA lists the keyboard's own keys, so
  nothing should be hidden, but it hasn't been tried.
