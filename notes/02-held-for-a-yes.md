# 02 — Held for a yes

[Note 01](01-a-list-not-a-picture.md) gave a person hands on a phone: a
numbered list, and a tap that checks before it lands. This note gives
those hands to an agent. The question that comes with them is the old
one: what may it do without asking?

## Asking every time is asking never

A harness that honours MCP's hints asks before every tool call that
changes something. A tap changes something. Sending an SMS on the
emulator took nine steps: open Messages, skip its sign-in screen, start
a chat, type the number, pick the contact, type the message, tap Send.
Asked about all nine, a person stops reading by the third. The yes that
mattered, the one on Send, gets the same glance as the one on "Use
Messages without an account".

So the question moves to the one place that can see what a tap is
*on*: Sparsh. **THE PHONE'S RULES DECIDE WHAT ASKS.** An agent's steps
run by themselves, and Sparsh holds the few that can't be taken back:

* a tap on something whose words say it acts: Send, Pay, Buy, Order,
  Place, Book, Confirm, Submit, Post, Share, Reply, Call, Delete,
  Remove, Install, Uninstall, Allow, Accept, Sign out, Block and a few
  more (`ASK_WORDS`). They're matched as whole words anywhere in the
  label, so "Place order" and "Delete account" are held and the
  "Orders" tab is not;
* typing into a password field;
* Enter, while the screen shows something that would be held (below).

Wrong guesses go one way: a tap held that didn't need to be costs one
yes. A tap missed costs a sent message. That decides which side the
list errs on.

## Held, not done

A held step isn't carried out. The agent gets an error it can read:

```
NOT DONE -- this needs the person's yes: tap image "Send SMS" in
com.google.android.apps.messaging -- held because it says "send". Call
confirm with hold "h68873c" to ask them. Do not try another way round it.
```

**`confirm` IS THE ONLY WAY THROUGH, AND EVERY HARNESS ASKS ABOUT IT.**
It is the one tool marked destructive. A harness that knows Sparsh
(Yantra reads each tool's kind from `sparsh status --json`) lets reads
and acts run and asks about `confirm` every time, even when told to
stop asking. A harness that knows nothing of Sparsh asks about it
anyway, because of the hint.

What the person reads is not a hold id. `describe_hold` gives the step
in words and the screen it was asked on, so the yes is to the message
that will go, as the phone shows it:

```
Do this on the phone?
On the phone emulator-5554: tap image "Send SMS" in
com.google.android.apps.messaging -- held because it says "send".
The screen when it was asked for:
App: com.google.android.apps.messaging
...
4 field "running late, be there at 7"
...
6 image "Send SMS"
```

The yes does exactly that tap. `confirm` reads the screen again and
looks for the held thing by kind, label and place, as a tap always
does (note 01). If the screen moved while the person read the card,
nothing is tapped. A yes works once. A hold lapses after ten minutes
and lives only in the server's memory, so what was going to be typed
into a password field never touches the disk, and the card says "(a
password; not shown)".

The command line is never held. `sparsh tap` is the person's own hand.

## Enter is a Send button, sometimes

Writing up the refusal above turned up a way round: in a chat app with
"Enter to send" turned on, `press_key enter` (or `type_text` with
`enter`) sends the message, and nothing held it. The model had been
*told* not to go round a hold, but a rule the model keeps isn't a rule.

**ENTER IS HELD WHERE A TAP WOULD BE.** While anything on the screen
would itself be held (a Send button, Post, Reply, Pay), Enter is held
too, and the card says why:

```
NOT DONE -- this needs the person's yes: press enter in
com.google.android.apps.messaging -- held because enter could do what
item "Send SMS — SMS" does (it says "send").
```

That was live, in the conversation where the refused "dinner is at 8"
was still in the box. Back and Home are never held.

