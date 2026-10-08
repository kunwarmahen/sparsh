"""What waits for a yes, and what never happens at all.

The bias these tests encode: A HELD STEP IS NOT DONE, AND ITS YES DOES
EXACTLY IT. The failures guarded against are a risky tap that slips
through (a word missed, a field the keyboard was already in), a yes
that does something else (the screen moved between the question and
the answer), and an off-limits app read anyway -- through `look`, a
number, or the app list. Every test checks what the phone received.
"""

import pytest

from sparsh import SparshError
from sparsh.phone import Held, Phone, ScreenChanged
from sparsh.rules import ASK_WORDS, AppRule, Rules, load
from sparsh.screen import Element


def el(label: str, **kw) -> Element:
    return Element(n=1, kind="button", label=label, bounds=(0, 0, 100, 100), tap=True, **kw)


@pytest.mark.parametrize(
    "label", ["Send", "Send SMS — SMS", "Place order", "Delete account", "PAY NOW", "Allow"]
)
def test_words_that_act_are_held(label):
    assert Rules().why_tap(el(label))


@pytest.mark.parametrize(
    "label", ["Orders", "Sender", "Settings", "Network & internet", "", "Send to 5554 — 5554"]
)
def test_whole_words_only(label):
    assert Rules().why_tap(el(label)) is None


def test_the_persons_file_adds_and_removes_words_and_names_apps(tmp_path):
    (tmp_path / "rules.toml").write_text(
        'ask = ["Archive"]\ndont_ask = ["share"]\nnever = ["com.chase.*"]\n'
    )
    rules, path = load(tmp_path)
    assert path == tmp_path / "rules.toml"
    assert rules.why_tap(el("Archive")) and not rules.why_tap(el("Share"))
    assert rules.forbidden("com.chase.sig.android") and not rules.forbidden("com.android.settings")


def test_no_file_is_the_defaults(tmp_path):
    rules, _ = load(tmp_path)
    assert rules.ask == ASK_WORDS and rules.never == ()


@pytest.mark.parametrize("text", ['never = "com.x"', "asks = []", "never = [", "ask = [1]"])
def test_a_wrong_file_is_a_sentence(tmp_path, text):
    (tmp_path / "rules.toml").write_text(text)
    with pytest.raises(SparshError, match="rules.toml"):
        load(tmp_path)


# -- held on the phone -------------------------------------------------------

SEND = (
    "<?xml version='1.0' ?><hierarchy rotation=\"0\">"
    '<node index="0" text="" resource-id="" class="android.widget.FrameLayout" '
    'package="com.google.android.apps.messaging" content-desc="" checkable="false" '
    'checked="false" clickable="false" enabled="true" focusable="false" focused="false" '
    'scrollable="false" long-clickable="false" password="false" selected="false" '
    'bounds="[0,0][1080,2400]">'
    '<node index="0" text="running late" resource-id="compose" class="android.widget.EditText" '
    'package="com.google.android.apps.messaging" content-desc="" checkable="false" '
    'checked="false" clickable="true" enabled="true" focusable="true" focused="true" '
    'scrollable="false" long-clickable="true" password="false" selected="false" '
    'bounds="[0,2000][900,2200]" />'
    '<node index="1" text="" resource-id="send" class="android.widget.ImageButton" '
    'package="com.google.android.apps.messaging" content-desc="Send SMS" checkable="false" '
    'checked="false" clickable="true" enabled="true" focusable="true" focused="false" '
    'scrollable="false" long-clickable="false" password="false" selected="false" '
    'bounds="[900,2000][1080,2200]" />'
    '<node index="2" text="" resource-id="pin" class="android.widget.EditText" '
    'package="com.google.android.apps.messaging" content-desc="" checkable="false" '
    'checked="false" clickable="true" enabled="true" focusable="true" focused="false" '
    'scrollable="false" long-clickable="false" password="true" selected="false" '
    'bounds="[0,100][1080,300]" />'
    "</node></hierarchy>"
)


