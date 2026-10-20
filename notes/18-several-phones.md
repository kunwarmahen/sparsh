# Several phones, each by a name

One phone at a time was the rule until now. Two phones answering got a
refusal that named both ([note 15](15-the-phone-that-answers.md)). That
was honest, but a household doesn't have one phone. Someone keeps an
old Nexus for the agent and carries an iPhone, and the person down the
hall has a phone of their own. The agent's tools need to reach each of
them by name, and a person's agent should reach only that person's
phones.

## One server, many phones

The obvious shape is one Sparsh server per phone. It breaks everything
downstream. Two servers means two sets of tool names
(`mcp__nexus__tap`, `mcp__iphone__tap`). Every `[tools] allow` list a
person wrote, every harness's tool picker and every rule that asks
before `confirm` is written against `mcp__sparsh__*`. Each one would
have to learn the new names, and would quietly stop asking about one it
didn't learn.

**ONE SERVER, MANY PHONES.** The phones are named where the server
starts:

```
SPARSH_PHONES="nexus=192.168.1.160:5555,iphone=http://127.0.0.1:8100"
```

The name is the person's own word (lower case, digits, dashes). What
follows `=` is how the phone is reached: an Android's adb serial or
Wi-Fi address, or an iPhone's WebDriverAgent address. These are the
same words `--serial` always took. The tools keep their names. Once
more than one phone is named, every tool takes `phone`, given as one of
the names (a JSON-schema `enum`, so a model can't invent one). With
only one phone named, `phone` is never needed.

**EVERY ANSWER NAMES ITS PHONE.** Each reply starts `Phone: nexus`. A
model working two phones reads two numbered lists that look alike (two
Settings screens, both with a 6), and the first line of each says whose
it was. A call that leaves out `phone` is refused with the names:

```
Not done: which phone? Say `phone`: nexus (Android), pixel (Android)
```

The server's opening `instructions` also say how many phones there are,
and which kind each is.

## One phone's screen never steers another

A number is only good against the screen it was read from
([note 01](01-a-list-not-a-picture.md)). With two phones, the Nexus's 6
must never be checked against the iPhone's list, let alone tapped
there. **EACH PHONE KEEPS ITS OWN LAST LOOK, HOLDS, WATCH AND SCREEN
KEEPER.** The last look was already saved per phone, in its own folder
under `~/.sparsh/phones/`. What was one per server is now one per name:

* **Holds.** A held step lives on its phone, and its id finds it.
  `confirm` and `describe_hold` need only the hold id, never the phone.
  A model that names the wrong phone on a `confirm` can't send the yes
  somewhere else.
* **Watch.** The person's own hand ([note 17](17-the-persons-own-hand.md))
  is watched on the phone they're showing the job on.
* **Screen keeper.** `SPARSH_AWAKE` takes one word per phone:
  `nexus=always,iphone=working`. An old Nexus kept for the agent never
  sleeps, while the person's daily iPhone keeps its own timeout. A
  phone left out of the list gets `working`. One plain word still
  applies to every phone. `sparsh state` reads the word for its own
  phone, so only the phone set aside for the agent reads a lit screen
  as `asleep`, free for a schedule.

## A phone the server wasn't given can't be reached

The names are the whole world the server sees. A `phone` that isn't one
of them is refused before anything is asked of adb. This is how a
harness keeps one person's agent off another person's phone: it starts
that person's server with only their phones. `sparsh mcp --phone
nexus` serves only the Nexus from the phones `SPARSH_PHONES` lists, and
`--phone NAME=WHERE` names a phone outright. Who owns which phone isn't
Sparsh's to know. The harness that starts the server knows that, and
says so by what it names.

An Android named by its Wi-Fi address is reconnected to whenever phones
are looked for, the same as `SPARSH_CONNECT`, so naming it is enough.

## Unnamed is today

With no `SPARSH_PHONES` and no `--phone`, nothing changed. The phone
is the one that answers, two answering is still refused, and every
existing setup keeps working. The hand commands (`look`, `tap`,
`state`, ...) take `--phone NAME`. When several phones are named and
none is chosen, they say *"which phone? choose with --phone (nexus:
Android, pixel: Android)"*. `--serial` and `--phone` together are
refused. `sparsh devices` and `sparsh status` put the name in front
of each phone. `status --json` gains `named`, a list of
`{name, where, kind}` for each named phone, answering or not, and a
`name` on each phone it found. A harness that doesn't read these
fields loses nothing.

## LIVE RECEIPT

The Nexus 6P on the cable and the Android 15 emulator, both answering.
Under the old rule this was a refusal:

```
$ export SPARSH_PHONES="nexus=84B7N16128001616,pixel=emulator-5554"
$ sparsh devices
nexus: 84B7N16128001616  Nexus_6P  device
pixel: emulator-5554  sdk_gphone64_x86_64  device
$ sparsh look
sparsh: which phone? choose with --phone (nexus: Android, pixel: Android)
$ sparsh state --phone pixel --json
{"serial": "emulator-5554", "screen": "on", "locked": false, "pin": null, "state": "in_use", "name": "pixel"}
```

`sparsh mcp` over its own wire, one JSON-RPC line per call:

```
instructions: A phone (Android or iPhone): look, then act by number. A held step
  needs the person's yes through confirm. There are 2 phones: nexus (Android),
  pixel (Android); every tool but confirm and describe_hold says which with `phone`.
look {}                       -> Not done: which phone? Say `phone`: nexus (Android), pixel (Android)
look {phone: nexus}           -> Phone: nexus / App: com.android.systemui / 1 image "Calendar notification: ..."
look {phone: pixel}           -> Phone: pixel / App: com.google.android.apps.nexuslauncher / 1 list "workspace" [scroll]
open_app {phone: nexus, name: settings}
                              -> Phone: nexus / App: com.android.settings / 1 item "Search settings" [tap]
```

The Nexus was asleep behind a swipe lock with no PIN. `open_app` went
through the swipe and opened Settings on the Nexus, and the emulator
was untouched. The tests (`tests/test_phones.py`) cover the rest with
two fake phones. A number read on one phone and tapped on the other is
refused with *"nothing has been read from this phone yet -- look
first"*. A Send held on the "iphone" is described and confirmed by its
id alone, and only that phone is tapped. Each phone gets its own screen
timeout.

## The iPhone `sparsh iphone` serves is listed unasked

The Nexus 6P on Wi-Fi, the iPhone 17 on the cable, `sparsh iphone`
keeping WebDriverAgent up for eighteen hours, and a fresh terminal:

```
$ sparsh devices
192.168.1.160:5555  Nexus_6P  device
```

Nothing was wrong with the iPhone. Sparsh only asks for an iPhone at an
address it is given, and that shell had neither `SPARSH_WDA` nor
`SPARSH_PHONES`. So `sparsh devices` and `sparsh status` now also list
the iPhone a running `sparsh iphone` serves. They find it by its pid
file in the state folder. A pid that names no live process lists
nothing, and an iPhone already named isn't listed twice.

Not as `device`, though: as `unnamed`, with a note that says how to
name it. Yantra and Sarathi take `device` to mean ready. If an iPhone
the tools can't reach were listed as ready, the agent would be told it
can work a phone it can't. `sparsh status` now prints every phone's
note too, as `devices` always did.

LISTING, NOT PICKING. `device.pick` still asks only the phones it is
told of. If a running `sparsh iphone` made the iPhone a candidate too,
a terminal that worked the Nexus alone would be told *"two phones
answer"* the moment the iPhone was plugged in. To work the iPhone, name
it, as before:

```
$ sparsh devices
192.168.1.160:5555  Nexus_6P  device
http://127.0.0.1:8100  iPhone  unnamed  (`sparsh iphone` serves it; to work it, export SPARSH_WDA=http://127.0.0.1:8100 or name it in SPARSH_PHONES)
$ export SPARSH_PHONES="nexus=192.168.1.160:5555,iphone=http://127.0.0.1:8100"
$ sparsh devices
nexus: 192.168.1.160:5555  Nexus_6P  device
iphone: http://127.0.0.1:8100  iPhone  device
$ sparsh look --peek --phone iphone
App: com.apple.springboard
(The phone is locked: this is its lock screen, not the app asked for. ...)
$ sparsh look --peek --phone nexus
App: com.android.systemui
(The phone is locked: this is its lock screen, not the app asked for. ...)
1 image "Google notification: NXPI is up 3.4%"
```

Both real phones were read by name from one terminal. Three tests in
`tests/test_plug_and_play.py` cover a live pid (`unnamed`), a dead one
(nothing), and an iPhone that is named and served at once (`device`,
once).

## Not here yet

* ~~A real iPhone and a real Android at once.~~ Both listed and read by
  name side by side (above). A task across both hasn't run yet.
* Who owns which phone. That belongs to the harness (Dvara's people)
  and to the house's settings (Sarathi's `[phone.NAME]`), not to Sparsh.
