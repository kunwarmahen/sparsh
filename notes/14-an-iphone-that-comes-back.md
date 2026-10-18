# 14 — An iPhone that comes back

*[Note 12](12-a-real-iphone.md) got WebDriverAgent running on a real
iPhone from Linux. Then the phone was unplugged and updated, and getting
it back took four tries, a certificate, and someone who knew go-ios.*

## Unplugged, then updated

An iPhone 17 was unplugged from the Linux computer, which stopped
WebDriverAgent (WDA): the phone's "Automation Running" banner went
away. Meanwhile the phone was updated to iOS 27.0.1. Plugged back in,
the start script got as far as WDA itself:

```
== starting WebDriverAgent (com.mahensingh.sparsh.WebDriverAgentRunner.xctrunner)
{"level":"ERROR","msg":"Failed running WDA","error":"runXUITestWithBundleIdsXcode15Ctx:
 cannot create a tunnel connection to testmanagerd: ConnectToServiceTunnelIface: service
 'com.apple.dt.testmanagerd.remote' is not available in RSD. If it is provided by the
 developer disk image, make sure a recent image is mounted (run `ios image auto`)"}
```

The words are go-ios's, and they are right: the tools WDA runs on live
on a *developer disk image* that is mounted onto the phone, and each
iOS version needs its own. An update leaves the phone with none. A
replug or a restart does too. Doing what the error said failed next:

```
$ ios image auto
{"msg":"downloading image","url":"https://deviceboxhq.com/ddi-17E5179g.zip"}
{"msg":"no existing device-side manifest, requesting new signature from Apple TSS"}
{"level":"ERROR","msg":"error mounting image","err":"MountImage: failed to get signature
 from Apple: getSignature: failed to send request: Post \"https://gs.apple.com/TSS/
 controller?action=2\": tls: failed to verify certificate: x509: certificate signed by
 unknown authority"}
```

The image has to be signed for this one phone by Apple's server. That
server's certificate is real, but it chains to Apple's own root, which
Linux's list of trusted roots doesn't include:

```
$ openssl s_client -connect gs.apple.com:443 -showcerts
 0 s:CN = gs.apple.com, O = Apple Inc.
   i:CN = Apple Server Authentication CA
 1 s:CN = Apple Server Authentication CA
   i:CN = Apple Root CA
 2 s:CN = Apple Root CA          <- self-signed, and not in /etc/ssl/certs
```

With Apple Root CA, downloaded from apple.com and checked against its
published SHA-256, `B0:B1:73:0E…:10:01:F0:24`, added to the bundle
go-ios reads for that one step (`SSL_CERT_FILE`), the image mounted and
WDA started:

```
{"msg":"success mounting image","image":"devimages/ddi-17E5179g/Restore"}
```

Nobody should have to work that out from a phone they just updated.

## One command

`sparsh iphone` (wdastart.py) does every step, in the order they
depend on each other, and says the one thing to do when a step can't go
on:

* **The tunnel.** iOS 17 and later reach developer tools only through a
  tunnel. One already running is used. Otherwise one is started in
  go-ios's *userspace* mode, which needs no `sudo`. The old script used
  `sudo`, which kept starting the phone a job for a person at a terminal.
* **The image, every start.** Mounted each time, because once it is
  mounted that costs nothing, and "is the right one mounted?" is
  exactly the question nobody thinks to ask. Apple's root ships with
  Sparsh (`apple-root-ca.pem`). Its SHA-256 is checked before every use,
  and it goes to go-ios for this step only. Nothing is added to the
  computer's own trust store.
* **WDA found on the phone.** The one app named
  `*.WebDriverAgentRunner.xctrunner` is the one to start. The old
  `PREFIX=` was a name to remember and type right.
* **It waits for the phone.** When WDA stops because the phone went
  away, this waits, and starts it all again when the phone is plugged
  back in. An unplug costs a replug and nothing else.
