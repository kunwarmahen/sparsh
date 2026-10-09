# 04 — Typing other languages

[Note 01](01-a-list-not-a-picture.md) left one thing undone. `adb shell
input text` types plain ASCII and nothing else. Sparsh refused é,
नमस्ते and emoji with a sentence rather than typing them wrong. That was
honest, but a phone agent that can't search for *café* or write a
message in Hindi isn't much use to most of the people who own a phone.

## What Android offers on its own

Tried on the API 35 emulator, with Settings' search field focused:

* `input text 'café'` doesn't drop the é. It crashes:
  `NullPointerException: Attempt to get length of null array` inside
  `InputShellCommand.sendText`. Android can't map é to a key press, and
  the shell command doesn't check for that.
* The clipboard. `cmd clipboard` answers "No shell command
  implementation". The service is there (`service list` shows
  `clipboard: [android.content.IClipboard]`), but reaching it by `service
  call` means hand-packing a `ClipData` parcel whose shape changes
  between Android versions. That's too fragile to put under a person's
  phone.

So nothing built into Android works. **IT TAKES A KEYBOARD APP.**

## ADBKeyBoard, switched to and back

[ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard) is an input method
(a keyboard, as far as Android is concerned) that types whatever
arrives as a broadcast: `am broadcast -a ADB_INPUT_B64 --es msg <base64>`.
Because the text is base64, nothing in it can upset the shell or `am`'s
argument parsing. It's GPL-2, about 18 KB, and widely used for test
automation.

Two choices came with it.

**THE PERSON INSTALLS IT, NOT SPARSH.** A keyboard sees what's typed
through it. Putting one on someone's phone is their decision, made once
with `adb install` (SETUP.md, Part G). Sparsh only checks whether it's
there (`pm list packages com.android.adbkeyboard`). Without it, the
refusal says what to install and where. A yes is remembered for the
session. A no isn't, so installing it mid-session works on the next try.

**ONLY FOR THE TEXT THAT NEEDS IT, THEN BACK.** Plain text still goes
through `input text`, the road the trial used. For anything else,
`AdbDevice.type_text`:

1. reads the person's keyboard (`settings get secure
   default_input_method`) and whether ADBKeyBoard is on their list
   (`ime list -s`);
2. turns it on if it wasn't (`ime enable`), switches to it (`ime set`),
   and waits half a second for it to take over the field;
3. broadcasts the text in pieces of 200 letters;
4. in a `finally`, switches back to the person's keyboard and takes
   ADBKeyBoard off the list again if it wasn't on it before.

So the phone is left as it was found, even when a broadcast fails
halfway. If the person chose ADBKeyBoard as their own keyboard, it's
left alone.

A literal `%s` takes the same road. `input` reads those two letters as
a space, and that used to be refused too.

## Each phone says what it can type

The early refusal used to be one function, `typeable()`, called by
`Phone.type` before tapping the field. It refused for both phones, so
an iPhone turned down é even though WebDriverAgent types it as given.
Now the question belongs to the phone: `Device.check_text(text)` raises
or returns.

* Android: plain text passes. Anything else passes only if ADBKeyBoard
  is installed.
* iPhone: everything passes.
* The fake phone: a `keyboard` flag. It records `("keyboard", text)`
  for that road, so tests can see which way the text went.

`Phone.type` still asks before anything is tapped. **NOTHING HALF-DONE**
stays true: a refused text never leaves a field tapped and empty.

## What the tests hold

`tests/test_phone.py` has an `AdbDevice` whose shell writes commands
down instead of running them. For "café" it expects exactly: the
package check, the keyboard read, the list, enable, set, one broadcast
(`Y2Fmw6k=`), set back, disable. Plain text after that is a single
`input text`. Without the app, the package check is the only command
run, and the error names ADBKeyBoard. 124 tests before, 127 after.

## Live, on the emulator

ADBKeyBoard v2.5-dev installed with `adb install`, then Settings'
search field, Android 15 (API 35):

```
$ uv run sparsh open settings && uv run sparsh tap 4
App: com.google.android.settings.intelligence
1 button "Back" [tap]
2 field "Search settings" [tap, type, focused]
3 text "Search settings"
$ uv run sparsh type "café नमस्ते 😸"
App: com.google.android.settings.intelligence
1 button "Back" [tap]
2 field "café नमस्ते 😸" [tap, type, focused]
3 button "Clear text" [tap]
4 text "Try searching in Tips & Support"
5 text "No results for café नमस्ते 😸"
```

All of it arrived on the first try, Devanagari and the emoji included.
Half a second was enough for the keyboard to take over the field. The
phone was back on its own keyboard afterwards
(`com.google.android.inputmethod.latin/...LatinIME`).

## Not yet

~~**A real phone.**~~ A Nexus 6P on Android 8.1 typed é, नमस्ते and 👋
into Settings' search and had Gboard back afterwards
([note 08](08-a-real-phone.md)). A phone maker's own keyboard, or a
slower phone, may still need longer than half a second to hand the
field over.
