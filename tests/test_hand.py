"""The person's own hand, read while they show the agent a job.

The bias these tests encode: SAY WHAT WAS SEEN, AND NO MORE. A tap is
named only from a screen that was actually read before it; a tap after
the screen moved is said as a tap at a spot, plainly unnamed. Keys are
counted, never read -- what was typed comes off the screen. A phone that
shows no fingers (an iPhone) says so, and hands over both screens rather
than guessing. And the person's steps land in the same log as the
agent's, by "you".
"""

from sparsh import log, mcp
from sparsh.hand import Gesture, described, gestures, scale_of, touchscreen
from sparsh.phone import Phone
from sparsh.rules import Rules
from sparsh.screen import read

from .conftest import screen

#: A tap on the Nexus 6P, as ``getevent -lt /dev/input/event1`` prints it.
TAP = """\
[   61046.716370] EV_ABS       ABS_MT_TRACKING_ID   00000a2f
[   61046.716370] EV_ABS       ABS_MT_POSITION_X    000001a0
[   61046.716370] EV_ABS       ABS_MT_POSITION_Y    00000600
[   61046.716370] EV_KEY       BTN_TOUCH            DOWN
[   61046.716370] EV_SYN       SYN_REPORT           00000000
[   61046.790000] EV_ABS       ABS_MT_TRACKING_ID   ffffffff
[   61046.790000] EV_KEY       BTN_TOUCH            UP
[   61046.790000] EV_SYN       SYN_REPORT           00000000
"""

SWIPE = """\
[   10.000000] /dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   00000001
[   10.000000] /dev/input/event1: EV_ABS       ABS_MT_POSITION_X    00000200
[   10.000000] /dev/input/event1: EV_ABS       ABS_MT_POSITION_Y    00000800
[   10.100000] /dev/input/event1: EV_ABS       ABS_MT_POSITION_Y    00000400
[   10.200000] /dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   ffffffff
"""

HELD = TAP.replace("61046.790000", "61047.900000")

CAPABILITIES = """\
add device 1: /dev/input/event2
  name:     "gpio-keys"
  events:
    KEY (0001): KEY_VOLUMEDOWN
add device 2: /dev/input/event1
  name:     "synaptics_dsx"
  events:
    ABS (0003): ABS_MT_SLOT           : value 0, min 0, max 9, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_X     : value 0, min 0, max 1439, fuzz 0, flat 0, resolution 0
                ABS_MT_POSITION_Y     : value 0, min 0, max 2559, fuzz 0, flat 0, resolution 0
"""


def test_a_tap_a_swipe_and_a_long_press_are_read_off_the_events():
    assert gestures(TAP.splitlines()) == [Gesture("tap", 416, 1536, 416, 1536)]
    swipe, = gestures(SWIPE.splitlines())
    assert swipe.kind == "swipe" and swipe.direction() == "up"
    assert gestures(HELD.splitlines())[0].kind == "long_press"


def test_a_second_finger_is_not_followed():
    two = TAP.replace("ABS_MT_TRACKING_ID   00000a2f",
                      "ABS_MT_SLOT          00000001\n[ 1.0] EV_ABS ABS_MT_POSITION_X 00000fff\n"
                      "[ 1.0] EV_ABS ABS_MT_SLOT 00000000\n"
                      "[   61046.716370] EV_ABS       ABS_MT_TRACKING_ID   00000a2f")
    assert gestures(two.splitlines())[0].x == 416


def test_the_touchscreen_and_its_scale_come_from_the_phone():
    assert touchscreen(CAPABILITIES) == "/dev/input/event1"
    assert scale_of(CAPABILITIES, "Physical size: 1440x2560") == (1.0, 1.0)
    assert scale_of(CAPABILITIES, "Physical size: 1440x2560\nOverride size: 720x1280") \
        == (0.5, 0.5)
    assert scale_of("", "Physical size: 1440x2560") == (1.0, 1.0)


def test_a_tap_is_named_from_the_screen_it_landed_on():
    home = read(screen("home"))
    (_, words, on), = described([Gesture("tap", 400, 1500, 400, 1500)], home, None)
    assert words.startswith("tapped") and '"Gmail' in words and on and "Gmail" in on


def test_only_the_first_step_is_named_and_keys_are_counted():
    home = read(screen("home"))
    keyboard = (0, 1500, 1080, 2400)
    found = [Gesture("tap", 400, 1450, 400, 1450),        # Gmail, read
             Gesture("tap", 100, 1600, 100, 1600),        # keys
             Gesture("tap", 300, 1700, 300, 1700),
             Gesture("tap", 400, 1450, 400, 1450)]        # after the screen moved
    steps = [words for _, words, _ in described(found, home, keyboard)]
    assert '"Gmail' in steps[0]
    assert steps[1].startswith("typed on the keyboard (2 key(s)")
    assert "the screen had moved on" in steps[2] and "Gmail" not in steps[2]


def tools(fake, tmp_path):
    return mcp.Tools(Rules(), state=tmp_path, device=fake, settle=0)


def test_watched_says_what_the_person_did_and_logs_it_as_theirs(fake, tmp_path):
    fake.current = "home"
    t = tools(fake, tmp_path)
    assert "Gmail" in t.call("watch_phone", {})
    fake.hand.append(Gesture("tap", 400, 1500, 400, 1500))
    fake.current = "settings"
    said = t.call("watched", {})
    assert said.startswith("What the person did since the last look")
    assert "1. tapped" in said and "Gmail" in said and "Network & internet" in said
    entry, = log.recent(Phone(fake, state=tmp_path, settle=0), 1)
    assert entry["by"] == "you" and entry["action"] == "tap" and "Gmail" in entry["on"]
    assert "Nothing was touched" in t.call("watched", {})   # settings is the new before


def test_an_iphone_hands_over_both_screens(fake, tmp_path):
    fake.hand = None                                    # shows no fingers
    fake.current = "home"
    t = tools(fake, tmp_path)
    t.call("watch_phone", {})
    fake.current = "settings"
    said = t.call("watched", {})
    assert "doesn't show where it is touched" in said
    assert said.index("The phone before:") < said.index("Gmail") < said.index("The phone now:")
    assert log.recent(Phone(fake, state=tmp_path, settle=0), 1) == []


def test_watched_before_watch_phone_starts_and_says_so(fake, tmp_path):
    said = tools(fake, tmp_path).call("watched", {})
    assert said.startswith("I wasn't watching yet")
