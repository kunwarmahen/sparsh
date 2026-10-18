# 13 — A scroll that skipped rows

*[Note 12](12-a-real-iphone.md) got an agent's task done on a real
iPhone. The next task looked done too, and the answer was wrong: the
page was read before it loaded, a scroll skipped rows, and the menu
the agent chose from said everything five times.*

## Five refunds the agent never saw

On an iPhone 17, an agent was asked whether an Amazon refund had come
through yet. It opened *Completed refunds*, scrolled down once, read
the list and answered that the newest refund was from November 2025.
The person said that was too old. The agent read the same rows again.
Only after the person told it to swipe up did it find refunds from May
and January.

Sparsh's log (`sparsh log`) showed what happened:

```
18:55:32 tap 26 "Completed refunds"
         ... 16 text "Credit or debit card refunds"     <- no rows yet
18:55:39 scroll down
         ... 11 button "Refunded November 7, 2025 +$12.82 ..."
```

The first screen came back before the list had loaded. There was a
heading and nothing under it. The scroll that followed carried the five
newest refunds past the screen in one move. Nothing the agent was shown
said any rows had gone by, so it took November 7 as the top of the list.

Two things made the scroll too long:

* **The swipe was 60% of the screen.** Amazon's own bars take the top
  and bottom of the screen, and the refunds filled 55% of it, so every
  row on the screen went off the top. No row was on both screens.
* **The finger lifted while it was still moving.** iOS reads that as a
  flick, and the page coasts on after the finger has gone.

## Two rows shared, every time

**TWO SCREENS SHARE ROWS.** A scroll now moves the finger 40% of the
screen, and on an iPhone the finger rests for 200 ms before it lifts,
so the page stops where the finger stopped. The same page on the same
phone, scrolled down once from the top, three times with the rest and
once without:

```
with the rest, try 1   top row: Refunded December 30, 2025 +$53.61
with the rest, try 2   top row: Refunded December 30, 2025 +$53.61
with the rest, try 3   top row: Refunded December 30, 2025 +$53.61
without the rest       top row: Refunded November 8, 2025 +$32.16
```

December 30 and November 8 were the last two rows of the screen before
the scroll. With the rest, both are still there afterwards, so the
agent can see where the two screens join. Without it, the page went one
row further, and December 30 was never on any screen.

The tradeoff: a long list takes half as many scrolls again as before.
On a local model each step costs time, but a scroll that skips rows
gives an answer that is wrong and looks right.

## A swipe for the list landing on a call

While this was being tried, a call rang in on the iPhone. A scroll
meant for Amazon was sent to the call screen, with *Answer call* and
*Decline* on it. An up-and-down swipe doesn't answer an iPhone call,
but on an Android phone a swipe can answer or decline one.

A tap was already safe. It is aimed at a number, and Sparsh looks for
that thing again before tapping ([note 01](01-a-list-not-a-picture.md)):
a call screen doesn't have the agent's "Completed refunds", so nothing
is tapped. A scroll, and typing where the keyboard already is, were
aimed at whatever was in front.

**THE SAME APP, OR NOTHING DONE.** Before a scroll, or typing with no
field named, the screen is read again. If another app is in front now,
nothing is done, and the agent gets the new screen back, as it does
when a tap's screen moved. Tried on the real iPhone, with Settings
brought up behind Sparsh's back between the look and the scroll:

```
read: com.amazon.Amazon
refused: the phone is in com.apple.Preferences now, not com.amazon.Amazon
where the screen was last read. Nothing was done. The screen now:
App: com.apple.Preferences
1 text "Settings"
...
```

On a screen that can't be read (one that never goes still), only the
app in front is checked. Keys are left alone: Back and Home are how an
agent leaves an app it shouldn't be in, and refusing them would trap it.

## A page read before it had loaded

Android waits for the screen to go still before describing it. On the
iPhone that wait is off, because WhatsApp never goes still
([note 12](12-a-real-iphone.md)), and a page inside an app fills in
after it opens. Read over and over after the tap on *Completed
refunds*:

```
 1.6s   20 lines  rows=0
 2.6s   21 lines  rows=5  first=['Refunded May 20 +$72.49 ...']
 3.6s   21 lines  rows=5
```

Sparsh waited 0.8 s and read once, so the agent got the heading and no
rows. With the shorter scroll it would still have started below the
newest refunds.

**READ AGAIN UNTIL IT HOLDS STILL.** On an iPhone, after a step, the
screen is read again until two reads agree, for up to 4 seconds after
the step. The iPhone doesn't mark which part of a screen is a web page,
so it can't be only those. A screen that was already still costs one
more read (about a second on Amazon). A slow one, like WhatsApp at 8
seconds a read, is past the 4 seconds after its first read and gets no
second. Android's reads already wait, so nothing changes there.

From Amazon's menu, *Customer Service*, then one tap on *Completed
refunds*, three times: the screen came back with all five rows each
time, the newest first. Asked again through Sarathi's containers once
they were rebuilt with both fixes (*"open Amazon's Completed refunds and
tell me the three newest"*), the answer started at May 20.

## Five lines of the same words

Amazon's menu on the iPhone came back like this:

```
9 text "Your shortcuts Orders Subscribe & Save Account Customer Service Lists ..."
10 list [scroll]
11 text "Your shortcuts Orders Subscribe & Save Account Customer Service Lists ..."
12 text "Your shortcuts Orders Subscribe & Save Account Customer Service Lists ..."
13 text "Your shortcuts"
14 text "Orders Subscribe & Save Account Customer Service Lists Buy Again ..."
15 list [scroll]
16 text "Orders Subscribe & Save Account Customer Service Lists Buy Again ..."
17 text "Orders"
18 item "Orders" [tap]
```

A web page inside an app names every box around its content with all
the words inside it, and the box around a link with the link's own
words. Each box got a line.

**A BOX THAT REPEATS ITS INSIDES SAYS NOTHING.** A box that isn't
tappable or a field, whose every word is said by something inside it,
gets no line. Words inside that are off screen count too: a row
scrolled away is the list's to show after a scroll, not the box's to
say now. A box with a word of its own keeps its line, and so does one
with nothing on screen inside it that has words. The same menu now:

```
9 list [scroll]
10 text "Your shortcuts"
11 list [scroll]
12 item "Orders" [tap]
13 item "Subscribe & Save" [tap]
14 item "Account" [tap]
15 item "Customer Service" [tap]
16 text "Explore more for you"
...
24 text "Browse by category"
25 button "Customer Service. List item 1 of 22 (collapsed)" [tap]
```

58 lines became 31. Settings, Messages and WhatsApp on the same phone
read exactly as before. A notification banner lost a line saying the
same as the button inside it.

## What is not here yet

* **The route through the app.** The agent reached the refunds through
  Customer Service, not Orders. *Orders* was on its screen as a line to
  tap; the model chose the other way. That is what the agent knows about
  Amazon, not what Sparsh shows it: a learned skill in Yantra can teach
  it once.
* **The same wait on Android, for a web page inside an app.** Android
  waits for a still screen, which a page still fetching its rows may
  already be. Not seen yet; Chrome's empty page is read twice
  ([note 10](10-where-the-list-falls-short.md)).
