"""The screen kept on while the agent works the phone.

The bias these tests encode: A SCREEN THAT SLEEPS MID-TASK LOCKS THE
TASK OUT, AND THE PERSON'S OWN SETTING IS THEIRS. A spell of work keeps
the screen on; once it is over the person's own timeout comes back --
even after a server that was killed, and never over one they changed
themselves. ``always`` never puts it back, and a lit screen is then no
sign of a person. ``off`` touches nothing. A word Sparsh doesn't know
is an error, and keeping the screen on never stops a step.
"""

import pytest

from sparsh import SparshError, mcp
from sparsh.awake import FILE, NEVER_MS, WORKING_MS, Awake, mode
from sparsh.rules import Rules

from .test_mcp import call


def keeper_tools(fake, tmp_path, how="working", idle=60.0):
    keeper = Awake(how, idle=idle)
    return keeper, mcp.Tools(Rules(), state=tmp_path, device=fake, settle=0, awake=keeper)


def saved(tmp_path, serial="fake"):
    path = tmp_path / "phones" / serial / FILE
    return path.read_text().strip() if path.exists() else None


def test_working_keeps_the_screen_on_then_puts_the_persons_own_back(fake, tmp_path):
    keeper, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")
    assert fake.timeout == WORKING_MS
    assert saved(tmp_path) == "30000"
    call(tools, "scroll", direction="down")
    assert fake.timeouts == [WORKING_MS]  # set once per spell, not every step
    keeper.rest()
    assert fake.timeout == 30000
    assert saved(tmp_path) is None


def test_the_spell_ends_by_itself_when_nothing_is_done(fake, tmp_path):
    import time

    keeper, tools = keeper_tools(fake, tmp_path, idle=0.05)
    call(tools, "look")
    time.sleep(0.3)
    assert fake.timeout == 30000


def test_a_screen_already_dark_with_no_pin_is_swiped_at_the_start(fake, tmp_path):
    """The rename from Telegram: the screen went dark between steps, and
    the next step found the lock screen."""
    fake.screen_on, fake.locked, fake.pin = False, True, False
    keeper, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")
    assert ("dismiss_lock",) in fake.actions
    assert not fake.locked


def test_a_pin_is_never_opened(fake, tmp_path):
    fake.screen_on, fake.locked, fake.pin = False, True, True
    keeper, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")
    assert ("dismiss_lock",) not in fake.actions
    assert fake.timeout == WORKING_MS  # the next time it is opened, it stays open


def test_a_timeout_the_person_changed_meanwhile_is_theirs(fake, tmp_path):
    keeper, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")
    fake.timeout = 60000  # Settings -> Display -> Sleep, by hand
    keeper.rest()
    assert fake.timeout == 60000
    assert saved(tmp_path) is None


def test_a_killed_servers_timeout_comes_back_with_the_next_one(fake, tmp_path):
    first, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")  # ... and the server is killed: no rest()
    first._cancel()
    second, tools = keeper_tools(fake, tmp_path, how="off")
    call(tools, "look")
    assert fake.timeout == 30000
    assert saved(tmp_path) is None


def test_always_never_puts_it_back_and_a_lit_screen_is_free(fake, tmp_path, monkeypatch):
    from sparsh.phone import Phone

    keeper, tools = keeper_tools(fake, tmp_path, how="always")
    call(tools, "look")
    keeper.rest()
    assert fake.timeout == NEVER_MS
    assert saved(tmp_path) == "30000"  # for the day it is set back
    phone = Phone(fake, state=tmp_path, settle=0)
    assert phone.state()["state"] == "in_use"
    monkeypatch.setenv("SPARSH_AWAKE", "always")
    assert phone.state()["state"] == "asleep"
    monkeypatch.setenv("SPARSH_AWAKE", "working")
    _, tools = keeper_tools(fake, tmp_path)
    call(tools, "look")
    tools.awake.rest()
    assert fake.timeout == 30000  # always, undone


def test_off_touches_nothing(fake, tmp_path):
    keeper, tools = keeper_tools(fake, tmp_path, how="off")
    call(tools, "look")
    keeper.rest()
    assert fake.timeouts == []


def test_a_phone_that_doesnt_say_is_left_alone_and_the_step_still_runs(fake, tmp_path):
    fake.timeout = None  # an iPhone
    keeper, tools = keeper_tools(fake, tmp_path)
    text, failed = call(tools, "look")
    assert not failed and fake.timeouts == []

    def broken(ms):
        raise SparshError("adb went away")

    fake.timeout = 30000
    fake.set_screen_timeout = broken
    text, failed = call(tools, "look")
    assert not failed and "App:" in text


@pytest.mark.parametrize("raw, word", [("", "working"), (" Always ", "always"), ("off", "off")])
def test_the_setting_is_one_of_three_words(raw, word):
    assert mode(raw) == word


def test_an_unknown_word_is_an_error_not_a_guess():
    said = "SPARSH_AWAKE is 'on'; it is one of working, always, off"
    with pytest.raises(SparshError, match=said):
        mode("on")