@pytest.fixture
def guarded(fake, tmp_path):
    fake.screens["send"] = SEND
    fake.current = "send"
    return Phone(fake, state=tmp_path, settle=0, rules=Rules(never=("com.chase.*",)))


def test_a_send_is_held_and_nothing_reaches_the_phone(guarded, fake):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.tap(2)
    assert fake.actions == []
    said = str(caught.value)
    assert said.startswith("NOT DONE") and 'button "Send SMS"' in said
    assert caught.value.hold.id in said


def test_the_yes_does_that_tap(guarded, fake):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.tap(2)
    guarded.confirm(caught.value.hold.id)
    assert fake.actions == [("tap", 990, 2100)]


def test_a_yes_works_once(guarded):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.tap(2)
    guarded.confirm(caught.value.hold.id)
    with pytest.raises(SparshError, match="no step is waiting"):
        guarded.confirm(caught.value.hold.id)


def test_a_yes_for_a_screen_that_moved_does_nothing(guarded, fake):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.tap(2)
    fake.current = "settings"
    with pytest.raises(ScreenChanged):
        guarded.confirm(caught.value.hold.id)
    assert fake.actions == []


def test_the_person_reads_what_the_screen_said(guarded):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.tap(2)
    told = guarded.held(caught.value.hold.id).describe("emulator-5554")
    assert told.startswith("On the phone emulator-5554: tap button")
    assert '"running late"' in told  # the message that would be sent


def test_typing_into_a_password_field_is_held_and_never_shown(guarded, fake):
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.type("hunter2", into=3)
    assert fake.actions == []
    assert "hunter2" not in str(caught.value)
    assert "hunter2" not in guarded.held(caught.value.hold.id).describe("x")
    guarded.confirm(caught.value.hold.id)
    assert ("text", "hunter2") in fake.actions


def test_typing_where_the_keyboard_already_is_checks_that_field(guarded, fake):
    # The PIN field (the last node) has the keyboard, not the message box.
    moved = SEND.replace('focused="true"', 'focused="false"')
    head, _, tail = moved.rpartition('focused="false"')
    fake.screens["pin"] = head + 'focused="true"' + tail
    fake.current = "pin"
    with pytest.raises(Held):
        guarded.type("1234")
    assert fake.actions == []


def test_ordinary_typing_is_not_held(guarded, fake):
    guarded.look()
    guarded.type(" -- sorry", into=1)
    assert ("text", " -- sorry") in fake.actions


def test_the_command_line_is_never_held(fake, tmp_path):
    fake.screens["send"] = SEND
    fake.current = "send"
    hands = Phone(fake, state=tmp_path, settle=0)
    hands.look()
    hands.tap(2)
    assert fake.actions == [("tap", 990, 2100)]


def test_an_app_off_limits_is_not_opened_listed_or_read(guarded, fake, tmp_path):
    fake.installed.append("com.chase.sig.android")
    with pytest.raises(SparshError, match="off limits"):
        guarded.open_app("com.chase.sig.android")
    assert "com.chase.sig.android" not in guarded.apps()
    fake.screens["bank"] = SEND.replace(
        "com.google.android.apps.messaging", "com.chase.sig.android"
    )
    fake.current = "bank"
    shown = guarded.look()
    assert shown.elements == [] and "off limits" in shown.text()
    assert "running late" not in shown.text()
    with pytest.raises(SparshError, match="off limits"):
        guarded.tap(1)
    guarded.key("back")  # the way out is always open
    assert fake.actions == [("keys", "back")]


def test_typing_with_no_field_to_take_it_is_refused(guarded, fake):
    # The words would be lost, and the next screen read as if they landed.
    fake.screens["nofocus"] = SEND.replace('focused="true"', 'focused="false"')
    fake.current = "nofocus"
    with pytest.raises(SparshError, match="no field has the keyboard"):
        guarded.type("hello")
    assert fake.actions == []


