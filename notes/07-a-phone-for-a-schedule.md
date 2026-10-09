# 07 — A phone for a schedule

[Note 02](02-held-for-a-yes.md) holds the steps that can't be taken
back (Send, Pay, Delete) for a person's yes, and the harness asks them.
That works while someone is there. A schedule runs when nobody is:
"text Sam every morning that I'm on my way" would be held at Send every
morning, with nobody to say yes. And the phone a schedule wants is
somebody's, maybe in their hand, maybe locked.

Sparsh's part is two small things. The waiting, the asking and the
skipping belong to the harness (Dvara's note 33).

## A grant: one held tap, narrowly

**THE PERSON NAMES IT, WITH THE SCHEDULE.** When they accept a schedule
they may name the held steps it may do without asking, and whoever
starts the tools passes them in `SPARSH_GRANTS`, a JSON list of
sentences in one form:

    send in Messages when the screen shows 555-0123

A tap held for its words goes through when one grant covers all three
parts at the moment of the tap: the tapped thing says that word (as a
whole word, the way the hold matched it), that app is in front (an
everyday name, found as `open_app` finds one), and that text is on the
screen.

**ON THE SCREEN, NOT "THE RECIPIENT".** A held Send knows its own words
and the app. It doesn't know who the message goes to; that is just
words somewhere on the screen, usually the conversation's title. So the
grant says what must be on the screen, and a Send in a chat with someone
else, where 555-0123 isn't, is held as before. The weak spot is honest:
the number written inside a message in another chat would pass. A
narrower check would need knowing the recipient, and the list doesn't
say it.

**NOTHING ELSE, EVER.** Not a tap by position (a spot has no words to
match), not typing into a password field, not Enter (held when a Send
sits beside the field), not a refused word, not an app on the `never`
list. A grant that can't be read is an error that stops the server,
never dropped: a schedule must not run believing it may do something
it may not.

The step log says so: `-> done (granted ahead: "send in Messages when
the screen shows 555-0123")`, and the screen the agent gets back starts
with the same sentence.

## Is it free?

`sparsh state [--json]` reads what Android already knows, from
`dumpsys power` (`mWakefulness`) and `dumpsys window`
(`isKeyguardShowing`):

| state | means |
|---|---|
| `in_use` | screen on and unlocked: someone has it in hand |
| `locked` | the lock screen is up: only its person can open it |
| `asleep` | nobody has it and no PIN is in the way (screen off, or a swipe lock): `sparsh wake` turns it on and swipes ([note 08](08-a-real-phone.md)) |
| `unknown` | the phone didn't say; an iPhone (WDA) says only "locked" |

**A LOCKED PHONE CAN'T BE WORKED.** It would take the person's PIN, and
Sparsh never has it. A phone that isn't in use is usually locked, so on
a real phone "free" mostly means "ask them to unlock it". The emulator
has no lock, which is why this never showed in the trials. To try it,
give the emulator a PIN: `adb shell locksettings set-pin 1234`, and
`adb shell locksettings clear --old 1234` afterwards.

## Live, on the emulator

Through Samay and Dvara, `qwen3.8:latest` on Ollama, a schedule "Text
555-0123 saying: running late, home by 7" with the grant above:

```
19:04:20 agent tap n=5  [on 5 item "Send SMS — SMS" [tap]] -> done
         (granted ahead: "send in Messages when the screen shows 555-0123")
```

The message was in the emulator's sent box. A second schedule texting
555-0199 with the same grant was held at Send, and the run's report
named the step. `sparsh state` read `in_use`, `asleep` and `locked`
correctly as the emulator was put in each.

## What the tests hold

`tests/test_rules.py`: a grant lets its Send through while its text is
on the screen; not when the text isn't there, or for another app or
word; never for a password; one that can't be read is an error; the
step log says "granted ahead" once; the phone's four states.
159 tests before, 166 after.

## Not here yet

* ~~A real phone. Its lock, its own Messages, its own screen-off
  timing.~~ A Nexus 6P: its lock read right, its Wi-Fi dozing while
  locked fixed ([note 08](08-a-real-phone.md)).
* An iPhone's `state` beyond "locked", and `wake` (WDA has no wake key).
