# 05 — A picture where the list has nothing

[Note 01](01-a-list-not-a-picture.md) chose a list over a picture: the
phone's own description of its screen, numbered, which a local model
reads well. That choice has a hole, and the phone trial found it. Some
screens give the list nothing. Settings' *About phone* page counts "Up
time" every second, so Android never calls it still enough to describe.
An app drawn as one big picture describes itself as a few unlabelled
lines. On those screens the agent was told "can't be read", and that
was all.

## Only there, and only when turned on

`sparsh mcp --shots` adds a screenshot to a tool's answer **when the
screen it led to has no list**: empty, or not describable at all. A
screen the list can read never comes with one. That keeps note 01's
bargain everywhere it already held: the model still works from the
numbered lines, and a picture costs nothing until there's nothing else.

**OFF UNLESS WHOEVER STARTS THE SERVER TURNS IT ON.** A phone's screen
is the person's messages, names and one-time codes. Sparsh can't tell
whether the model on the other end can see pictures, or whether it runs
on this computer or in someone's cloud. The harness that starts it can.
Yantra turns it on for a local model that says it can see, and for a
cloud model only when the person sets `YANTRA_PHONE_SHOTS=on`.
`sparsh status --json` names the flag (`"shots": "--shots"`) so a
harness knows this Sparsh has it.

**NEVER OF AN APP THE RULES KEEP OUT.** An app on the person's `never`
list shows the agent nothing, and the picture would undo that. When the
screen can't be read, its app isn't in the description either, so
Sparsh asks the phone which app is in front (`dumpsys activity
activities` on Android, WDA's `activeAppInfo` on an iPhone). An app on
the list gets no picture. If the app can't be named at all while the
rules keep the agent out of any, there's no picture either: unsure is
the side to refuse on.

**AN UNREADABLE SCREEN IS AN ANSWER, NOT A FAILURE.** `look` used to
fail on the About page ("Not done: the screen keeps changing"). A
failed call carries text only, so the picture would have had nowhere to
ride. Now `look` answers with the app in front and what to do, and the
picture comes with that answer:

```
App: com.android.settings
(this screen can't be read as a list: the screen keeps changing (a video,
an animation, or a clock ticking -- Settings' About page does), so the
phone can't describe it. Press back to leave this page, and find what you
need another way (a search, a different page).)
(A screenshot of this screen is attached to this result: you can already
see it, no tool is needed. Only numbered things can be tapped, so to act
on what it shows, find it another way -- press back, scroll, or search.)
```

The second sentence originally said "read it there". In the trial,
`gemma4:26b` once went looking for a `read_image` tool to open a file
it imagined. Saying the picture is already in front of the model, and
that no tool is needed, is the fix: in two more runs with the new
wording, it never did.

## The picture is for reading

**NOTHING TAPS BY POSITION.** Note 01's rule stands: the agent says a
number, and a number is something that was on the list. A picture of
the About page shows "Device name", but there's no number to tap it
with. The sentence under the picture says so, so the model goes another
way (a search, another page) instead of guessing.

## Live, on the emulator

`gemma4:26b` on Ollama, through Yantra, with the About page open. The
model was asked for the phone's IMEI, a fifteen-digit number nobody can
guess:

```
sparsh: 9 tool(s); phone emulator-5554 (sdk_gphone64_x86_64), emulator-5556
(sdk_gphone64_x86_64); screenshots on (local model) -- via .../sparsh

The IMEI number shown on the phone's screen is 867400022047199.
── end_turn · 5179 in / 286 out · 2 iteration(s)
```

That is the emulator's IMEI. One `look`, one picture, and the list had
nothing.

The phone trial's two About-page tasks with `--shots`
(Yantra's `examples/phone_trial.py`), `gemma4:26b`:

| task | without pictures | with pictures |
|---|---|---|
| which Android version | done in round 1, not done in round 3 | done, 2 of 2 (pictures shown 1 and 3 times) |
| rename the phone | not done | not done, 0 of 4 |

Without pictures, the version question came down to luck: whether one
of the many reads happened to catch the About page still
([Yantra's note 120](https://github.com/kunwarmahen/yantra/blob/main/notes/120-thirteen-tasks-on-a-phone.md)).
With them, the first visit is enough. Renaming needs a tap on the About
page, and a picture gives no number to tap. In one run gemma renamed the phone's
*Bluetooth* name instead and said the phone was renamed. Reading the
phone afterwards caught it. Pictures make a page readable; they don't
make it workable.

## What the tests hold

`tests/test_mcp.py`:

* an unreadable screen is an answer with its app, not an error;
* without `--shots`, no picture is sent;
* with it, an unreadable screen comes with a PNG, and a readable one
  doesn't;
* an act that leads to an unreadable screen says "Done" and shows it;
* no picture of an app on the `never` list, nor of one that can't be
  named while some are kept out.

127 tests before, 134 after.

## Not here yet

* Acting on what only the picture shows. That would mean tapping by
  position, which this project decided against.
* The cloud road. Turned on with `YANTRA_PHONE_SHOTS=on` and untried,
  like the rest of the cloud trial.
