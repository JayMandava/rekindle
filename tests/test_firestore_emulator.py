"""Runs only when the Firebase Firestore emulator is up (skipped otherwise):

    firebase emulators:start --only firestore --project demo-rekindle      # terminal 1
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 GOOGLE_CLOUD_PROJECT=demo-rekindle python -m pytest tests/test_firestore_emulator.py

Needs no credentials and no billing. Verifies FirestoreStore persistence end to end.
"""
import os
from datetime import date

import pytest

from rekindle.config import Settings
from rekindle.engine import Engine
from rekindle.models import Route, Status

pytestmark = pytest.mark.skipif(not os.getenv("FIRESTORE_EMULATOR_HOST"), reason="Firestore emulator not running")


def build():
    return Engine.build(Settings(mode="local", store="firestore", chaos=0.0, as_of=date(2026, 10, 18),
                                 project=os.getenv("GOOGLE_CLOUD_PROJECT", "demo-rekindle")))


def test_state_survives_a_restart():
    e = build()
    before = len(e.store.list_drafts())
    e.run_campaign(limit=6)
    d = next(x for x in e.store.list_drafts() if x.route == Route.needs_review and x.status == Status.pending)
    assert e.decide(d.id, "approve").status == Status.sent
    victim = next(x for x in e.store.list_drafts() if x.status == Status.pending)
    assert e.inbound("STOP", customer_id=victim.customer_id)["intent"] == "stop"

    e2 = build()                                                    # a brand-new engine, same Firestore
    assert len(e2.store.list_drafts()) >= before + 6
    assert victim.customer_id in e2.store.suppressed()
    assert e2.store.get_draft(d.id).status == Status.sent
    assert e2.store.get_trust().approved_unedited >= 1
    assert any(ev["kind"] == "opt_out" for ev in e2.store.list_events())
    assert e2.run_campaign(limit=500)["skipped_suppressed"] >= 1    # suppression is honoured after the restart
