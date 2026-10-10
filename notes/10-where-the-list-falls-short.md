# 10 — Where the list falls short, and what you say yes to

*[Note 05](05-a-picture-where-the-list-has-nothing.md) sent a picture
where the list has nothing, and [note 06](06-a-tap-by-position.md) let
the agent tap a spot on it, held every time. Both were all or nothing:
one readable line on a screen, and no picture went. A real phone
showed what that missed, and what the person saw when asked.*

## Thirty-odd steps to read four names

From Telegram, on a real Nexus 6P, `qwen3.8-64k:latest`: *"Search for
good Indian restaurants near by."* The agent searched in Chrome and
read back:

```
App: com.android.chrome
1 text "Web View"
2 button "Open the home page" [tap]
3 item "Connection is secure" [tap]
4 field "google.com/search?q=good+Indian+resta..." [tap, type]
...
```

So it told its person it couldn't read the results, and offered Google
Maps. Maps' results came back like this:

```
14 item "Sponsored — Wheelchair accessible" [tap]
16 item [tap, scroll]
17 item [tap]
18 item [tap]
19 item [tap]
20 item [tap]
...
26 item "Call" [tap]
27 item "Website" [tap]
```

Every button had a name, and not one place did. With *"Tap through"*,
the agent opened each blank row, read the place's own page, pressed
back, and scrolled for the next: thirty-odd steps, half an hour, for
four restaurants. The screen showed all four names the whole time. No
picture went, because the list had *something*.

Then *"dial"*, and the card its person was asked with:

```
Do this on the phone?
On the phone 192.168.1.161:5555: tap button "Call (dial)" in com.google.android.dialer -- held because it says "call".
The screen when it was asked for:
App: com.google.android.dialer
1 item "dialpad view" [tap]
2 button "More options" [tap]
3 field "(919) 535-3020" [tap, type, focused]
4 button "backspace" [tap]
5 item "1," [tap]
6 text "1"
...
41 item "Send a message" [tap]
```

Forty-one lines, most of them the keypad. The number being called is
line 3. The person said yes, and the agent answered that *"the hold on
the dial button expired"*. Sparsh's log says otherwise: the tap was
done at 21:57:36, and the phone answered *"Turn off airplane mode to
make a call."*

Three things went wrong, and each one is fixed below.

## A list that is there and still says nothing

**A LIST CAN BE THERE AND STILL SAY NOTHING.** The reader now counts
two ways a screen's list leaves out what matters on it
(`Screen.partly_blank`):

* **Things to tap with no words**: three or more, not counting a box as
  big as the screen (Maps lays one behind everything). Across the 194
  screens the agents had read on the emulator and the 6P, only Maps
  reached three. Settings, Messages, the launcher, Chrome with a page
  read all count zero.
* **A web page with no words in the list**: a `WebView` with nothing
  inside it that has words.

The second one isn't Chrome hiding the page. Read again a few seconds
later, the same search came back with every restaurant on it:

```
40 item "Haveli Indian Cuisine Rated 4.7 out of 5 179 reviews ..." [tap]
51 item "Taj Indian Bistro Rated 4.9 out of 5 242 reviews ..." [tap]
```

Chrome fills in a page's description a moment after it's first asked
for, and the agent's look came 0.8 seconds after Enter. So **A BLANK
PAGE IS LOOKED AT TWICE**: Sparsh waits two settles and reads it again.
Only a page still blank after that counts as partly blank.

A partly blank screen goes out like an unreadable one, with a
screenshot (`--shots` only, never of an app on the `never` list), and
says why:

```
(A screenshot is attached -- 6 things on it to tap have no words: you can already see it, no tool is needed. Tap by number whatever the list has; for what only the picture shows, tap_at its position, which the person is asked about.)
```

One screen does *not* get its picture: the lock screen. Its
notifications are unnamed boxes too, and the 6P's counted four. But a
lock screen already says what it needs, *"ask its person to unlock
it"*, and a look doesn't help with that.