* **Failures in plain words.** A developer the phone doesn't trust yet
  ("could not get pid") becomes the Settings path to tap. A tunnel
  from before an update (the RSD error again, even with the image
  mounted) gets a new one. Three starts that never answer give up, with
  go-ios's last words and where the rest of them are.

`sparsh iphone --background` runs it behind and returns once the phone
answers. That is what Sarathi's **Use the iPhone** button,
`sarathi phone iphone` and `sarathi up` call (Sarathi's notes/19).
`sparsh iphone --stop` stops it. `scripts/start-wda-from-linux.sh` is
now a line that runs `sparsh iphone`, so steps already written down
still work.

## LIVE RECEIPT

On the iPhone 17 on iOS 27.0.1, each step the command runs, against the
real phone and with WDA left running:

```
phone 00008150-000C236C36C0C01C
ios 27
tunnelled True
mounted ok
bundle com.mahensingh.sparsh.WebDriverAgentRunner.xctrunner
```

The image, mounted with Apple's root from inside Sparsh, is kept in
`~/.sparsh/devimages/ddi-17E5179g`.

The first whole run, with the `sudo` tunnel stopped, failed three times:

```
starting WebDriverAgent (com.mahensingh.sparsh.WebDriverAgentRunner.xctrunner)
WebDriverAgent didn't start (... Cannot connect to com.apple.dt.testmanagerd.remote,
 missing tunnel address and RSD port. To start the tunnel, run `ios tunnel start`); trying again
```

No tunnel was started, because Sparsh thought one was running. With no
tunnel, `ios tunnel ls` still prints a log line that names the phone,
`{"msg":"no udid specified using first device in list","udid":"00008150-…"}`,
and Sparsh had looked for the phone's ID anywhere in the output. Now
only the list counts: an entry with this phone's ID and an address.
"Missing tunnel address" also gets a new tunnel. Run again, with no
`sudo` anywhere:

```
$ sparsh iphone --background
starting the iPhone behind (what it says: /home/mahen/.sparsh/iphone.log)
the iPhone is ready: SPARSH_WDA=http://127.0.0.1:8100

$ cat ~/.sparsh/iphone.log
starting the developer tunnel (iOS 17 and later)
starting WebDriverAgent (com.mahensingh.sparsh.WebDriverAgentRunner.xctrunner)
the iPhone is ready: SPARSH_WDA=http://127.0.0.1:8100

$ SPARSH_WDA=http://127.0.0.1:8100 sparsh look --peek
App: com.apple.springboard
1 item "Contacts (Widget, Stack)" [tap]
2 item "news folder (3 apps)" [tap]
```

The tunnel it started is `ios tunnel start --userspace`, run as the person.

## What the tests hold

`tests/test_wdastart.py` runs the steps against `ios` as a small
script. Apple's root is added to this computer's roots, and a changed
root is refused. The image is mounted with that bundle on every start,
even when a tunnel was already running. WDA's name is read from the
phone, and a phone without it is told how to install it. A log line
naming the phone is not a tunnel. With no tunnel, one is started
without `sudo`. The RSD error, again and again,
gets a new tunnel and gives up after three tries with go-ios's own
words. "Could not get pid" becomes the Settings path to tap.

## What is not here yet

* ~~A whole start by `sparsh iphone` on the real phone, with no `sudo`
  tunnel.~~ Run above, after the fix for the tunnel it thought it saw.
* ~~The phone unplugged and plugged back in while `sparsh iphone`
  runs.~~ Run on the iPhone 17: unplugged, it waited; plugged back in
  and unlocked, it was ready again. Sarathi's **Use the iPhone** button
  started it in its `sarathi-iphone` unit (Sarathi's notes/19).
* More than one iPhone. The first one go-ios lists is the one started.
* The image after an iOS that go-ios doesn't know yet. go-ios picks the
  image by version, and only a newer go-ios can mount it.
