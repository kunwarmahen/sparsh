# 19 — The battery and missed calls, without the screen

A morning brief wants two things from the phone: is the battery low, and
did anyone call. Before this note, the only way to get either was to
work the screen: open Settings → Battery and read the percentage, then
open the Phone app's Recents and read the rows. That is a phone job.
Someone has to be sure nobody is using the phone, it has to be awake,
and if it's locked its person is asked to unlock it, so that an agent
could read one number.

`phone_status` reads both from the phone's own records, with no tap
and nothing on the screen changed:

```
Battery: 23%, not charging.
Missed calls (1 new): 5550100.
```

## Where each comes from

**Android.** The battery is `dumpsys battery`: `level`, and `status` 2
(charging) or 5 (full) counted as charging. The missed calls are the
call log, through the content provider adb can reach:

```
content query --uri content://call_log/calls --projection number:name:date --where 'type=3 AND new=1'
```

Type 3 is a missed call. `new=1` means the person hasn't looked at it
yet, which is what "missed" means to them. A missed call they've
already seen isn't news. A contact's name is used when the log has one,
and the number otherwise.

**The quotes are the bug that was found.** adb hands the phone's shell
its words joined by spaces. Unquoted, `type=3 AND new=1` reached the
phone as three words, and the query read nothing. On the Android 15
emulator that looked exactly like a phone that keeps its call log
private. A test now checks that the filter goes out quoted.

**When a phone won't say.** Some Android builds keep the call log from
adb. Then the answer is *"Missed calls: this phone doesn't let them be
read."*, never *"none"*. "None" would be a claim, and here nothing was
read at all.

**iPhone.** WebDriverAgent has `/wda/batteryInfo` (a level from 0 to 1,
and a state: 2 charging, 3 full), asked inside the session, with the
sessionless path as a fallback. An iPhone lets nothing read its calls,
so an iPhone's answer says the battery and that its calls can't be
read.

## A read, and only a read

`phone_status` is annotated `readOnlyHint`, so a harness runs it
without asking. Nothing is logged as an act, because nothing was done.
It doesn't look at the screen, so it doesn't need the phone awake.
A host that knows a package admits this tool and none of the screen's
can give it the phone on any run. Dvara does that for a schedule, with
no phone job (its note 63).

## Receipt

The Android emulator (`Medium_Phone_API_35`). A call placed and
dropped with `adb emu gsm call 5550100` / `gsm cancel`, and the battery
set with `adb emu power capacity 23`, `ac off`, `status discharging`.
Then over MCP:

```
{"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text":
 "Battery: 23%, not charging.\nMissed calls: this phone doesn't let them be read."}], ...}}
```

That was the unquoted filter. The same query typed by hand returned the
row (`number=5550100, type=3, new=1`). Quoted:

```
{"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text":
 "Battery: 23%, not charging.\nMissed calls (1 new): 5550100."}], ...}}
```

Not tried here: a real Nexus (it wasn't on the network) and a real
iPhone's battery through WebDriverAgent. The iPhone path is tested
against a fake WebDriverAgent that answers `batteryInfo`.

## What was deliberately not built

* **Marking missed calls as seen.** The person's phone tells them about
  their calls, and an agent clearing that badge would be taking
  something away from them.
* **Voicemail, texts, notifications.** Each is a different record, and
  most belong to an app rather than to the phone. A watch on the
  notification (Prahari's inlet) is the road for those.