**THE MODEL MAY ASK.** No count catches every way a list falls short,
and the model can often tell (a map with no places on it). `look` takes
`picture: true`. Without `--shots` the answer says there is no picture
and to work from the list, so the model isn't left waiting for one. And
Yantra's phone layer tells a model that sees: ask for a picture, don't
open rows one by one to find out what they are.

**A TAP BY POSITION GOES WITH THE PICTURE.** `tap_at` was refused
wherever the list had anything. Now it's allowed on any screen that
came with a picture, partly blank or asked for (`Phone.pictured`, set
by the server when it attaches one, cleared by the next result without
one). It's still held every time, and the person still sees the spot.
Nothing gets past a hold this way: a spot on Send is asked about just
as the Send button is, and a spot has no grant.

**THE MODEL'S PICTURE IS MADE SMALLER.** The first live run of all
this, on the 6P with `qwen3.8-64k:latest`, never answered. Maps shows
one place per screen under its map, so the agent scrolled, and each
result brought a full screenshot. Sent straight to Ollama, one cost
3635 tokens of the model's 64k and took 22 seconds to read. By the
tenth scroll, each step took two minutes, and the turn hit its
25-minute limit still scrolling. The same screen at 720 pixels across
cost 950 tokens and took 8 seconds, and qwen read the same thing from
it ("Anjappar Indian - 4.8 (51 reviews)"). From Chrome's results at
that size it read *Haveli Indian Cuisine, 4.7 (179 reviews)* and *Taj
Indian Bistro, 4.9*. So the picture the model gets is made smaller the
way the person's is (picture.py). A tap by position is a share of the
picture, not a pixel, so it lands in the same place.

## What the person says yes to

**THE PERSON SEES WHAT THEY SAY YES TO.** The numbered list is the
model's. It is how a model with no eyes knows where things are, and it
was never meant for a person deciding about a phone call in a chat.
Every hold now takes a screenshot as it is made, and `describe_hold`
gives:

```
On the phone 84B7N16128001616: tap button "Call (dial)" in com.google.android.dialer -- held because it says "call".
On the screen: field "(919) 535-3020"
```

with the picture made smaller (720 pixels across at most) and **what
it would tap ringed**, or the field it would type into. The words
filled in on the screen (fields with text, never a password, three at
most) go on the card as well, because they are what a person checks:
the number being called, the message being sent. Dvara sends the
picture to Telegram first and the buttons under it. Yantra's page
shows it above the words, and its terminal saves it to a file.