def test_enter_is_held_where_a_send_button_is(guarded, fake):
    # "Enter to send" makes Enter the Send button; the code, not the
    # model's manners, keeps it from going round the hold.
    guarded.look()
    with pytest.raises(Held) as caught:
        guarded.key("enter")
    assert fake.actions == []
    assert 'enter could do what button "Send SMS"' in str(caught.value)
    with pytest.raises(Held):
        guarded.type("see you", into=1, enter=True)
    assert fake.actions == []
    guarded.confirm(caught.value.hold.id)
    assert fake.actions == [("keys", "enter")]


def test_enter_runs_where_nothing_would_be_held(guarded, fake):
    fake.current = "settings_search_typed"
    guarded.look()
    guarded.key("enter")
    guarded.type("wifi", into=2, enter=True)
    assert ("keys", "enter") in fake.actions and ("text", "wifi") in fake.actions


def test_a_feed_row_saying_share_does_not_hold_enter(guarded, fake):
    # Chrome's new tab: the field being typed in, and far below it a news
    # feed whose rows say "Share ...". Enter goes to the field's address.
    fake.screens["feed"] = SEND.replace(
        'class="android.widget.ImageButton" package="com.google.android.apps.messaging" '
        'content-desc="Send SMS"',
        'class="android.view.ViewGroup" package="com.google.android.apps.messaging" '
        'content-desc="Share Raleigh puts data centers on notice"',
    ).replace('bounds="[900,2000][1080,2200]"', 'bounds="[0,600][1080,900]"')
    fake.current = "feed"
    guarded.look()
    guarded.type("example.com", into=1, enter=True)
    assert fake.actions[-1] == ("keys", "enter")


def test_a_send_row_beside_the_box_holds_enter_whatever_it_is_called(guarded, fake):
    # Messages reads its Send as a row ("item"), not a button: still held.
    fake.screens["row"] = SEND.replace(
        'class="android.widget.ImageButton"', 'class="android.view.ViewGroup"'
    )
    fake.current = "row"
    guarded.look()
    with pytest.raises(Held):
        guarded.key("enter")
    assert fake.actions == []


def test_back_is_never_held(guarded, fake):
    guarded.look()
    guarded.key("back")
    assert fake.actions == [("keys", "back")]


# -- rules a harness added for one app ($SPARSH_APP_RULES) -------------------

MESSAGES = "com.google.android.apps.messaging"


def app_guarded(fake, tmp_path, **rule):
    fake.screens["send"] = SEND
    fake.current = "send"
    rules = Rules(apps={MESSAGES: AppRule(**rule)})
    return Phone(fake, state=tmp_path, settle=0, rules=rules)


def test_a_word_refused_for_an_app_is_not_done_and_no_yes_gets_through(fake, tmp_path):
    phone = app_guarded(fake, tmp_path, refuse=("send",), why="Setu: Messages is Read only")
    phone.look()
    with pytest.raises(SparshError, match="not done here: Setu: Messages is Read only") as e:
        phone.tap(2)
    assert not isinstance(e.value, Held) and fake.actions == []
    with pytest.raises(SparshError, match="enter could do what a tap would"):
        phone.key("enter")
    assert fake.actions == []


def test_a_word_an_app_asks_about_is_held(fake, tmp_path):
    phone = app_guarded(fake, tmp_path, ask=("running",))
    phone.look()
    with pytest.raises(Held):
        phone.tap(1)  # the message box says "running late"
    assert fake.actions == []


def test_the_rule_is_only_for_its_app(fake, tmp_path):
    phone = Phone(
        fake,
        state=tmp_path,
        settle=0,
        rules=Rules(apps={"com.twitter.android": AppRule(refuse=("network",))}),
    )
    phone.look()  # Settings
    phone.tap(6)  # Network & internet
    assert fake.actions == [("tap", 540, 820)]


