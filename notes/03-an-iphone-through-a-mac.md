# 03 — An iPhone, through a Mac, once

[Note 01](01-a-list-not-a-picture.md) read an Android phone's screen
as a numbered list, and [note 02](02-held-for-a-yes.md) decided which
of an agent's steps wait for a person. Both assumed `adb`: a program
that comes with Android's tools and can work a phone with nothing
installed on it. An iPhone has nothing like it. This note is about how
much of Sparsh survives the move, and the answer we wanted was all of
it.

## The one thing only a Mac can do

Apple's way for a computer to drive an iPhone is XCUITest, the
framework its own UI tests use. Appium's
[WebDriverAgent](https://github.com/appium/WebDriverAgent) (WDA) wraps
it in a small app that runs on the phone and answers HTTP on port 8100:
`GET /source` for the screen, W3C pointer actions for a finger,
`/wda/keys` for the keyboard. Anything that can send HTTP can drive the
phone.

Getting WDA *onto* the phone is the hard part. It has to be built and
signed with Xcode, and Xcode only runs on macOS. With a free Apple ID
the signature lasts seven days; with a paid developer account, a year.

**THE MAC SIGNS; LINUX DRIVES.** Sparsh doesn't ask for a Mac to sit
between the agent and the phone. `scripts/build-wda-on-mac.sh` builds
and signs WDA once and packs it as `WDA.ipa`. It runs at the Mac's
keyboard or over SSH, and unlocks the login keychain first, since
signing over SSH otherwise fails. On Linux,
[go-ios](https://github.com/danielpaulus/go-ios) installs the `.ipa`
over USB and starts it (`scripts/start-wda-from-linux.sh`), and from
then on the Mac can be closed until the signature runs out. A Mac
borrowed for a weekly rebuild is enough.

The other option is kept too: `build-wda-on-mac.sh --run` runs WDA from
the Mac with the phone plugged in there, and Sparsh reaches it over
Wi-Fi. That's simpler on day one, but the Mac has to stay awake.

## One reader, two phones

The numbered list is where the care went in note 01. A Settings row
takes its words from inside it, a switch that can't be tapped by
itself joins its row, and a box with no size gets no line. A second
reader written for XCUITest's tree would have to win every one of
those arguments again, and would drift from the first.

So `iphone.py` doesn't read the iPhone's screen. **IT TRANSLATES.**
`as_android()` rewrites WDA's `/source` into the XML `uiautomator dump`
prints, and `screen.read()` reads it the way it reads Android:

| XCUITest says | Android's word for it |
|---|---|
| `Cell`, `Button`, `Link`, `Icon` | clickable |
| `Table`, `CollectionView`, `ScrollView` | scrollable |
| `TextField`, `SearchField`, `TextView` | `EditText` (a field) |
| `SecureTextField` | `EditText`, password |
| `Switch` with value `1` | checkable, checked |
| `visible="false"` | no node (what's inside is still read) |
| `Keyboard` | left out, as adb's dump leaves out the keyboard |

The list for Settings, written by hand in WDA's shape (`tests/screens/ios`):

```
App: com.apple.Preferences
1 text "Settings"
2 field "Search" [type]
3 list [scroll]
4 switch "Airplane Mode" [tap, off]
5 item "Wi-Fi (HomeNet)" [tap]
6 item "Bluetooth — On" [tap]
```

The tap check (note 01), the holds and rules (note 02), the MCP server
and `look --peek` all run on top without being changed. The same
`Phone` class drives both kinds of phone.

## Where the translation had to think

Two places where translating word for word would have been wrong.

**A ROW WITH A SWITCH IS THE SWITCH.** On Android, tapping the
Airplane mode row flips it, so the switch joins the row's line and a
tap goes to the middle of the row. On an iPhone the row does nothing;
only the switch flips. Translated word for word, the row would get a
line, a tap on it would land in empty space, and the screen after
would show nothing changed. So a cell that holds a switch steps aside:
the switch takes the line, under the row's words, and the tap lands on
the switch.

**A ROW'S WORDS ARE SAID ONCE.** An iPhone row often carries its own
label ("Wi-Fi") and value ("HomeNet"), *and* holds the text nodes
those came from. Android's reader only takes words from inside when the
row has none of its own, so it would give the row a line and then each
text node another line. Inside anything tappable that already has its
words, plain text and images are left blank. The row's value goes
where Android puts a description: `"Wi-Fi (HomeNet)"`.

Coordinates stay in the iPhone's points throughout. `/source` gives
points, and the pointer actions take points, so nothing needs scaling.
Screenshots are in pixels, but nothing taps from a screenshot.

## What an iPhone hasn't got

* **No Back key.** `back` is the swipe in from the left edge, which
  most apps built on Apple's navigation take as back. A sheet or a
  full-screen video may not.
* **`end` does nothing.** On Android, `--clear` moves to the end of the
  field and deletes. Tapping an iPhone field already puts the cursor at
  the end.
* **`recent`, `search` and the arrows are refused** with a sentence
  that lists what an iPhone does have, rather than guessed at.
* **No list of apps.** WDA can't list what's installed. `apps` is
  Apple's own apps plus what `$SPARSH_IOS_APPS` names, and everyday
  names ("settings", "messages") come from a table on the device.
  `Phone.which_app` asks the device for `nicknames` first, since
  `com.apple.Preferences` doesn't say "settings" anywhere.
* **Which field has the keyboard.** Older WDA doesn't say. When the
  keyboard is up and one field is on screen, that field is it. With
  two, none is guessed, and an agent's typing has to name the field
  (note 02 already refuses typing that has nowhere to go).

## What has been checked, and what hasn't

The tests (`tests/test_iphone.py`) run the screens through the real
reader and the real `Phone`, against a stand-in WebDriverAgent that
answers HTTP on a local port and records every call. They check
where each tap lands, that a moved screen means nothing is tapped,
that a lapsed WDA session is opened again once, and that keys an
iPhone lacks are refused before anything is sent.

**None of it has run on a real iPhone yet.** The screens in
`tests/screens/ios` are written by hand in WDA's shape, not captured
from a phone. Neither script has run on a Mac or with go-ios. The first
real run is where this note gets its receipt, and probably a
correction or two: how a real Cell labels itself, whether `focused`
arrives, and the go-ios commands on a current iOS.

## What is not here yet

* A real iPhone: a captured Settings screen, the scripts run end to
  end, an agent's task done on it.
* Typing beyond plain ASCII. WDA could type it, but `typeable()`
  refuses it for both phones until Android can too.
* ~~Rebuilding WDA on a schedule, before the free signature runs out.~~
  Said instead of scheduled: the date is read from inside `WDA.ipa`
  (its `embedded.mobileprovision`) when it's installed, and `sparsh
  devices`, `sparsh status` (its `wda` field) and Yantra's startup line
  say it two days before. A rebuild needs the Mac and a password, so a
  reminder is the honest part; doing it unasked isn't.
