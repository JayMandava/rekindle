import pytest

from rekindle.models import Route, Status
from rekindle.routing import TRUST_WARMUP, TrustState, route
from rekindle.models import Risk, Verification


def V(conf=0.9, passed=True):
    return Verification(passed=passed, confidence=conf)


def test_router_policy():
    cold, warm = TrustState(), TrustState(approved_unedited=TRUST_WARMUP)
    assert route(V(), Risk(tier="low"), cold)[0] == Route.needs_review          # warm-up: human first
    assert route(V(), Risk(tier="low"), warm)[0] == Route.auto_send
    assert route(V(), Risk(tier="medium"), warm)[0] == Route.needs_review
    assert route(V(), Risk(tier="high"), warm)[0] == Route.needs_review
    assert route(V(0.5), Risk(tier="low"), warm)[0] == Route.needs_review
    assert route(V(0.95, passed=False), Risk(tier="low"), warm)[0] == Route.blocked


def test_trust_threshold_learns():
    t = TrustState()
    start = t.threshold
    for _ in range(10):
        t.record("approved")
    assert t.threshold < start and t.threshold >= 0.70
    low = t.threshold
    t.record("edited"); t.record("rejected")
    assert t.threshold > low
    for _ in range(100):
        t.record("rejected")
    assert t.threshold <= 0.95


def test_nothing_auto_sends_during_warmup(engine):
    out = engine.run_campaign(limit=30)
    assert out["auto_sent"] == 0 and out["drafted"] == 30
    assert engine.sender.outbox == []


def test_approve_sends_and_cooldown_blocks_repeat(engine):
    engine.run_campaign(limit=5)
    d = next(x for x in engine.store.list_drafts() if x.route == Route.needs_review)
    sent = engine.decide(d.id, "approve")
    assert sent.status == Status.sent and len(engine.sender.outbox) == 1
    assert "Reply STOP" in engine.sender.outbox[0]["body"] or "STOP" in engine.sender.outbox[0]["body"]
    again = engine.run_campaign(limit=500)
    assert again["skipped_cooldown"] >= 5          # pending + recently contacted are not re-drafted
    ids = [x.customer_id for x in engine.store.list_drafts()]
    assert len(ids) == len(set(ids))


def test_edit_must_pass_guardrail(engine):
    engine.run_campaign(limit=3)
    d = next(x for x in engine.store.list_drafts() if x.route == Route.needs_review)
    with pytest.raises(ValueError, match="fails fact verification"):
        engine.decide(d.id, "edit", text=d.text + " Enjoy 50% off!")
    assert engine.store.get_draft(d.id).status == Status.pending
    ok = engine.decide(d.id, "edit", text=d.text + " Warm wishes.")
    assert ok.status == Status.sent and ok.decision == "edited"


def test_stop_suppresses_before_generation_and_cancels_queue(engine):
    engine.run_campaign(limit=10)
    d = engine.store.list_drafts()[0]
    res = engine.inbound("STOP", customer_id=d.customer_id)
    assert res["intent"] == "stop" and res["cancelled_drafts"] == 1
    assert engine.store.get_draft(d.id).status == Status.rejected
    with pytest.raises(ValueError):
        engine.decide(d.id, "approve")
    out = engine.run_campaign(limit=500)
    assert out["skipped_suppressed"] >= 1
    assert all(x.customer_id != d.customer_id or x.id == d.id for x in engine.store.list_drafts())


def test_hindi_stop_and_send_time_gate(engine):
    engine.run_campaign(limit=10)
    d = engine.store.list_drafts()[1]
    engine.store.suppress(d.customer_id, "test")         # e.g. suppression written by another process
    engine._send(d, "approved")
    assert engine.store.get_draft(d.id).status == Status.rejected and engine.sender.outbox == []
    assert engine.inbound("रोको", customer_id=engine.store.list_drafts()[2].customer_id)["intent"] == "stop"


def test_blocked_draft_cannot_be_approved_unchanged():
    from datetime import date
    from rekindle.config import Settings
    from rekindle.engine import Engine
    e = Engine.build(Settings(mode="local", chaos=1.0, as_of=date(2026, 10, 18)))
    e.drafter.chaos = 1.0
    e.drafter._clean_on_retry = staticmethod(lambda t: False)   # force persistent bad drafts
    e.run_campaign(limit=40)
    blocked = [x for x in e.store.list_drafts() if x.route == Route.blocked]
    assert blocked, "chaos drafts should be blocked by the guardrail"
    with pytest.raises(ValueError):
        e.decide(blocked[0].id, "approve")
    assert e.sender.outbox == []


def test_orders_attributed_within_window(engine):
    engine.run_campaign(limit=3)
    d = next(x for x in engine.store.list_drafts() if x.route == Route.needs_review)
    engine.decide(d.id, "approve")
    engine.record_order(d.customer_id, 9000.0, "Sitter session")
    other = next(x for x in engine.store.list_drafts() if x.status == Status.pending)
    engine.record_order(other.customer_id, 5000.0, "Annual album")   # never contacted -> not attributed
    k = engine.kpis()
    assert k["recovered_revenue"] == 9000.0 and k["converted_customers"] == 1