def test_an_apps_pace_is_kept_between_steps(fake, tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr("sparsh.phone.time.sleep", lambda s: slept.append(s))
    phone = app_guarded(fake, tmp_path, pace=3.0)
    phone.look()
    phone.tap(3)
    phone.look()
    phone.tap(3)
    assert len(slept) == 1 and 2.5 < slept[0] <= 3.0


def test_rules_arrive_as_json_and_a_bad_one_is_a_sentence(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARSH_APP_RULES", '{"com.x": {"refuse": ["Post"], "pace": 3}}')
    rules, _ = load(tmp_path)
    assert rules.apps == {"com.x": AppRule(refuse=("post",), pace=3.0)}
    for bad, said in (
        ("{nope", "not JSON"),
        ('{"com.x": {"allow": ["post"]}}', "takes refuse"),
        ('{"com.x": {"refuse": "post"}}', "list of words"),
    ):
        monkeypatch.setenv("SPARSH_APP_RULES", bad)
        with pytest.raises(SparshError, match=said):
            load(tmp_path)


# -- a schedule's grants: a held tap done without a yes, narrowly --------


def granted(fake, tmp_path, *sentences):
    from sparsh.rules import grant

    fake.screens["send"] = SEND
    fake.current = "send"
    return Phone(fake, state=tmp_path, settle=0,
                 rules=Rules(grants=tuple(grant(s) for s in sentences)))  # fmt: skip


def test_a_grant_lets_its_send_through_while_its_text_is_on_the_screen(fake, tmp_path):
    phone = granted(fake, tmp_path, "send in Messages when the screen shows running late")
    phone.look()
    screen = phone.tap(2)
    assert fake.actions == [("tap", 990, 2100)]
    assert 'the schedule allows "send in Messages when the screen shows running late"' in (
        screen.text()
    )


def test_a_grant_whose_text_is_not_on_the_screen_still_holds(fake, tmp_path):
    phone = granted(fake, tmp_path, "send in Messages when the screen shows 555-0123")
    phone.look()
    with pytest.raises(Held):
        phone.tap(2)
    assert fake.actions == []


def test_a_grant_for_another_app_or_word_still_holds(fake, tmp_path):
    for sentence in (
        "send in YouTube when the screen shows running late",
        "delete in Messages when the screen shows running late",
    ):
        phone = granted(fake, tmp_path, sentence)
        phone.look()
        with pytest.raises(Held):
            phone.tap(2)
    assert fake.actions == []


def test_a_grant_never_covers_a_password(fake, tmp_path):
    phone = granted(fake, tmp_path, "send in Messages when the screen shows running late")
    phone.look()
    with pytest.raises(Held):
        phone.type("1234", into=3)


def test_a_grant_that_cant_be_read_is_an_error_not_dropped():
    from sparsh.rules import grants

    assert grants('["send in Messages when the screen shows 555-0123"]')[0].shows == "555-0123"
    for bad in ('["send to 555-0123"]', '"send"', "not json", "[3]"):
        with pytest.raises(SparshError):
            grants(bad)


def test_the_phone_says_whether_a_schedule_may_use_it(fake, tmp_path):
    phone = Phone(fake, state=tmp_path, settle=0)
    for on, locked, state in (
        (True, False, "in_use"),
        (False, True, "locked"),
        (True, True, "locked"),
        (False, False, "asleep"),
    ):
        fake.screen_on, fake.locked = on, locked
        assert phone.state()["state"] == state
    fake.screen_on, fake.locked = None, False  # an iPhone says only "locked"
    assert phone.state()["state"] == "unknown"


def test_a_step_done_under_a_grant_says_so_in_the_log(fake, tmp_path):
    from sparsh import log

    phone = granted(fake, tmp_path, "send in Messages when the screen shows running late")
    phone.look()
    log.recorded(phone, "agent", "tap", {"n": 2}, lambda: phone.tap(2))
    step = log.recent(phone, 1)[0]
    assert step["outcome"] == "done"
    assert step["said"] == 'granted ahead: "send in Messages when the screen shows running late"'
    log.recorded(phone, "agent", "look", {}, phone.look)
    assert "said" not in log.recent(phone, 1)[0]  # said once, not carried over
