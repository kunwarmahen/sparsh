# The person's own hand

Sparsh sees what it does. Every tap the agent asks for goes through it,
is checked against the screen, and is written down
([note 02](02-held-for-a-yes.md)). What the person does with their own
finger it never saw, and until now it had no reason to.

The reason is a person teaching their agent a job by showing it (Yantra's
`/learn watch`). They open WhatsApp, tap Mom, type a message, and say
"next" after each step. The agent is told "next" and sees a new screen,
with no idea how it got there. A skill written from that is a list of
screens with nothing between them.

## Two tools

```
watch_phone   the screen now, kept as "before"; on Android, touches start
              being read
watched       what the person did since, and the screen now -- which
              becomes the next "before"
```

Both are reads: neither changes the phone, so a harness that knows
Sparsh never asks about them. The agent calls `watch_phone` once, when
the person says they're starting, and `watched` every time they say
they did a step.

## Android: the finger, against the screen as it was

`adb shell getevent -lt` streams the touchscreen's raw events.
It runs with a terminal on the phone's side (`adb shell -t -t`): piped,
getevent's lines wait in a 4 KB buffer (the receipt below shows what
that did). `getevent -lp` names which input device is the touchscreen and its
range, and `wm size` gives the screen's size. Together they turn a touch
into a spot in screen pixels. One touch, from the finger going down to
it lifting, is one gesture: a tap, a long press (0.6 s or more without
moving), or a swipe (40 pixels or more). Only the first finger is
followed, so a pinch reads as its first finger.

A tap's spot is matched to the smallest thing on the "before" screen
that holds it, so the agent reads

```
What the person did since the last look (on com.whatsapp):
1. tapped 4 item "Mom" [tap]
2. typed on the keyboard (12 key(s); what it says is on the screen now)
The phone now:
...
```

and not two numbers. Nothing is installed on the phone for this, and no
accessibility service is turned on. `uiautomator events` would name the
tapped element directly, but Android lets only one UI automation
connection run at a time, and it would fight `uiautomator dump`, which
every look needs.

ONLY THE FIRST STEP CAN BE NAMED. After a tap the screen moves, and the
screen it moved to wasn't read. Reading the screen after every touch
would race the person's next touch, and a dump takes one to three seconds
on a Nexus 6P. So a tap after the screen first moved is said as a tap
at a spot, with the reason: *the screen had moved on by then, so what
was there wasn't read*. The agent is told to call `watched` after every
step, so in a lesson this is the rare case, and it is said rather than
guessed.

KEYS ARE COUNTED, NEVER READ. Touches inside the keyboard's area (the
same `keyboard_area` that keeps a tap off a key, [note 08](08-a-real-phone.md))
are one step of typing. What was typed is read off the screen afterwards.
A password typed while showing is a row of dots on the screen, so it is
a row of dots to the agent too.

## An iPhone shows no fingers

WebDriverAgent drives an iPhone; it can't watch one. There `watched`
gives the screen before and the screen now, and says why:

```
This phone doesn't show where it is touched, so compare the two screens
to tell what the person did -- and ask them if unsure.
The phone before:
...
The phone now:
...
```

The agent tells the person what it thinks they did ("you opened
General"), so they can correct it. That's slower than Android's answer,
but it doesn't claim to know more than it does.

## Written down as theirs

Each step `watched` names goes into the same log as the agent's, by
`you` (`log.noted`), so `sparsh log` and Yantra's `/phone log` show the
walk-through beside what the agent did. An iPhone's comparison names no
step, so nothing is logged for it.

## The screen is assumed upright

A touch is scaled from the touchscreen's range to the size `wm size`
gives. A phone turned sideways while showing would put the spot in the
wrong place, and the tap would be matched to the wrong thing. Lessons
are taught upright; the rotation isn't read.

## Receipt

From the tests (`tests/test_hand.py`), the events a Nexus 6P's
`getevent -lt` prints for one tap:

```
[   61046.716370] EV_ABS       ABS_MT_TRACKING_ID   00000a2f
[   61046.716370] EV_ABS       ABS_MT_POSITION_X    000001a0
[   61046.716370] EV_ABS       ABS_MT_POSITION_Y    00000600
[   61046.716370] EV_KEY       BTN_TOUCH            DOWN
[   61046.790000] EV_ABS       ABS_MT_TRACKING_ID   ffffffff
[   61046.790000] EV_KEY       BTN_TOUCH            UP
-> Gesture("tap", 416, 1536)
```

A tap at 400,1500 on the saved Pixel home screen is named `tapped`
Gmail's line; the same tap after the screen moved is unnamed; two keys
on the keyboard are `typed on the keyboard (2 key(s)…)`; and with no
touch feed (an iPhone), both screens come back and nothing is logged.
### On the real Nexus 6P

The touchscreen is `synaptics_dsx` at `/dev/input/event0`, with a range
of 1439 × 2559, the same as `wm size`'s 1440x2560, so the scale is 1. The
person did each step and said next:

```
unlocked (fingerprint)   -> No touch was seen, but the screen changed ...
                            the lock is a sensor on the back; nothing touched
                            the screen, and nothing was claimed
opened Gmail             -> 1. tapped 10 item "Folder: Play" [tap]
                            2. swiped up
```

That second answer was wrong, and the reason was the pipe. Two raw
readers ran alongside for that step, one piped and one with a terminal:
the piped one had **0 lines**, the one with a terminal had all 40, three
clean taps. Sparsh's own piped reader had been handed one 4 KB chunk late,
so half a gesture from one step was joined to the next. With `-t -t`:

```
tapped the search box, typed "uni"
  -> What the person did since the last look (on com.google.android.gm):
     1. tapped 3 field "Ask Gmail" [tap, type]
     2. typed on the keyboard (3 key(s); what it says is on the screen now)
     The phone now:
     3 field "uni" [tap, type, focused]

sparsh log
  14:19:38 you   tap  [on 3 field "Ask Gmail" [tap, type]] -> done
  14:19:38 you   typing -> done (typed on the keyboard (3 key(s); ...))
```

The field was named from the screen as it was before the tap. The three
keys were counted, not read, and "uni" came off the screen afterwards.
281 tests pass.

Not yet run: the iPhone's before-and-after, and a whole lesson through
an agent (`/learn watch`).

## What is not here yet

* **A fingerprint unlock is a step nobody saw.** It is said as "the
  screen changed with no touch", which is true. A lesson that starts
  locked starts from the lock.

* **Naming every step, not just the first.** A screen read after each
  touch settles would let the second and third taps between two
  "next"s be named too. Worth it only if people forget to say next.
* **A sideways phone.** The rotation from `dumpsys input` would fix the
  scaling.
