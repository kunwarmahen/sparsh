# An app not on the list, found the way a person finds it

On an iPhone, Sparsh opens an app by its name in a list. WebDriverAgent
can't tell an app that isn't installed from one that isn't running, so
the list is read over the cable by go-ios, every 5 minutes while `sparsh
iphone` runs ([note 12](12-a-real-iphone.md)). That list is missing
apps in three cases: an app installed in the last few minutes; a phone
whose list was never read, because WebDriverAgent is reached some other
way; and a name the list holds differently. Each was answered *"no app
matches"*, which an agent passes on as "it isn't installed". WhatsApp was
the first ([note 12](12-a-real-iphone.md)).

A person who can't find an app on the home screen swipes down and types
its name. Spotlight finds anything installed, with no list.

## What it does

When the list has no app by that name, and only then, on an iPhone
(`WdaDevice.search_open`):

1. home, then a swipe down from the middle of the home screen: Spotlight;
2. the name typed into its field;
3. the screen read, up to four times, for a result whose label **is**
   that name (case aside);
4. a tap on it, an icon first if the name is on several, and then a
   check that an app is in front, not the home screen.

**WORD FOR WORD, OR NOT AT ALL.** "WhatsApp Busi" is not "WhatsApp
Business", and "Bank" is not "Bank of America". The wrong app opened is
worse than none, so a near match is not tapped. The search field, the
keyboard and its keys say the name too, and are never the result.

**RETURN IS NEVER PRESSED.** On a name that matches no app, Return in
Spotlight searches the web. A name that finds nothing ends at the home
screen with *"no app called 'X' on this iPhone (looked in Spotlight
too)"*.

**THE RULES STILL HOLD.** The app's bundle is known only once it is in
front. An app the person's rules keep the agent out of is left for
home at once, before anything on it is read, and the open fails with the
same words as any app off limits.

What was found is added to `iphone-apps.json`, so the next open finds it
on the list. The next read over the cable replaces the whole file, and
has the app anyway.

## LIVE RECEIPT

Built while the iPhone was in a drawer and the Android on the cable
([note 15](15-the-phone-that-answers.md)), so the Spotlight screen in
`tests/screens/ios/spotlight.xml` is written by hand in WDA's shape.
Then run on the real iPhone 17, from the containers: an app not on the
list was asked for by name, found in Spotlight and opened. A real
Spotlight screen can still take the hand-written one's place.

## What the tests hold

In `tests/test_iphone.py`, against a stand-in WebDriverAgent: an app not
on the list is opened from Spotlight (the icon tapped, not the field,
a key or "WhatsApp Business"), said to have been found there, and kept,
so the next open finds it on the list; a near match is not tapped and the
phone is left at home; the name is typed once and Return never sent; an
app the rules keep out is left for home.

## What is not here yet

* A real Spotlight screen in the tests, from the iPhone 17 (the open
  itself has run there).
* Android. It asks the phone for its apps on every open, so it has no
  list to fall behind.
