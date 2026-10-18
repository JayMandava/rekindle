import pytest

from rekindle.consent import classify_reply_offline, is_stop


@pytest.mark.parametrize("t", ["STOP", "stop.", " Unsubscribe ", "रोको", "बंद करो", "停止", "やめて", "நிறுத்து", "Please don't message me again", "berhenti"])
def test_stop_detected(t):
    assert is_stop(t)


@pytest.mark.parametrize("t", ["Please don't stop the album order", "Yes please", "How much?", "when can we come"])
def test_normal_replies_are_not_stop(t):
    assert not is_stop(t)


def test_offline_intents():
    assert classify_reply_offline("Yes please, any slot this weekend?") == "interested"
    assert classify_reply_offline("How much is it?") == "question"
    assert classify_reply_offline("STOP") == "stop"