**BESIDE THE FIELD, NOT ANYWHERE ON THE SCREEN.** At first Enter was
held while *anything* on the screen would be, on the theory that one
extra yes is the cheap side to be wrong on. The phone trial
([Yantra's notes/120](https://github.com/kunwarmahen/yantra/blob/main/notes/120-thirteen-tasks-on-a-phone.md))
found the cost. Chrome's new tab puts a news feed under the address bar,
and its rows say "Share ...". Every `example.com` + Enter was held. Told
no, `gemma4:26b` tapped Chrome's suggestion instead: through, but round
the no.

Enter presses what sits next to the field being typed into: Send beside
the message box, Post under a reply. So with a field focused, only
things in its row count, give or take the field's own height. The Share
row far down the feed doesn't count; Messages' Send does, even though
Messages reads it as a row (`item`), not a button. With no field
focused, anything on the screen still counts.

## Off limits

The person can also keep the agent out of an app entirely
(`never = ["com.chase.*"]` in `~/.sparsh/rules.toml`). Such an app
can't be opened, isn't in `list_apps`, and if the agent lands in it
anyway (a notification, a link) its screen comes back empty:

```
App: com.chase.sig.android
(this app is off limits: the person's rules keep the agent out of it, so
nothing on it is shown. Press back or home to leave.)
```

Keys are never refused. Back and Home are the way out.

**THE PERSON'S FILE, NOT THE MODEL'S.** No tool reads or writes the rules
beyond what `status` reports. A model that could edit its own list of
words to ask about would have no list.

## What the first live run found

The first run of the SMS task on `qwen3.8:latest` failed in two
instructive ways, both fixed before this was committed.

**The model said `ref`.** Yantra's browser tools take an element as
`ref`, and the model carried the habit over:
`type_text({"ref": "4", "text": "running late, be there at 7"})`. The
server ignored the unknown key and typed with no field focused. The
words went nowhere, and the next screen still showed the field's hint.
Two rules came out of it:

* **UNKNOWN ARGUMENTS ARE ERRORS**, and the error names the right key:
  `type_text has no argument `ref` -- use `into``. On the next try the
  model used `into`.
* **TYPING NEEDS A FIELD.** For an agent, typing with no field focused
  is refused ("no field has the keyboard, so nothing was typed"), rather
  than lost while the agent reads the next screen as if it had landed.
  Text that can't be typed at all (é, emoji) is refused before anything
  is tapped.

**"Send to 5554" was held.** Messages' contact picker labels the row
for a number "Send to 5554 — 5554". Tapping it chooses who the message
goes to; it sends nothing. Held, it cost a yes before the message was
even written. "Send" followed by "to" is now not held. The real Send
button, labelled "Send SMS", still is.

## Written down

The agent's last message is its own account of what it did ("Done -- the
text was sent"). A person reading it afterwards deserves the phone's
account too. **EVERY ACT IS WRITTEN DOWN, HOWEVER IT ENDED**: each tap,
typing, scroll, key, app opened and confirm goes into
`~/.sparsh/phones/<serial>/actions.jsonl`, with who asked for it (the
agent, or "you" on the command line), the line it was aimed at as it
was read, how it ended (`done`, `held`, `changed`, `not_done`), why if
not done, and the screen it led to. Held and refused steps are the
point: a log of successes alone would read as if nothing was ever
stopped.

Looks aren't written down; they change nothing. Text typed into a
password field is `(hidden)`, here as on the card. The newest 500 steps
are kept, so the file never grows without end. `sparsh log` reads it:

```
10:15:07 agent press_key keys=["enter"] -> held (h39b833: enter could do what item "Send SMS — SMS" does (it says "send"))
10:15:07 agent open_app name="whatsapp" -> not_done (no app matches 'whatsapp'. ...)
```

## Live receipt

The Android 15 emulator, headless, booted clean; Yantra on
`qwen3.8:latest`, no other sibling connected:

```
$ yantra --provider ollama --model qwen3.8:latest \
    --prompt "Using the Messages app on my phone, send a text to 5554 saying: running late, be there at 7"
sparsh: 9 tool(s); phone emulator-5554 (sdk_gphone64_x86_64) -- via .../sparsh
→ open_app {"name": "messages"}        welcome screen
→ tap {"n": 2}                         "Use Messages without an account"
→ tap {"n": 6}                         "Start chat"
→ type_text {"into": 4, "text": "5554"}
→ tap {"n": 5}                         "Send to 5554 — 5554" (not held)
→ type_text {"into": 5, "text": "running late, be there at 7"}
→ tap {"n": 6}                         NOT DONE ... "Send SMS" ... hold "h68873c"
→ confirm {"hold": "h68873c"}          the card above; y
Done -- the text "running late, be there at 7" was sent to 5554 (SMS).
── end_turn · 31395 in / 504 out · 9 iteration(s)
```

Nine model calls, one question, about two minutes. The phone's own
message store agrees:

```
$ adb shell content query --uri content://sms --projection address,body,type
Row: 0 address=5554, body=running late, be there at 7, type=2
```

(`type=2` is a sent message.)

The same model turned Airplane mode on with no questions at all: six
calls, 55 seconds, through Settings search, then read back "Airplane
mode is on" from the Internet page.

And the no. The same task with a different message, answered `n`:

```
→ tap {"n": 5}                         NOT DONE ... "Send SMS — SMS" ... hold "h939cb3"
→ confirm {"hold": "h939cb3"}          the card; n
mcp__sparsh__confirm was denied: you said no at the approval prompt.
It looks like you declined the send, so I left the message ready but
unsent. "dinner is at 8" is still sitting in the text box to 5554 --
just tell me if you'd like to send it, edit it, or clear it.
── end_turn · 19622 in / 590 out · 6 iteration(s)
```

It didn't try again, press Enter in the field, or look for another
button. The message store still holds only the first message.

## What is not here yet

* A phone for runs nobody is watching. A scheduled run would have its
  held steps refused, and its everyday steps done on a phone no one is
  looking at. Yantra gives such runs no phone at all for now.
* The trial: the same tasks on several local models, and on a cloud
  model, counted. Two tasks on one model is a receipt, not a measure.
* Screenshots through the agent's tools, for apps whose screens don't
  describe themselves.
