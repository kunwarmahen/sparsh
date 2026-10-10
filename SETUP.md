# Setting up a phone for Sparsh, step by step

Sparsh lets an AI agent use a phone the way you do: read what's on the
screen, tap, type, scroll and open apps. Before it can, the phone has
to let a computer drive it. Android and iPhone do that very
differently, so this guide has a part for each.

**Pick one to start with:**

| | Android emulator | Android phone | iPhone |
|---|---|---|---|
| What you need | a Linux computer | an Android phone and a USB cable | an iPhone, a USB cable, and a Mac for one step |
| How long, the first time | 20 minutes (most of it downloading) | 10 minutes | about an hour |
| Afterwards | start the emulator and go | plug in and go | the Mac's signature lasts 7 days with a free Apple ID; then a 5-minute rebuild |
| Good for | trying Sparsh with nothing at risk | real apps you already use | the same, on an iPhone |
| Status | tested | tested on a Nexus 6P (Android 8.1), cable and Wi-Fi ([notes/08](notes/08-a-real-phone.md)) | **written and tested against a stand-in, not yet run on a real iPhone** |

If you've never used Sparsh, start with the emulator. To check a phone
works with an agent in one go, [Part T](#part-t--test-it-end-to-end-one-recipe-per-phone)
has a copy-and-paste test for each. It's a pretend
phone in a window on your computer: nothing an agent does to it can
touch your real messages, money or accounts.

> **What an agent can see.** Anything on a phone's screen can be read:
> messages, emails, names, one-time codes. Sparsh holds the risky steps
> for your yes (Send, Pay, Delete, typing a password; see the README's
> "What it asks you first"), but it still *reads* whatever is on the
> screen. Use the emulator or a spare phone until you trust it.

---

## Step 0 · Install Sparsh (everyone)

You need [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
and `git`.

```
git clone https://github.com/kunwarmahen/sparsh
cd sparsh
uv sync
uv run sparsh --help
```

Sparsh has no other dependencies. Every command below is run from this
`sparsh` folder (`uv run sparsh` is how you call it from here).

**So that agents find it by themselves**, put `sparsh` on your `PATH`
with one link (the same way Setu's install does):

```
mkdir -p ~/.local/bin
ln -sf "$PWD/.venv/bin/sparsh" ~/.local/bin/sparsh
which sparsh                       # ~/.local/bin/sparsh
```

Yantra looks for `sparsh` on `PATH`; without the link it needs
`YANTRA_SPARSH=~/sparsh/.venv/bin/sparsh` every time. Sarathi finds a
checkout beside its own without the link. Only link one: just this
folder's `sparsh`, never all of `.venv/bin` (that would put this
folder's Python first on your `PATH`).

---

## Part A · The Android emulator

### A1 · Install adb

`adb` is Android's own small program for talking to phones. Sparsh
works through it.

```
sudo apt install adb              # Debian / Ubuntu
sudo dnf install android-tools    # Fedora
```

(Android Studio, in the next step, brings its own copy too. Sparsh
finds it in `~/Android/Sdk` if there's none on your `PATH`.)

### A2 · Make a pretend phone

1. Install [Android Studio](https://developer.android.com/studio) and
   open it once. Let it download what it offers.
2. Open **Device Manager** (on the welcome screen: *More Actions →
   Virtual Device Manager*).
3. Press **+**, choose any recent phone (we test with *Medium Phone*),
   and a recent Android version (we test with Android 15, "API 35").
   Finish.

You won't need Android Studio again. To start the pretend phone from a
terminal:

```
~/Android/Sdk/emulator/emulator -list-avds          # the names of your pretend phones
~/Android/Sdk/emulator/emulator -avd Medium_Phone_API_35 -no-snapshot-save
```

`-no-snapshot-save` means anything the agent changes is thrown away
when the emulator stops, so every start is a clean phone. Add
`-no-window` to run it with no window at all.

### A3 · Check Sparsh sees it

In another terminal:

```
$ uv run sparsh devices
emulator-5554  sdk_gphone64_x86_64  device
```

Now go to [Part D](#part-d--check-it-works).

---

## Part B · A real Android phone

### B1 · Install adb

The same as [A1](#a1--install-adb).

### B2 · Let the phone be driven ("USB debugging")

Android hides this switch so nobody turns it on by accident.

1. On the phone, open **Settings → About phone**. (Samsung: **Settings
   → About phone → Software information**.)
2. Tap **Build number** seven times. The phone says *"You are now a
   developer"*. It may ask for your PIN.
3. Go back to **Settings → System → Developer options** (Samsung:
   **Settings → Developer options**, at the bottom).
4. Turn on **USB debugging**.

### B3 · Plug it in and say yes

Plug the phone into the computer with a USB cable. Some cables only
charge; if nothing happens below, try another.

The phone asks **"Allow USB debugging?"** and shows the computer's key.
Tick **Always allow from this computer** and press **Allow**.

```
$ uv run sparsh devices
R58M12ABCDE  SM_G991B  device
```

| If it says | Do this |
|---|---|
| `unauthorized` | Unlock the phone; the "Allow USB debugging?" question is waiting on its screen. |
| `offline` | Unplug it and plug it back in. |
| nothing at all | Try another cable or port; check USB debugging is still on; run `adb devices` to see what `adb` itself says. |

When the emulator is also running you'll see two lines. Then tell
Sparsh which one with `--serial R58M12ABCDE`, or
`export ANDROID_SERIAL=R58M12ABCDE`.

### B4 · Without the cable (optional)

Android 11 and later can do the same over Wi-Fi. In **Developer
options → Wireless debugging**, turn it on, choose **Pair device with
pairing code**, and on the computer:

```
uv run sparsh pair 192.168.1.23:37000 123456   # the address and code the phone shows
uv run sparsh connect 192.168.1.23:41234       # the address on the Wireless debugging page
uv run sparsh devices                          # 192.168.1.23:41234  ...  device
```

(`adb pair` and `adb connect` do the same.) To have Sparsh connect by
itself every time it looks for phones, after a restart too, set
`SPARSH_CONNECT=192.168.1.23:41234`. Sarathi's containers reach the
phone this way (Sarathi's `sarathi phone`).

The address can change when wireless debugging is turned off and on,
or the phone restarts; check the Wireless debugging page if it stops
answering.

**Android 10 and older** have no Wireless debugging page. Plug the
phone in once and tell its `adb` to listen on the network; its Wi-Fi
address is on *Settings → About phone → Status*, or:

```
adb shell ip -4 addr show wlan0                # inet 192.168.1.161/24 ...
adb tcpip 5555                                 # restarting in TCP mode port: 5555
uv run sparsh connect 192.168.1.161:5555
```

The key you allowed over the cable is the one that counts, so nothing
is paired. It lasts until the phone restarts; then plug in and run
`adb tcpip 5555` again. A Nexus 6P on Android 8.1 was driven this way,
from this computer and from inside Sarathi's containers.

Now go to [Part D](#part-d--check-it-works).

---

## Part C · An iPhone

> **Not yet run on a real iPhone.** Everything here is written and
> tested against a stand-in, but nobody has gone through it end to end
> on a real Mac and iPhone yet. If a step fails, the message it prints
> is the thing to report.

### Why an iPhone needs a Mac

An Android phone can be driven by `adb` with nothing installed on it.
An iPhone can't. The only way in is a small helper app called
**WebDriverAgent** (WDA) that runs *on the iPhone* and takes taps over
the network. Apple only lets an app onto an iPhone if it's **signed**,
and signing needs **Xcode**, which only runs on a Mac.

So the Mac does one job: build and sign WDA. Everything else happens on
Linux:

```
   Mac (once a week)            Linux (every day)               iPhone
   ┌───────────────┐   WDA.ipa  ┌──────────────────┐   USB     ┌─────────┐
   │ Xcode builds  │ ─────────▶ │ go-ios installs  │ ────────▶ │  WDA    │
   │ and signs WDA │            │ and starts WDA   │           │ :8100   │
   └───────────────┘            │                  │ ◀──────── │         │
                                │ sparsh look/tap  │   HTTP    └─────────┘
                                └──────────────────┘
```

The Mac can be someone else's, and you can
do almost all of the Mac part from Linux over the network.

**A free Apple ID is enough.** The catch is that what it signs only
opens for **7 days**; then you rebuild (C5, about five minutes). A paid
Apple Developer account ($99 a year) makes it last a year.

### C1 · On the Mac, at its keyboard (once)

These need someone at the Mac, or Screen Sharing (C2).

1. **An account for you (recommended).** If it's someone else's Mac,
   make yourself a separate user in **System Settings → Users &
   Groups**. Your Apple ID and signing keys then live in your account,
   not theirs. The Mac's owner types their password once to allow it.
2. **Remote Login** (so you can use `ssh`): **System Settings → General
   → Sharing → Remote Login**, on. Allow your user. The same panel
   shows the Mac's name, like `macbook.local`.
3. **Screen Sharing** (so you can see the Mac's screen from Linux):
   in the same panel, turn on **Screen Sharing**. Press the **ⓘ** next
   to it and turn on **VNC viewers may control screen with password**,
   and set a password. Linux's screen-sharing programs need that.
4. **Xcode**: install it from the **App Store** (it's large, around
   10–15 GB; check there's room). Open it once, accept the licence, and
   let it install its extra parts. If it offers to download the iOS
   simulator, you can skip that; building for a real phone doesn't need
   it.

### C2 · Reaching the Mac from Linux

From now on you can stay at your Linux computer.

**Its screen**, for the steps that only work in Xcode's windows:

```
sudo apt install remmina remmina-plugin-vnc     # or any VNC viewer
remmina -c vnc://macbook.local
```

Use the Screen Sharing password from C1, then log in as your user.

**A terminal on it:**

```
ssh you@macbook.local
```

If the `.local` name doesn't resolve, use the Mac's address from
**System Settings → Wi-Fi → Details**.

### C3 · Sign in to Xcode and meet the iPhone (once)

On the Mac's screen (directly, or through Remmina):

1. **Xcode → Settings → Accounts → +** → **Apple ID**, and sign in. A
   free Apple ID shows a team called *"Your Name (Personal Team)"*.
2. Select that team, press **Manage Certificates… → + → Apple
   Development**. This makes the key that signs WDA.
3. Plug the iPhone **into the Mac**, unlock it, and tap **Trust** when
   it asks about this computer. Xcode needs to have seen the phone once
   to sign an app for it.
4. On the iPhone: **Settings → Privacy & Security → Developer Mode**,
   on. The phone restarts and asks you to confirm. (The switch only
   appears after the phone has met a Mac with Xcode.)

### C4 · Build WDA (from Linux, over ssh)

On Linux, in the `sparsh` folder:

```
scp scripts/build-wda-on-mac.sh you@macbook.local:
ssh -t you@macbook.local ./build-wda-on-mac.sh
```

What it does, so nothing is a surprise:

* asks for **your Mac password** once. Signing needs the Mac's keychain
  open, and over `ssh` it's locked. This is the most common way a
  build over `ssh` fails, and the script handles it;
* downloads WebDriverAgent from Appium's GitHub;
* gives it a name that's yours (`com.<your user>.sparsh…`), because
  Apple won't sign the name it ships with;
* builds and signs it (a few minutes the first time), then packs
  `~/sparsh-wda/WDA.ipa`;
* prints the **PREFIX** it used. Write that down; Linux needs it.

| If it says | Do this |
|---|---|
| `no Apple team found` | C3 steps 1–2 aren't done: add the Apple ID and the Apple Development certificate. |
| `Xcode isn't ready` | Open Xcode once on the Mac's screen, or run `sudo xcode-select -s /Applications/Xcode.app` there. |
| `the build didn't make ...` | Run the `xcodebuild` line it prints to see Xcode's full complaint. Often the iPhone was never plugged into the Mac (C3 step 3). |

Copy the result to Linux:

```
scp you@macbook.local:sparsh-wda/WDA.ipa .
```

### C5 · Every 7 days (free Apple ID)

You don't have to keep count. The build prints the date its signature
runs out, and when you install `WDA.ipa` (C6), Sparsh reads that date
from inside it and remembers it. Two days before the end, `sparsh
devices`, `sparsh status` and Yantra's first line all say so:

```
Note: the iPhone's WebDriverAgent signature runs out Tue 14 Oct 16:02: rebuild it on the Mac before then (build-wda-on-mac.sh).
```

To check any time:

```
$ uv run sparsh wda
/home/you/sparsh/WDA.ipa: signed until Tue 14 Oct 16:02 (6.2 days left)
```

When it's time, run C4 again (nothing else needs redoing), copy the new
`WDA.ipa`, and install it (C6). If you forget, the start script refuses
a run-out one with that same sentence, instead of the phone refusing it
in Apple's words.

### C6 · Start WDA on the iPhone, from Linux

Install two things on Linux, once:

```
sudo apt install usbmuxd           # lets Linux see an iPhone over USB at all
npm install -g go-ios              # gives you the `ios` program
```

([go-ios](https://github.com/danielpaulus/go-ios) also has ready-made
downloads if you don't use npm.) Plug the iPhone **into Linux**, unlock
it, and tap **Trust**. Then:

```
PREFIX=com.you.sparsh scripts/start-wda-from-linux.sh WDA.ipa
```

with the PREFIX that C4 printed. The script:

* on iOS 17 and later, starts the developer "tunnel" Apple now
  requires. It asks for `sudo` and stays running in the background;
* installs `WDA.ipa` (leave off the file name next time if nothing was
  rebuilt);
* forwards port 8100, so `http://127.0.0.1:8100` on Linux reaches WDA
  on the phone;
* starts WDA and stays running. Leave this terminal open; Ctrl-C stops
  it.

**The first time only**, the iPhone refuses to open an app from an
unknown developer. On the iPhone: **Settings → General → VPN & Device
Management →** your Apple ID → **Trust**. Then run the script again.

### C7 · Check Sparsh sees it

In another terminal:

```
export SPARSH_WDA=http://127.0.0.1:8100
uv run sparsh devices
```

You should see a line ending `iPhone  device`. If it says `offline`,
WDA isn't running (C6).

`SPARSH_WDA` tells Sparsh which iPhone to use. Instead, you can name it
on each command with `--serial http://127.0.0.1:8100`. Any computer on
the same Wi-Fi can use the phone's own address in place of `127.0.0.1`
(**Settings → Wi-Fi → ⓘ** on the iPhone shows it).

### Or: leave the iPhone plugged into the Mac

If the Mac is always on, you can skip C6. Keep the iPhone plugged into
the Mac and run:

```
ssh -t you@macbook.local ./build-wda-on-mac.sh --run
```

It builds and starts WDA from the Mac and stays running. On Linux, use
the iPhone's Wi-Fi address: `export SPARSH_WDA=http://192.168.1.40:8100`.
It's simpler the first day, but the Mac has to stay awake.

### What's different on an iPhone

* **No Back key.** `back` is the swipe in from the left edge, which
  most apps take as back. Some screens (sheets, full-screen videos)
  don't.
* **No Recent, Search or arrow keys.** They're refused with a sentence
  that lists the keys an iPhone does have.
* **The apps list.** An iPhone won't tell a computer what's installed.
  `sparsh apps` lists Apple's own apps; add yours as bundle ids with
  `export SPARSH_IOS_APPS=com.burbn.instagram,net.whatsapp.WhatsApp`.
  `open settings`, `open messages` and other Apple apps work by name.

---

## Part D · Check it works

The same for all three phones. Open Settings and read the screen:

```
$ uv run sparsh open settings
App: com.android.settings
1 list "settings homepage container" [scroll]
2 image "Profile picture, double tap to open Google Account" [tap]
3 text "Settings"
4 item "Search settings" [tap]
5 list "main content scrollable container" [scroll]
6 item "Network & internet — Mobile, Wi‑Fi, hotspot" [tap]
7 item "Connected devices — Bluetooth, pairing" [tap]
...
```

That's what the agent reads. Every line is one thing on the screen,
with a number. Tap one by its number, and Sparsh prints the screen it
led to:

```
uv run sparsh tap 6                          # Network & internet
uv run sparsh key back
uv run sparsh look --shot /tmp/phone.png     # also a picture, to compare
```

If the list says *"nothing on this screen can be read"*, see the
README's "When the phone can't describe its screen".

---

## Part E · Hand it to an agent

### With Yantra

[Yantra](https://github.com/kunwarmahen/yantra) finds Sparsh by itself
and starts its tools when a phone is attached.

```
export YANTRA_SPARSH=~/sparsh/.venv/bin/sparsh     # where you cloned Sparsh
export SPARSH_WDA=http://127.0.0.1:8100            # iPhone only
cd ~/yantra
```

Then start Yantra on either road.

**Local road (Ollama).** Nothing leaves your computer. The agent reads
the numbered list, not pictures, so a local model can do this:

```
uv run yantra --provider ollama --model qwen3.8:latest
```

**Cloud road.** With `ANTHROPIC_API_KEY` in Yantra's `.env`:

```
uv run yantra
```

Either way, one line at the start says the phone was found:

```
sparsh: 9 tool(s); phone emulator-5554 (sdk_gphone64_x86_64) -- via /home/you/sparsh/.venv/bin/sparsh
```

Then ask in plain words: *"turn on airplane mode"*, *"what's the newest
message in Messages?"* When a step would send, pay, delete or type a
password, Yantra stops and asks you first: one sentence, and a picture
of the phone's screen with what it would tap ringed (in the terminal,
a file whose path is printed under the question).

**iPhone and Yantra:** with `SPARSH_WDA` set, the agent's tools and the
**phone** panel on Yantra's page both use the iPhone. Yantra is told
it's an iPhone (so `back` is a swipe), and its first line says when the
signature is two days from running out.

### With another agent program

Any harness that takes MCP servers (Claude Code, Cursor, …):

```json
{"mcpServers": {"sparsh": {"command": "/home/you/sparsh/.venv/bin/sparsh", "args": ["mcp"],
                           "env": {"SPARSH_WDA": "http://127.0.0.1:8100"}}}}
```

Leave out `env` for an Android phone. Allow every tool except
`confirm`, so the risky steps still come to you (README, "Letting an
agent use it").

---

## Part T · Test it end to end, one recipe per phone

Each recipe ends with the same two checks: **an agent does a harmless
task on the phone by itself**, and **a text is stopped for your yes**.
They use a local model through Ollama; with a cloud key, leave off
`--provider` and `--model`. Run the Yantra lines from your Yantra
folder, after the link in Step 0 (or with `YANTRA_SPARSH` set).

**What you should see every time:** the first lines include
`sparsh: 10 tool(s); phone <name> (...)`. No such line means Yantra
didn't find Sparsh or a phone: run `sparsh devices` to see which.

### T1 · The emulator

```
~/Android/Sdk/emulator/emulator -avd Medium_Phone_API_35 -no-snapshot-save &
adb wait-for-device
sparsh devices                     # emulator-5554  sdk_gphone64_x86_64  device

cd ~/yantra
uv run yantra --provider ollama --model gemma4:26b \
  --prompt "Turn on airplane mode on my phone."
adb shell settings get global airplane_mode_on      # 1 means it worked
adb shell cmd connectivity airplane-mode disable    # put it back

echo n | uv run yantra --provider ollama --model gemma4:26b \
  --prompt "Text 555-0123 from my phone: hello from the agent"
```

The second run stops at a card, `Do this on the phone? … tap … "Send
SMS"`, showing the message; the `n` piped in says no, and nothing is
sent. Leave off `echo n |` to answer it yourself.

### T2 · An Android phone on a USB cable

Part B first (USB debugging on, the computer allowed). Then:

```
sparsh devices                     # R58M...  SM_S911B  device
cd ~/yantra
uv run yantra --provider ollama --model gemma4:26b \
  --prompt "On my phone, open Settings and tell me what the Battery row says."
echo n | uv run yantra --provider ollama --model gemma4:26b \
  --prompt "Text <a number of yours> from my phone: hello from the agent"
```

The first answer should match your phone's Battery row. With the
emulator running as well, say which: `export ANDROID_SERIAL=R58M...`
(the name `sparsh devices` prints).

**The lock.** Lock the phone and ask the first line again. With a PIN,
the agent is told *"The phone is locked … Ask its person to unlock it"*
and says so instead of guessing. `sparsh state` says `locked`. With only
a swipe lock, `sparsh state` says `asleep` (`"pin": false` with
`--json`), and the agent's `open_app` swipes it away and carries on.

**The screen while it works.** A local model can think for longer than
the phone's screen timeout between steps. So while an agent works it,
Sparsh raises the timeout to 10 minutes, and puts yours back 2 minutes
after its last step or when it stops. Check it mid-task with `adb shell
settings get system screen_off_timeout` (`600000`, then yours again).
`SPARSH_AWAKE=always` keeps the screen on for good (a phone set aside
for the agent); `SPARSH_AWAKE=off` leaves the timeout alone (README,
Settings).

**Pictures, and the card.** With a model that can see (`qwen3.8:latest`
does), try a screen the list reads only in part, and a tap only the
picture can show:

```
uv run yantra --provider ollama --model qwen3.8:latest \
  --prompt "On my phone, search Google Maps for Indian restaurants near me and tell me the top three with their ratings."
uv run yantra --provider ollama --model qwen3.8:latest \
  --prompt "On my phone, search Google Maps for Indian restaurants, then tap the pin on the map (not the list) of the best-rated one you can see on the map, to open it, and tell me its name."
```

The first should name restaurants read off the screenshot, without
opening each row. The second stops with a question whose picture has a
pin ringed in red: open the file, check the ring, then answer. On a
Nexus 6P (Android 8.1) a yes opened the restaurant on that pin
(notes/10).

**The trial, on your own phone.** Yantra's phone trial has a set made
for a phone you use: nothing sent, nothing wiped, each switch turned and
turned back (Yantra's note 120):

```
cd ~/yantra
YANTRA_SPARSH=~/sparsh/.venv/bin/sparsh uv run python examples/phone_trial.py \
  --serial R58M... --provider ollama --model qwen3.8:latest \
  --cases examples/phone_trial_real.jsonl
```

Each task is graded by reading the phone afterwards. Stay on the cable:
one task turns Wi-Fi off. Not the emulator set's `alarm` task: it clears
the Clock app first.

### T3 · An Android phone over Wi-Fi

B4 first (wireless debugging; pair once). Then:

```
sparsh connect 192.168.1.23:41234              # the Wireless debugging page's address
export SPARSH_CONNECT=192.168.1.23:41234       # reconnect by itself from now on
export ANDROID_SERIAL=192.168.1.23:41234
sparsh devices                                 # 192.168.1.23:41234  Pixel_7  device
```

and the two Yantra lines from T2. On Android 10 or older there is no
Wireless debugging page: on the cable, `adb tcpip 5555`, then
`sparsh connect <its Wi-Fi address>:5555` (B4). If a locked phone's
dozing Wi-Fi answers `error: closed`, Sparsh connects again once by
itself.

### T4 · An iPhone

Part C first. In one terminal, leave WDA running:

```
PREFIX=com.you.sparsh scripts/start-wda-from-linux.sh
```

In another:

```
export SPARSH_WDA=http://127.0.0.1:8100
sparsh devices                     # http://127.0.0.1:8100  iPhone  device
cd ~/yantra
uv run yantra --provider ollama --model gemma4:26b \
  --prompt "On my iPhone, open Settings and tell me what the Battery row says."
echo n | uv run yantra --provider ollama --model gemma4:26b \
  --prompt "Text <a number of yours> from my iPhone: hello from the agent"
```

The first line also says `iPhone`. (Not yet run on a real iPhone: tell
us what you see.)

### Without a link or a flag: by hand

Any of the above works without the `PATH` link, by naming Sparsh:

```
YANTRA_SPARSH=~/sparsh/.venv/bin/sparsh uv run yantra ...    # this run
uv run yantra --sparsh ~/sparsh/.venv/bin/sparsh ...          # the same, as a flag
```

Or as an ordinary MCP server, in a file Yantra reads (`--mcp-config
phone.json`):

```json
{"servers": {"sparsh": {"command": "/home/you/sparsh/.venv/bin/sparsh", "args": ["mcp"]}}}
```

As a plain MCP server, Yantra can't tell Sparsh's steps apart, so it
asks before every tap, not only before `confirm`. That's fine for a
quick test; the link or `YANTRA_SPARSH` is the everyday way. In a running session, `/phone` says what's
attached and `/phone use` adds the tools for a phone plugged in after
the start.

---

## Part F · Your rules (recommended before a real phone)

`~/.sparsh/rules.toml` is yours, and no agent tool can change it. The
most useful line keeps the agent out of apps altogether:

```toml
never = ["com.chase.*", "*bank*", "com.google.android.apps.walletnfcrel"]
```

An app on that list can't be opened, and if the agent lands in it
anyway, nothing on its screen is shown. `uv run sparsh status` prints
the rules in force. The README's "Your rules" has the rest.

---

## Part G · Typing other languages (optional, Android)

On its own, Android lets a computer type only plain letters, digits and
punctuation. Ask an agent to search for *café* or write *नमस्ते* and Sparsh
says it can't, and types nothing. An iPhone doesn't need this part.

The fix is a small keyboard app called
[ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard). It's open source
(GPL-2), about 18 KB, and does one thing: it types whatever the computer
sends it. Sparsh never installs it for you. If you want it:

```
curl -LO https://github.com/senzhk/ADBKeyBoard/releases/download/v2.5-dev/keyboardservice-debug.apk
adb install keyboardservice-debug.apk
```

That's all. You don't have to switch keyboards yourself. When text
needs it, Sparsh switches to ADBKeyBoard, types, and switches straight
back to your own keyboard. It also takes ADBKeyBoard off your keyboard
list again if it wasn't there before. Plain text still goes the old way
and never touches it.

To remove it: `adb uninstall com.android.adbkeyboard`.

> **Status:** works on the Android 15 emulator and on a real Nexus 6P
> (Android 8.1): é, नमस्ते and emoji typed into Settings' search, and the
> phone's own keyboard back in place afterwards.

---

## Quick reference

| | Android | iPhone |
|---|---|---|
| Drives it | `adb` | WebDriverAgent on the phone, started by go-ios |
| Name it with | `--serial R58M...` / `ANDROID_SERIAL` | `--serial http://127.0.0.1:8100` / `SPARSH_WDA` |
| Check | `uv run sparsh devices` | the same, with `SPARSH_WDA` set |
| Every day | plug in / start the emulator | `scripts/start-wda-from-linux.sh` |
| Screen while an agent works | kept on; `SPARSH_AWAKE=always` or `off` | left to Auto-Lock |
| Other languages (é, नमस्ते, emoji) | install ADBKeyBoard once (Part G) | nothing to do |
| Every 7 days | — | `ssh -t <mac> ./build-wda-on-mac.sh`, copy `WDA.ipa`, install; `sparsh wda` says when |