**THE PHONE BY ITS NAME.** The cards above start *"On the phone
192.168.1.161:5555"* or *"84B7N16128001616"*, an address and a serial
its person had never seen. A card now says *"On your phone (Nexus
6P)"*: the name its owner gave it in Settings (`settings get global
device_name`, Android 7.1 and later), or its model if that's unset, or
an iPhone's own name from WDA. The serial is said only when the phone
gives no name. The app goes the same way: *"in Phone"*, not *"in
com.google.android.dialer"*. A short table names the apps people know
(`APP_NAMES`: Phone, Messages, Maps, Chrome, Gmail, Settings …), an
iPhone's nicknames are read backwards, and any other app is named by
the last part of its package that isn't a maker's
(`com.Nishant.Singh.DroidTimelapse` is *DroidTimelapse*).

The first live card put the ring on the phone's Home button, which
showed two things. **THE RING IS A SHARE OF THE PICTURE.** Android's list
measures the screen without its navigation bar (2392 pixels tall on
the 6P), and its screenshot includes it (2560), so a share worked out
from the list landed low. It's now worked out from the screenshot's own
size, as a tap by position already was (an iPhone's from its size in
points, which is what its list uses). **WHAT THE YES WILL TAP IS SHOWN
UNCOVERED.** The dialler's green Call button sat under Gboard's number
pad, which the list leaves out (note 08). A yes already puts the
keyboard away before tapping. Now the hold does that before it takes
the picture, so the ring is on a Call button the person can see. Back
only closes a keyboard; nothing is done early.

The list comes back only when there is no picture: a phone that
wouldn't give a screenshot, or an app the rules keep out (where no
step is ever held anyway).

A screenshot costs a second or so on a real phone, and ringing it two
more seconds in plain Python. That's paid only for held steps, and
it's small next to the person reading the card.

## "Done" means done

**A YES COMES BACK AS DONE, AND THE PHONE'S ANSWER AS THE PHONE'S.**
`confirm` returned `Done. App: …` and the next screen, and the
dialler's screen that time was a two-line dialog. The model read the
dialog as its own step failing. It now reads:

```
Done: the step was carried out. The phone now (its answer to the step):
App: com.google.android.dialer
1 text "Turn off airplane mode to make a call."
2 button "Cancel" [tap]
```

`confirm`'s own description says the same, and so does Yantra's phone
layer: what follows "Done:" is the phone's answer to a step that was
carried out (*"Network is not ready"*, *"Turn off airplane mode"*),
never a lapsed hold.

## Live, on the Nexus 6P

Through Dvara (`dvara say`, the terminal standing in for the chat),
your own `minder` package, `qwen3.8-64k:latest`, the phone over its
cable. *"On my phone, search Google Maps for Indian restaurants near me
and tell me the top three by name with their ratings."* Seven steps,
4 minutes 39 seconds, and no row opened:

```
Here are the top 3 Indian restaurants from your Google Maps search:

1. **Kaara Modern Indian Restaurant** — 4.9 ★ (2,174 reviews)
2. **Haveli Indian Cuisine** — 4.7 ★ (179 reviews)
3. **Charminar Biryani & Chat** — 4.3 ★ (302 reviews)
```

Before the pictures were made smaller, the same request scrolled for
25 minutes and never answered (above).

Then *"Call Haveli Indian Cuisine at 919-535-3020 from my phone."* The
agent opened the dialler, typed the number, and the Call tap was held:

```
minder wants to run mcp__sparsh__confirm:
  Do this on the phone?
