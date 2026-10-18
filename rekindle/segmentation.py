"""Turns SQL segment rows into outreach targets with grounded facts (deterministic, no LLM)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .babytrails import SHOOT_LABEL
from .config import Merchant
from .models import Fact, Target

SKIP_SEGMENTS = {"active"}


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def journey_trigger(r: dict, as_of: date, merchant: Merchant) -> Optional[tuple[str, str]]:
    """The next natural session for this family, from an ESTIMATED birth date. Returns (kind, label) or None.

    Never fires for customers with no usable age (e.g. maternity-only history): we do not infer a baby.
    """
    if not r.get("anchor_date"):
        return None
    dob = date.fromisoformat(r["anchor_date"])
    age = (as_of - dob).days
    who = r.get("anchor_name") or "Your baby"
    lo, hi = merchant.newborn_to_baby_days
    if r.get("last_shoot_type") == "newborn" and lo <= age <= hi:
        return "age", f"{who} is about {round(age / 30.4375)} months old"
    first_bday = dob + timedelta(days=365)
    if as_of <= first_bday <= as_of + timedelta(days=merchant.birthday_window_days):
        return "birthday", f"{who} turns 1 in {first_bday.strftime('%B %Y')}"
    return None


def build_targets(rows: list[dict], as_of: date, merchant: Merchant) -> list[Target]:
    ltvs = sorted(r["monetary"] for r in rows)
    vip_cut = ltvs[int(len(ltvs) * 0.9)] if ltvs else float("inf")
    targets: list[Target] = []
    for r in rows:
        trig = journey_trigger(r, as_of, merchant)
        segment = r["segment"]
        if trig and r["recency_days"] >= 45:
            segment = "milestone_due"
        elif segment in SKIP_SEGMENTS:
            continue
        wa = bool(r["consent_whatsapp"]) and bool(r.get("phone"))
        em = bool(r["consent_email"]) and bool(r.get("email"))
        if not (wa or em):
            continue  # consent first: no opted-in channel, no outreach, no draft
        first = r["name"].split()[0]
        stype = r.get("last_shoot_type") or ""
        last = f"{SHOOT_LABEL.get(stype, r['last_product'])} session on {_fmt(date.fromisoformat(r['last_order_date']))}"
        facts = [
            Fact(id="F1", label="Customer first name", value=first),
            Fact(id="F2", label="Last session", value=last),
            Fact(id="F3", label="Sessions booked so far", value=str(r["frequency"])),
        ]
        if r.get("anchor_name"):
            facts.append(Fact(id="F4", label="Child's first name", value=r["anchor_name"]))
        milestone_label = None
        if trig:
            kind, milestone_label = trig
            facts.append(Fact(id="F5", label="Upcoming milestone (estimated)", value=milestone_label))
            if kind == "age":
                facts.append(Fact(id="F6", label="Studio offering", value=merchant.baby_session_fact))
        priority = (r["r_score"] * 0.2 + r["f_score"] * 0.35 + r["m_score"] * 0.45) / 5
        if segment == "milestone_due":
            priority += 0.25
        targets.append(Target(
            customer_id=r["customer_id"], name=r["name"], first_name=first, language=r.get("language") or "en",
            phone=r.get("phone") or None, email=r.get("email") or None,
            consent_whatsapp=wa, consent_email=em, segment=segment,
            r_score=r["r_score"], f_score=r["f_score"], m_score=r["m_score"],
            recency_days=r["recency_days"], frequency=r["frequency"], monetary=r["monetary"],
            last_order_date=date.fromisoformat(r["last_order_date"]), last_product=r["last_product"],
            last_shoot_type=stype, priority=round(priority, 3), vip=r["monetary"] >= vip_cut,
            milestone_label=milestone_label, facts=facts,
        ))
    targets.sort(key=lambda t: -t.priority)
    return targets


def segment_summary(rows: list[dict], as_of: date, merchant: Merchant) -> dict:
    """Counts for the whole base (including active), plus the milestone overlay."""
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["segment"]] = counts.get(r["segment"], 0) + 1
    counts["milestone_due"] = sum(1 for r in rows if r["recency_days"] >= 45 and journey_trigger(r, as_of, merchant))
    return counts


def consent_summary(rows: list[dict]) -> dict:
    return {"opted_in": sum(1 for r in rows if r["consent_whatsapp"] and r.get("phone")), "total": len(rows)}
