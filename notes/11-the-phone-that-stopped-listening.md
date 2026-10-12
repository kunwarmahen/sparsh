# 11 — The phone that stopped listening

*[Note 08](08-a-real-phone.md) reached an older phone over Wi-Fi: plug
it in once, `adb tcpip 5555`, then connect. It worked, until the
phone was switched off and on again.*

## "No phone yet", with the phone on the desk

A Nexus 6P on Android 8.1 was reached from Sarathi's containers at
`192.168.1.161:5555`. Its person switched it off, then on, and restarted
the containers. Yantra's phone panel said:

```
No phone yet. Plug one in with USB debugging on (and allow it on the
phone), or start the emulator, then refresh.
```

On the computer, `sparsh devices` listed the phone on its cable. In the
container, `adb devices` listed nothing at all. Two things had happened,
and neither was said anywhere:

* **The phone had stopped listening.** `adb tcpip` lasts until the
  phone restarts. Android 10 and older have no Wireless debugging page
  to turn it back on from; only the cable can.
* **Its address had moved**, from `.161` to `.160`. The containers were
  still knocking on the old one.

Sparsh did knock. `$SPARSH_CONNECT` named the address, and `attached`
connected to it before listing, as [note 08](08-a-real-phone.md) built
it to. When the connect failed, the address was just left out of the
list. An empty list is what "no phone" looks like, so the panel said
the one thing that was certainly wrong.

## A phone that was named is never silently gone

An address in `$SPARSH_CONNECT` that doesn't answer is now listed,
offline, with what brings it back:

```
$ SPARSH_CONNECT=192.168.1.161:5555 sparsh devices
84B7N16128001616  Nexus_6P  device
192.168.1.160:5555  Nexus_6P  device
192.168.1.161:5555  ?  offline  (not answering over Wi-Fi -- a phone that restarted stops listening: plug it in and run `sparsh tcpip` (its address may have changed too), or turn Wireless debugging back on)
```

The same sentence goes out in `sparsh status --json` as each phone's
`note`, and Yantra's panel shows it under the phone in place of adb's
bare state word. Adb's own `offline` hint, "unplug it and plug it back
in", is wrong for a phone with no cable. The `note` field is extra: a
harness that reads only `serial`, `state` and `model` still works.

One choice came with it. A listed address that doesn't answer is still
a listed phone, so a computer with the phone on its cable and an old
Wi-Fi address in `$SPARSH_CONNECT` would have two, and every command
would ask which. When exactly one of them is ready, it is the one
picked.

## One command, from the cable

The fix was always the same three steps: ask the phone its Wi-Fi
address, tell it to listen, connect. The order matters. Once
`adb tcpip` runs, the phone's adb restarts, and for a second or two
nothing answers on the cable or the network. So the address is read
first, while the cable still answers:

```
$ sparsh tcpip
84B7N16128001616 listens over Wi-Fi at 192.168.1.160:5555, and is connected.
The cable can come out. A restart of the phone turns this off: plug it in and run `sparsh tcpip` again.
Elsewhere (a container, another computer): SPARSH_CONNECT=192.168.1.160:5555, or `sarathi phone 192.168.1.160:5555`.
```

That is the real Nexus 6P, and the address it printed was the new one.
`--json` gives `{serial, address, connected, said}` for a program to
read; Sarathi's `sarathi phone tcpip`, and the button on its home page,
are this command and nothing more.

It only ever acts on a phone on a USB cable. The emulator is left
alone, and so are addresses and iPhones, since none of them can be told
to listen this way. When it stops, it says why in one sentence: no
phone on a cable, the phone waiting for its USB yes, or a phone that
isn't on Wi-Fi.

This works on any Android, not only old ones. Pairing over Wireless
debugging needs the phone's screen, a six-digit code and two addresses.
With the phone already on the cable, `tcpip` needs none of that.

## Why it isn't a setting

A setting would suggest it stays on. It doesn't: it lasts only until
the next restart of the phone, and nothing on a computer can turn it
back on without the cable. So it is a command to run again, and the
offline line names it every time it's needed.

## What the tests hold

`tests/test_tcpip.py`, against an `adb` made of a shell script:

* a named address that doesn't answer is listed offline, with the
  command that fixes it, in `devices` and in `status`;
* the address is read before `tcpip` runs, and `tcpip` before the
  connect;
* no phone on a cable, only the emulator, a phone waiting for its USB
  yes, and a phone with no Wi-Fi address each stop it with a sentence;
* the phone on its cable is picked over its own silent address.

## Not here yet

* The address moving is still the router's choice. A fixed address for
  the phone (a DHCP reservation, by its MAC) keeps the containers'
  `SPARSH_CONNECT` right after a restart, so only the `tcpip` step is
  left to repeat.