On the phone 84B7N16128001616: tap button "Call (dial)" in com.google.android.dialer -- held because it says "call".
On the screen: field "(919) 535-3020"
(The picture shows the phone's screen; what it would tap is ringed.)
  the phone's screen, what it would tap ringed: /tmp/dvara-ask-rnt4cr4a.png
approve? [y/N]
```

The picture was the dialler at 720 by 1280: the number across the
middle and the green Call button ringed in red, the keyboard put away.
The first try, before the two fixes above, ringed the Home button under
Gboard's keys. No was answered. Nothing was dialled, and the agent
said: *"You declined that — I won't place the call. The number is
dialed up on your phone if you'd like to press call yourself."*

Then a tap by position, for something only the picture has: *"On my
phone, search Google Maps for Indian restaurants, then tap the pin on
the map (not the list) of the best-rated one you can see on the map,
to open it, and tell me its name."* A map's pins have no lines in the
list at all; the map is one backdrop the size of the screen. The agent
opened Maps (`open_app "Google Maps"`, one step now: see below),
searched, and asked:

```
On the phone 84B7N16128001616: tap the spot ringed on the picture (x 412, y 266 of 1000) in com.google.android.apps.maps -- held because it is a tap by position: what is at that spot is known only from the picture.
(The picture shows the phone's screen; what it would tap is ringed.)
```

The picture had the red ring on the pin marked 4.7, the best rating
on the map. Yes, and:

```
The best-rated pin visible on the map was 4.7, and it opened **Haveli Indian Cuisine** (4.7 stars, 179 reviews, 1125 Hatches Pond Ln Ste 113).
```

The first yes didn't get that far. **THE APP IN FRONT, ON OLD ANDROID
TOO.** Sparsh refused the tap, saying *"the phone is in another app now,
not com.google.android.apps.maps; nothing was tapped"*, five seconds
after the question and with nobody touching the phone. It finds the app
in front from the line `topResumedActivity=`, which Android 10 and later
print. The 6P runs 8.1, which prints only `mResumedActivity:`, so the
app read as no app, and a yes to any tap by position there was always
refused. Both are read now. The emulator (Android 15) never showed it.

## Names a package doesn't say

The same runs lost a step at each app. `open_app` found "Google Maps"
nowhere: no part of `com.google.android.apps.maps` is "googlemaps".
"phone" isn't in `com.google.android.dialer` at all. The agent got the
list of packages back, and its next step named one. Android won't tell
a computer an app's name as the launcher shows it, so it has to come
from somewhere else. There are three places now:

* **A table, for apps whose package says something else** (`NICKNAMES`
  in device.py): "phone", "dialer" and "calls" are the dialler, "gmail"
  and "email" are `com.google.android.gm`, and so on for contacts,
  camera, clock, calendar, gallery and files. Each name lists the
  packages that app goes by on Google's, Samsung's and plain Android's
  phones, most likely first. Only an installed one is opened.
* **A whole part of a package beats one that only begins with it.**
  "Chrome" found both `com.android.chrome` and
  `com.google.android.apps.chromecast.app`, and refused as unclear.
* **WORD BY WORD, LAST WORD FIRST.** "Google Maps" gets "maps" and
  finds one app. A word that fits several ("google" fits ten on the 6P)
  is passed over, not guessed at. Words that name no app ("app", "the",
  "my") are passed over too: "the phone app" had found Chromecast
  through `chromecast.app`.

Against the 6P's 37 apps: "Google Maps", "phone", "Phone app", "Chrome",
"Google Chrome", "Gmail", "Messages app" and "Google Photos" each open
the app meant. "Google" alone still says it fits several.

## What the tests hold

`tests/test_screen.py`: Maps' unnamed places make a screen partly
blank and a screen-sized backdrop doesn't count; two aren't enough; a
web page with no words is a blank page and one with words isn't; none
of the saved screens is partly blank.

`tests/test_rules.py`: the ring is a share of the picture, not of the
list; a target under the keyboard is shown with the keyboard put away,
and the yes still taps it.

`tests/test_phone.py`: a phone is named as its person named it, or by
its model; an app as a person calls it. The app in front is read from Android 8's words
and Android 10's. A nickname finds an app no package names, and
only one that is installed; "Chrome" is Chrome, not Chromecast too;
"Google Maps" and "the phone app" go word by word, and "google stuff"
opens nothing. A page not yet described is read once more and
found filled; a page that stays blank is read twice, no more.

`tests/test_mcp.py`: a partly blank screen comes with its picture and
says why, and without `--shots` it's only the list; a lock screen with
unnamed notifications comes without one; a picture can be asked for on
any screen, and without `--shots` the answer says there is none;
`tap_at` works on a screen that came with a picture and is refused
after the next look without one; on a partly blank screen it's held; a
held tap is shown as its picture, ringed and made smaller, with the
words filled in and no list; with no screenshot to be had, the list
comes back; a held step names the phone, not its address; a yes says "Done: the step was carried out."; the model's
picture is 720 pixels across.

190 tests before, 217 after.

## Not here yet

* **An iPhone's partly blank screens.** The count reads Android's
  words. An iPhone's screen is rewritten into them (note 03), so it
  should carry over, but no real iPhone has been read.
* **Pictures for a cloud model.** As in note 05, on only when its
  person says so (`YANTRA_PHONE_SHOTS=on`), and untried.
* ~~**Everyday names for some apps.**~~ See *Names a package doesn't
  say*, above.
* **A threshold that learns.** Three unnamed things is a number from
  194 screens on two phones. Another maker's apps may want another.
