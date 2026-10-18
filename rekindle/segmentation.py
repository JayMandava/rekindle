"""Turns SQL segment rows into outreach targets with grounded facts (deterministic, no LLM)."""
from __future__ import annotations

from datetime import date, timedelta

from .config import Merchant
from .models import Fact, Target

SKIP_SEGMENTS = {"active"}


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def next_milestone(anchor: date, as_of: date, merchant: Merchant):
    """Next milestone (months since anchor) falling in [as_of, as_of+window]. Returns (months, date) or None."""
    for months in merchant.milestone_months:
        due = _add_months(anchor, months)
        if as_of <= due <= as_of + timedelta(days=merchant.milestone_window_days):
            return months, due
    return None


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _ordinal_months(m: int) -> str:
    return "1 year" if m == 12 else "2 years" if m == 24 else "18 months" if m == 18 else f"{m} months"


def build_targets(rows: list[dict], as_of: date, merchant: Merchant) -> list[Target]:
    ltvs = sorted(r["monetary"] for r in rows)
    vip_cut = ltvs[int(len(ltvs) * 0.9)] if ltvs else float("inf")
    targets: list[Target] = []
    for r in rows:
        anchor = date.fromisoformat(r["anchor_date"]) if r.get("anchor_date") else None
        ms = next_milestone(anchor, as_of, merchant) if anchor else None
        segment = r["segment"]
        if ms and r["recency_days"] >= 45:
            segment = "milestone_due"
        elif segment in SKIP_SEGMENTS:
            continue
        wa = bool(r["consent_whatsapp"]) and bool(r.get("phone"))
        em = bool(r["consent_email"]) and bool(r.get("email"))
        if not (wa or em):
            continue  # consent first: no consented channel, no outreach, no draft
        first = r["name"].split()[0]
        facts = [
            Fact(id="F1", label="Customer first name", value=first),
            Fact(id="F2", label="Last session", value=f"{r['last_product']} on {_fmt(date.fromisoformat(r['last_order_date']))}"),
            Fact(id="F3", label="Sessions booked so far", value=str(r["frequency"])),
        ]
        milestone_label = None
        if r.get("anchor_name"):
            facts.append(Fact(id="F4", label="Child's first name", value=r["anchor_name"]))
        if ms:
            months, due = ms
            milestone_label = f"{r['anchor_name']} turns {_ordinal_months(months)} on {_fmt(due)}"
            facts.append(Fact(id="F5", label="Upcoming milestone", value=milestone_label))
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
            priority=round(priority, 3), vip=r["monetary"] >= vip_cut, milestone_label=milestone_label, facts=facts,
        ))
    targets.sort(key=lambda t: -t.priority)
    return targets


def segment_summary(rows: list[dict], as_of: date, merchant: Merchant) -> dict:
    """Counts for the whole base (including active), plus milestone overlay."""
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["segment"]] = counts.get(r["segment"], 0) + 1
    ms = 0
    for r in rows:
        if r.get("anchor_date") and r["recency_days"] >= 45 and next_milestone(date.fromisoformat(r["anchor_date"]), as_of, merchant):
            ms += 1
    counts["milestone_due"] = ms
    return counts
