"""Local-mode scenario that exercises the whole loop on the synthetic dataset.

Everything produced here is SIMULATED (owner decisions, replies, orders) and tagged so in the audit log.
It exists so the cockpit and dashboard have something to show; it is not a pilot result.
"""
from __future__ import annotations

import random

from .engine import Engine
from .models import Route, Status

PRODUCT_PRICE = {"Newborn session": 9500, "Sitter session": 7500, "Cake smash session": 11000,
                 "Family portrait session": 8500, "Maternity session": 9000, "Annual album": 4500}
REPLIES = {"interested": ["Yes please, do you have a slot this weekend?", "Yes, we would like to book"],
           "question": ["How much is the cake smash package?"],
           "not_interested": ["Not now, thanks"]}


def seed_demo(eng: Engine, seed: int = 11) -> dict:
    rng = random.Random(seed)
    log: dict = {}
    # 1) first campaign: trust-building phase, so everything lands in the owner's queue
    log["campaign_1"] = eng.run_campaign(limit=40)
    # 2) the owner works the queue: approvals, a couple of edits, a rejection (simulated)
    approved = edited = rejected = 0
    for d in [x for x in eng.store.list_drafts() if x.status == Status.pending and x.route == Route.needs_review][:24]:
        roll = rng.random()
        try:
            if roll < 0.82:
                eng.decide(d.id, "approve"); approved += 1
            elif roll < 0.94:
                eng.decide(d.id, "edit", text=d.text + " Warm wishes."); edited += 1
            else:
                eng.decide(d.id, "reject", reason="not the right tone for this family"); rejected += 1
        except ValueError:
            pass
    log["owner_decisions"] = {"approved": approved, "edited": edited, "rejected": rejected}
    # 3) second campaign: autonomy is now earned, low-risk drafts go out on their own
    log["campaign_2"] = eng.run_campaign(limit=50)
    # 4) simulated customer behaviour on messages that were sent
    sent = [d for d in eng.store.list_drafts() if d.status == Status.sent]
    replies = orders = 0
    stop_done = False
    for d in sent:
        if rng.random() < 0.24:
            intent = rng.choices(["interested", "question", "not_interested"], [0.55, 0.3, 0.15])[0]
            eng.inbound(rng.choice(REPLIES[intent]), customer_id=d.customer_id)
            replies += 1
            if intent == "interested" and rng.random() < 0.45:
                product = rng.choice(list(PRODUCT_PRICE))
                eng.record_order(d.customer_id, round(PRODUCT_PRICE[product] * rng.uniform(0.95, 1.15), 2), product)
                orders += 1
        elif not stop_done and rng.random() < 0.05:
            eng.inbound("STOP", customer_id=d.customer_id); stop_done = True
    # one non-English opt-out, to show suppression works beyond English
    lang_of = {r["customer_id"]: r.get("language") for r in eng.rows(refresh=False)}
    for d in eng.store.list_drafts():
        if d.status == Status.pending and lang_of.get(d.customer_id) == "ta":
            eng.inbound("நிறுத்து", customer_id=d.customer_id)
            break
    log["simulated"] = {"replies": replies, "orders": orders}
    return log
