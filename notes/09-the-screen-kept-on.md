# 09 — the screen kept on

*[Note 08](08-a-real-phone.md) made a swipe lock no one's to open:
`wake` and `open_app` swipe it away. That covers a phone found asleep.
This note is about a phone that falls asleep while the agent is in the
middle of using it.*

## A rename that stopped at the lock screen

From Telegram, on `qwen3.8-64k:latest`, *"Rename my phone to Trial
Phone"*. The agent opened Settings, scrolled twice, searched, and the
next tool result was:

```
App: com.android.systemui
(The phone is locked: this is its lock screen, not the app asked for. Ask its person to unlock it, then look again.)
```

It told its person to unlock a phone they hadn't touched. Two things
had happened between steps. The phone's screen timeout is 30 seconds,
and a local model thinking between steps easily takes longer than that.
And someone else was using the phone at the same moment: a browser page
opened on it mid-task (Sparsh caught that one, *"the screen changed
since it was read … Nothing was done"*). With a PIN, a dark screen is a
lock only its person can open, and a phone left to time out mid-task
will always end up there.

## On while working, then the person's own

**A SCREEN THAT SLEEPS MID-TASK LOCKS THE TASK OUT**, so `sparsh mcp`
keeps it on while an agent works the phone. The first tool call of a
spell raises Android's screen timeout to ten minutes (and swipes away a
no-PIN lock if the screen had already gone dark). Every later call keeps
the spell going, reads included, because a model that looks and thinks
is still working. Two minutes after the last call, or when the server
stops, the person's own timeout comes back. Dvara stops its servers at
the end of each turn, so that is usually when it happens.

Three things keep it the person's phone:

* **Their value is written down before anything changes**
  (`~/.sparsh/phones/<serial>/screen-timeout`), so a server that was
  killed puts it back the next time one starts.
* **Only Sparsh's own value is undone.** If the timeout isn't ten
  minutes any more when the spell ends, the person changed it
  meanwhile, and theirs stays.
* **It never stops a step.** A phone that doesn't say its timeout (an
  iPhone: WDA can't read Auto-Lock) is left alone, and a failure to set
  it is ignored: keeping the screen on helps a step, and is never a
  condition of one.

`SPARSH_AWAKE` chooses:

| | |
|---|---|
| `working` (default) | the above |
| `always` | the screen never times out, until the setting says otherwise |
| `off` | the timeout is left alone (and one left over from `always` or a killed server is put back) |

**ALWAYS IS A PHONE SET ASIDE FOR THE AGENT.** With the screen lit for
good, a lit, unlocked screen no longer means someone has the phone in
hand, so `sparsh state` says `asleep` (free for a schedule) where it
would say `in_use`. That is wrong for a phone someone carries, which is
why it isn't the default.

A word Sparsh doesn't know stops the server with a plain error, rather
than being guessed at:

```
$ SPARSH_AWAKE=on sparsh mcp
sparsh: SPARSH_AWAKE is 'on'; it is one of working, always, off
```

## Live, on the Nexus 6P

The phone was dozing behind its swipe lock, with its own 30-second
timeout. One `look` through `sparsh mcp`, and the phone checked from
outside while the server ran and after it stopped:

```
before: 30000, mWakefulness=Dozing
during: 600000, mWakefulness=Awake, mDreamingLockscreen=false
look -> App: com.android.settings | 1 item "Search settings" [tap] | …
after: 30000
```

`always`, then `off`:

```
always, server gone: 2147483647; sparsh state: asleep: nobody has it, and no PIN stands in the way
                                  (without SPARSH_AWAKE: in use: the screen is on and unlocked)
off: 30000
```

Then the rename again, through Dvara (`dvara say`, the terminal standing
in for the chat), `qwen3.8-64k:latest`, the phone at its own 30 seconds.
It took 17 steps over several minutes and never met the lock screen.
Afterwards the timeout read 30000 again. The rename itself went to
Quick Share's device name, as in note 08: Android 8.1 has no
device-name setting of its own.

## What the tests hold

`tests/test_awake.py`: a spell raises the timeout once and puts the
person's own back, by itself after the idle time too; a dark screen with
no PIN is swiped at the start and a PIN never is; a timeout the person
changed meanwhile stays theirs; a killed server's is put back by the
next one; `always` never puts it back and makes a lit screen free; `off`
touches nothing; a phone that doesn't say is left alone and a failure
never stops a step; the setting is one of three words. 177 tests
before, 190 after.

## Not here yet

* **Two harnesses on one phone at once.** Each server keeps its own
  spell; the first to finish puts the person's timeout back while the
  other may still be working. One phone, one agent at a time is still
  the assumption.
* **An iPhone's Auto-Lock.** WDA can neither read nor set it, so an
  iPhone is left to its own.
