"""Risk tiering and the trust-earning router.

Policy: human-supervised first, autonomy earned. Auto-send stays OFF until the merchant has made
TRUST_WARMUP decisions. After that only LOW-risk drafts above the (learning) confidence threshold
auto-send; everything else goes to the owner's cockpit. Unedited approvals lower the threshold
(never below FLOOR); edits and rejections raise it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import Merchant
from .models import DraftOut, Risk, Route, Target, Verification

TRUST_WARMUP = 20
FLOOR, CEIL, START = 0.70, 0.95, 0.85


@dataclass
class TrustState:
    threshold: float = START
    approved_unedited: int = 0
    edited: int = 0
    rejected: int = 0

    @property
    def decisions(self) -> int:
        return self.approved_unedited + self.edited + self.rejected

    @property
    def auto_enabled(self) -> bool:
        return self.decisions >= TRUST_WARMUP

    def record(self, outcome: str) -> None:
        if outcome == "approved":
            self.approved_unedited += 1
            self.threshold = max(FLOOR, self.threshold - 0.005)
        elif outcome == "edited":
            self.edited += 1
            self.threshold = min(CEIL, self.threshold + 0.02)
        elif outcome == "rejected":
            self.rejected += 1
            self.threshold = min(CEIL, self.threshold + 0.04)
        self.threshold = round(self.threshold, 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(decisions=self.decisions, auto_enabled=self.auto_enabled, warmup=TRUST_WARMUP)
        return d


def assess_risk(t: Target, d: DraftOut, merchant: Merchant) -> Risk:
    reasons: list[str] = []
    high = False
    offer = next((o for o in merchant.offers if o["id"] == d.offer_id), None)
    if offer and offer["discount"]:
        high = True
        reasons.append("contains a discount")
    if t.segment == "milestone_due":
        high = True
        reasons.append("references a child's milestone")
    if high:
        return Risk(tier="high", reasons=reasons)
    if t.vip:
        reasons.append("top-decile customer")
    if t.recency_days > 365:
        reasons.append("dormant over a year")
    return Risk(tier="medium" if reasons else "low", reasons=reasons or ["routine win-back, no sensitive content"])


def route(v: Verification, risk: Risk, trust: TrustState) -> tuple[Route, str]:
    if not v.passed:
        return Route.blocked, "failed fact verification"
    if not trust.auto_enabled:
        return Route.needs_review, f"trust-building phase ({trust.decisions}/{TRUST_WARMUP} decisions)"
    if risk.tier != "low":
        return Route.needs_review, f"{risk.tier} risk: {', '.join(risk.reasons)}"
    if v.confidence < trust.threshold:
        return Route.needs_review, f"confidence {v.confidence:.2f} below threshold {trust.threshold:.2f}"
    return Route.auto_send, f"low risk, confidence {v.confidence:.2f} >= {trust.threshold:.2f}"
