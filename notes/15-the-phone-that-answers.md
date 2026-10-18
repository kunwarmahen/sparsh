# The phone that answers, not the one written down

An iPhone was put in a drawer and an Android plugged into the same
cable. Every list still said one phone, *"iPhone, not answering --
start WebDriverAgent on it"*. The Android was on the desk, on the cable,
and nothing could reach it. Two things kept it out. The first was
Sparsh's own rule for choosing a phone. The second was where the
containers that work the phone run.

## A place to ask, not an answer

`$SPARSH_WDA` says where an iPhone's WebDriverAgent would answer. It
was set once, when the iPhone was set up (Sarathi writes it as
`[phone] wda`), and `pick` took it as the phone whenever it was set:

```python
serial = serial or os.environ.get("ANDROID_SERIAL") or os.environ.get("SPARSH_WDA") or None
if is_wda(serial):
    return WdaDevice(serial)
```

That made sense with one phone. It was also the reason Sarathi refused a
settings file with both an Android and an iPhone in it: both written
down meant "the iPhone", quietly. But a setting written once can't say
which phone is plugged in today.

**THE PHONE THAT ANSWERS IS THE PHONE.** Now `$SPARSH_WDA` is a place to
ask. When no phone is named (`--serial`, `$ANDROID_SERIAL`), the
iPhone there and the Androids adb sees are asked alike, and the one that
answers is used:

* one answers: that one;
* two answer: said, not guessed. *"more than one phone answers
  (84B7N16128001616 (Nexus_6P), http://127.0.0.1:8100 (iPhone)); unplug
  one, or choose with --serial"*. Several phones at once is a plan of its
  own, not a tie to break here;
* none answers: the iPhone, if one was named, is still handed back, so
  the first call says why it isn't answering. Otherwise the old
  sentences about no phone, or one not ready.

The MCP server already picks the phone on every call, not once at
start, so a phone swapped in the middle of a session is the one the
next tap goes to. The price is one quick ask of WebDriverAgent's
`/status` per call when an iPhone is named. A refused connection on this
computer costs nothing; an address that doesn't answer is given 3
seconds.

## A cable the containers can't see

Sarathi's containers run Sparsh too, and a container can't see the USB
cable. An Android reached them only over Wi-Fi (`$SPARSH_CONNECT`):
Wireless debugging on, and after every restart of the phone the cable
again (`sparsh tcpip`, [note 11](11-the-phone-that-stopped-listening.md)).
The iPhone didn't have that problem, because WebDriverAgent's port is
forwarded to this computer, and a container reaches this computer.

The cable belongs to one adb server anyway, the one on this computer.
Handing a container the whole USB bus would give it every device on it,
and its own adb server would fight this one for the phone. adb's client
can be pointed at a server somewhere else:
`ADB_SERVER_SOCKET=tcp:host:5037`. It can also be pointed at a Unix
socket, `ADB_SERVER_SOCKET=localfilesystem:/path`.

**A FILE, NOT A PORT.** `sparsh adb-share` (adbshare.py) listens on
`~/.sparsh/adb.sock`, mode 0600, and passes each connection through to
the adb server on `127.0.0.1:5037`. Whoever reaches adb can work the
phone. A port a container reaches is on this computer's house address
(that is where `host.containers.internal` points), so it would be open
to the house as well. A file belongs to its owner, and `~/.sparsh` is
already mounted into the containers that work the phone. The server
stays the one every program here uses, so `adb devices` on this computer
works as before, and `adb start-server` is run once if nothing is
listening yet.

## LIVE RECEIPT

The Nexus 6P on the cable, `SPARSH_WDA` still naming the iPhone that
was put away, on this computer:

```
$ SPARSH_WDA=http://127.0.0.1:8100 sparsh look --peek
App: com.android.systemui
(The phone is locked: this is its lock screen, not the app asked for. Ask its person to unlock it, then look again.)
1 image "Photos notification:"
```

Before, the same command went to the iPhone and failed. Then the share,
and adb inside Sarathi's Dvara container, which had seen only the
iPhone:

```
$ sparsh adb-share --socket ~/.sparsh/adb-try.sock
sharing adb at /home/mahen/.sparsh/adb-try.sock; in a container: ADB_SERVER_SOCKET=localfilesystem:/home/mahen/.sparsh/adb-try.sock

$ ls -l ~/.sparsh/adb-try.sock
srw------- 1 mahen mahen 0 Oct 18 09:20 /home/mahen/.sparsh/adb-try.sock

$ podman exec sarathi-dvara sh -c 'ADB_SERVER_SOCKET=localfilesystem:/home/mahen/.sparsh/adb-try.sock adb devices -l'
List of devices attached
84B7N16128001616       device usb:1-9 product:angler model:Nexus_6P device:angler transport_id:1

$ podman exec sarathi-dvara sh -c 'ADB_SERVER_SOCKET=… adb shell getprop ro.build.version.release'
8.1.0
```

On this computer, `adb devices` still listed the phone, and the socket
file went away when the share was stopped (SIGTERM, as systemd stops
it). Sarathi starts the share as `sarathi-adb` and gives the containers
the variable (Sarathi's notes/20).

## What the tests hold

`tests/test_plug_and_play.py`: an Android in the iPhone's place is the
phone; the iPhone is the phone when it answers and no Android does; two
that answer are named, both of them; nothing answering hands back the
named iPhone; no adb on this computer still finds the iPhone; a named
Android is used even with an iPhone answering. A connection on the file
reaches adb and comes back; only its owner can open the file; one left
by an earlier run is replaced, and anything else at that path is left
alone; with nothing listening yet, adb is started, and the connection is
closed rather than left hanging.

## What is not here yet

* Two phones answering at once, both used. Today that is refused with
  both names (the several-phones plan).
* A phone over Wi-Fi with a cable phone beside it: both answer, so it is
  refused like any two.
