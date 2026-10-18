"""Orchestrates the loop: segment -> consent/suppression gate -> draft -> verify -> risk -> route -> send/queue."""
from __future__ import annotations

import json
import os
import statistics
import uuid
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .babytrails import bookings_to_rows
from .channels import Sender, make_sender
from .config import Merchant, Settings
from .datasource import BigQueryDataSource, DataSource, LocalDataSource
from .drafting import Drafter, choose_channel, make_drafter, render
from .models import Draft, DraftOut, Route, Status, Target
from .routing import assess_risk, route as route_draft
from .sample import generate
from .segmentation import build_targets, consent_summary, segment_summary
from .store import FirestoreStore, MemoryStore, Store, now
from .verifier import verify

ASSUMED_MINUTES_PER_MESSAGE = 3  # assumption used for the "time saved" KPI; shown as an assumption in the UI
ATTRIBUTION_DAYS = 30


class Engine:
    def __init__(self, settings: Settings, merchant: Merchant, ds: DataSource, store: Store, drafter: Drafter, sender: Sender):
        self.settings, self.merchant, self.ds, self.store, self.drafter, self.sender = settings, merchant, ds, store, drafter, sender
        self._rows: list[dict] = []

    # -- construction ---------------------------------------------------------------------------
    @classmethod
    def build(cls, settings: Optional[Settings] = None) -> "Engine":
        s = settings or Settings()
        m = Merchant()
        if s.is_gcp:
            return cls(s, m, BigQueryDataSource(s), FirestoreStore(s.project, s.bq_dataset), make_drafter(s), make_sender(s, m))
        if os.getenv("REKINDLE_BOOKINGS_JSON"):   # run the local cockpit on a real Baby Trails export
            c, o = bookings_to_rows(json.loads(Path(os.environ["REKINDLE_BOOKINGS_JSON"]).read_text()))
        else:
            c, o = generate(s.as_of)
        return cls(s, m, LocalDataSource(c, o), MemoryStore(), make_drafter(s), make_sender(s, m))

    # -- data -----------------------------------------------------------------------------------
    def rows(self, refresh: bool = True) -> list[dict]:
        if refresh or not self._rows:
            self._rows = self.ds.segment_rows(self.settings.as_of, self.merchant)
        return self._rows

    def segments(self) -> dict:
        return segment_summary(self.rows(), self.settings.as_of, self.merchant)

    def consent(self) -> dict:
        return consent_summary(self.rows())

    def _contact(self, customer_id: str) -> tuple[Optional[str], Optional[str]]:
        for r in self.rows(refresh=False):
            if r["customer_id"] == customer_id:
                return r.get("phone") or None, r.get("email") or None
        return None, None

    # -- campaign -------------------------------------------------------------------------------
    def run_campaign(self, limit: int = 40, segments: Optional[list[str]] = None) -> dict:
        targets = build_targets(self.rows(), self.settings.as_of, self.merchant)
        drafts = self.store.list_drafts()
        suppressed = self.store.suppressed()
        cutoff = now() - timedelta(days=self.merchant.cooldown_days)
        busy = {d.customer_id for d in drafts if d.status == Status.pending or (d.sent_at and d.sent_at >= cutoff)}
        out = {"considered": 0, "skipped_suppressed": 0, "skipped_cooldown": 0, "drafted": 0,
               "auto_sent": 0, "needs_review": 0, "blocked": 0, "retried": 0}
        for t in targets:
            if out["drafted"] >= limit:
                break
            if segments and t.segment not in segments:
                continue
            out["considered"] += 1
            if t.customer_id in suppressed:       # suppression is checked BEFORE any generation
                out["skipped_suppressed"] += 1
                continue
            if t.customer_id in busy:
                out["skipped_cooldown"] += 1
                continue
            d = self._draft_one(t, out)
            if d:
                out["drafted"] += 1
                out[{"auto_send": "auto_sent", "needs_review": "needs_review", "blocked": "blocked"}[d.route.value]] += 1
        return out

    def _draft_one(self, t: Target, counters: dict) -> Optional[Draft]:
        channel = choose_channel(t)
        if channel is None:
            return None
        langs = set(self.merchant.languages) & (getattr(self.drafter, "languages", None) or set(self.merchant.languages))
        if t.language not in langs:
            t = t.model_copy(update={"language": "en"})   # only approved template languages are sent; never pretend
        out: DraftOut = self.drafter.draft(t, channel, self.merchant)
        v = verify(out, t.facts, channel.value, self.merchant)
        if not v.passed:  # one regeneration with the verifier's reasons as feedback
            counters["retried"] += 1
            retry = self.drafter.draft(t, channel, self.merchant, feedback=v.hard_issues)
            rv = verify(retry, t.facts, channel.value, self.merchant)
            if rv.passed:
                out, v = retry, rv
            else:
                v.hard_issues = list(dict.fromkeys(v.hard_issues + rv.hard_issues))
        risk = assess_risk(t, out, self.merchant)
        trust = self.store.get_trust()
        r, why = route_draft(v, risk, trust)
        d = Draft(
            id=uuid.uuid4().hex[:12], customer_id=t.customer_id, customer_name=t.name, segment=t.segment,
            channel=channel, language=t.language, subject=out.subject, text=out.text.strip(),
            rendered=render(channel, t, out, self.merchant), claims=out.claims, facts=t.facts,
            offer_id=out.offer_id, verification=v, risk=risk, route=r, drafter=self.drafter.name,
            created_at=now(),
        )
        d.risk.reasons = d.risk.reasons + [f"route: {why}"]
        self.store.put_draft(d)
        self.store.add_event("drafted", customer_id=t.customer_id, draft_id=d.id, segment=t.segment,
                             channel=channel.value, route=r.value, risk_tier=risk.tier,
                             confidence=v.confidence, detail=why)
        if r == Route.auto_send:
            self._send(d, "auto")
        return d

    def _send(self, d: Draft, decision: str) -> None:
        phone, email = self._contact(d.customer_id)
        if d.customer_id in self.store.suppressed():       # last-moment gate, e.g. STOP arrived while queued
            d.status, d.reject_reason, d.decision = Status.rejected, "customer opted out before send", "suppressed"
            self.store.put_draft(d)
            return
        try:
            self.sender.send(d, phone, email)
        except Exception as e:  # noqa: BLE001  surface provider failures in the cockpit, never silently drop
            d.status, d.reject_reason = Status.failed, f"send failed: {e}"
            self.store.put_draft(d)
            self.store.add_event("send_failed", customer_id=d.customer_id, draft_id=d.id, detail=str(e))
            return
        d.status, d.decision, d.sent_at = Status.sent, decision, now()
        d.decided_at = d.decided_at or d.sent_at
        self.store.put_draft(d)
        self.store.add_event("sent", customer_id=d.customer_id, draft_id=d.id, segment=d.segment,
                             channel=d.channel.value, route=d.route.value, risk_tier=d.risk.tier,
                             confidence=d.verification.confidence, detail=decision)

    # -- owner decisions ------------------------------------------------------------------------
    def decide(self, draft_id: str, action: str, text: Optional[str] = None, reason: Optional[str] = None) -> Draft:
        d = self.store.get_draft(draft_id)
        if d is None:
            raise KeyError(draft_id)
        if d.status != Status.pending:
            raise ValueError(f"draft already {d.status.value}")
        trust = self.store.get_trust()
        d.decided_at = now()
        if action == "reject":
            d.status, d.decision, d.reject_reason = Status.rejected, "rejected", reason or "rejected by owner"
            trust.record("rejected")
        elif action in ("approve", "edit"):
            if d.route == Route.blocked and not (action == "edit" and text):
                raise ValueError("this draft failed fact verification; edit it or reject it")
            edited = action == "edit" and text is not None and text.strip() != d.text
            if edited or d.route == Route.blocked:
                new = text.strip()
                # the edited text must itself pass the guardrail (claims that no longer appear are dropped)
                claims = [c for c in d.claims if c.span.lower() in new.lower()]
                v = verify(DraftOut(subject=d.subject, text=new, claims=claims, offer_id=d.offer_id), d.facts,
                           d.channel.value, self.merchant)
                if not v.passed:
                    raise ValueError("edit fails fact verification: " + "; ".join(v.hard_issues))
                d.text, d.claims, d.verification = new, claims, v
                d.rendered = self._re_render(d)
            if d.route == Route.blocked and not edited:
                raise ValueError("blocked drafts cannot be approved unchanged")
            d.decision = "edited" if edited else "approved"
            trust.record("edited" if edited else "approved")
            self.store.set_trust(trust)
            self.store.add_event("decision", customer_id=d.customer_id, draft_id=d.id, detail=d.decision)
            self._send(d, d.decision)
            return self.store.get_draft(d.id)  # type: ignore[return-value]
        else:
            raise ValueError(f"unknown action {action}")
        self.store.set_trust(trust)
        self.store.put_draft(d)
        self.store.add_event("decision", customer_id=d.customer_id, draft_id=d.id, detail=d.decision)
        return d

    def _re_render(self, d: Draft) -> str:
        t = next((x for x in build_targets(self.rows(refresh=False), self.settings.as_of, self.merchant)
                  if x.customer_id == d.customer_id), None)
        if t is None:
            return d.rendered
        return render(d.channel, t, DraftOut(subject=d.subject, text=d.text, claims=d.claims, offer_id=d.offer_id), self.merchant)

    # -- inbound --------------------------------------------------------------------------------
    def find_customer(self, phone: Optional[str] = None, email: Optional[str] = None, customer_id: Optional[str] = None) -> Optional[str]:
        norm = lambda p: "".join(ch for ch in (p or "") if ch.isdigit())[-10:]
        for r in self.rows(refresh=False) or self.rows():
            if customer_id and r["customer_id"] == customer_id:
                return r["customer_id"]
            if phone and norm(r.get("phone")) and norm(r.get("phone")) == norm(phone):
                return r["customer_id"]
            if email and r.get("email") and r["email"].lower() == email.lower():
                return r["customer_id"]
        return None

    def inbound(self, text: str, phone: Optional[str] = None, email: Optional[str] = None, customer_id: Optional[str] = None) -> dict:
        from .consent import is_stop

        cid = self.find_customer(phone, email, customer_id)
        if cid is None:
            return {"matched": False, "intent": "unknown"}
        intent = "stop" if is_stop(text) else self.drafter.classify_reply(text)   # STOP never depends on an LLM
        if intent == "stop":
            self.store.suppress(cid, "opt-out reply")
            cancelled = 0
            for d in self.store.list_drafts():
                if d.customer_id == cid and d.status == Status.pending:
                    d.status, d.reject_reason, d.decision = Status.rejected, "customer opted out", "suppressed"
                    d.decided_at = now()
                    self.store.put_draft(d)
                    cancelled += 1
            self.store.add_event("opt_out", customer_id=cid, detail=f"cancelled {cancelled} queued drafts")
            return {"matched": True, "customer_id": cid, "intent": "stop", "cancelled_drafts": cancelled}
        self.store.add_event("reply", customer_id=cid, detail=intent)
        return {"matched": True, "customer_id": cid, "intent": intent}

    def record_order(self, customer_id: str, amount: float, product: str, on: Optional[date] = None) -> None:
        self.ds.add_order(customer_id, on or self.settings.as_of, amount, product)
        self.store.add_event("order", customer_id=customer_id, amount=amount, detail=product)

    # -- metrics --------------------------------------------------------------------------------
    def kpis(self) -> dict:
        drafts = self.store.list_drafts()
        events = self.store.list_events()
        sent = [d for d in drafts if d.status == Status.sent]
        auto = [d for d in sent if d.decision == "auto"]
        reviewed = [d for d in drafts if d.decision in ("approved", "edited", "rejected") and d.decided_at]
        lat = [(d.decided_at - d.created_at).total_seconds() for d in reviewed]
        sent_at: dict[str, list[datetime]] = {}
        for e in events:
            if e["kind"] == "sent":
                sent_at.setdefault(e["customer_id"], []).append(e["ts"])
        recovered, converted = 0.0, set()
        for e in events:
            if e["kind"] == "order" and e["customer_id"] in sent_at:
                if any(timedelta(0) <= e["ts"] - s <= timedelta(days=ATTRIBUTION_DAYS) for s in sent_at[e["customer_id"]]):
                    recovered += float(e["amount"])
                    converted.add(e["customer_id"])
        repliers = {e["customer_id"] for e in events if e["kind"] == "reply"}
        trust = self.store.get_trust()
        return {
            "drafted": len(drafts), "sent": len(sent), "auto_sent": len(auto),
            "needs_review": sum(1 for d in drafts if d.status == Status.pending and d.route == Route.needs_review),
            "blocked": sum(1 for d in drafts if d.route == Route.blocked),
            "blocked_pending": sum(1 for d in drafts if d.route == Route.blocked and d.status == Status.pending),
            "rejected": sum(1 for d in drafts if d.decision == "rejected"),
            "auto_send_rate": round(len(auto) / len(sent), 3) if sent else 0.0,
            "approval_latency_median_s": round(statistics.median(lat), 1) if lat else None,
            "minutes_saved": len(sent) * ASSUMED_MINUTES_PER_MESSAGE,
            "assumed_minutes_per_message": ASSUMED_MINUTES_PER_MESSAGE,
            "reply_rate": round(len(repliers & {d.customer_id for d in sent}) / len(sent), 3) if sent else 0.0,
            "opt_outs": sum(1 for e in events if e["kind"] == "opt_out"),
            "recovered_revenue": round(recovered, 2), "converted_customers": len(converted),
            "attribution_days": ATTRIBUTION_DAYS,
            "trust": trust.to_dict(),
            "synthetic": not self.settings.is_gcp,
        }
