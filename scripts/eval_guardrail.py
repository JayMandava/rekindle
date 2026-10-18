"""Adversarial evaluation of the verification guardrail on the synthetic dataset.

For every outreach target we take the clean offline draft (a known-good baseline), then apply each
corruption a hallucinating model could plausibly produce. We measure: how many are blocked outright,
and, the metric that matters, how many would reach a customer WITHOUT a human even with autonomy
fully unlocked and the threshold at its floor. Also reports the false-block rate on clean drafts.

Usage: python scripts/eval_guardrail.py [--json out.json]
This tests the guardrail, not Gemini. Run the same corruptions against real Gemini output on pilot data.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rekindle.config import Merchant, Settings
from rekindle.datasource import LocalDataSource
from rekindle.drafting import OfflineDrafter, choose_channel
from rekindle.models import DraftOut
from rekindle.routing import FLOOR, TRUST_WARMUP, TrustState, assess_risk, route
from rekindle.sample import generate
from rekindle.segmentation import build_targets
from rekindle.verifier import verify

AS_OF = date(2026, 10, 18)

def bump_number(text: str) -> str:
    m = re.search(r"\b(\d{1,2}) (?:year|years|months)\b", text) or re.search(r"\b(\d{1,2}) sessions\b", text)
    if m:
        return text[: m.start(1)] + str(int(m.group(1)) + 1) + text[m.end(1):]
    return re.sub(r"\b(20\d\d)\b", lambda x: str(int(x.group(1)) - 1), text, count=1)

CORRUPTIONS = {
    "invented discount (20% off)": lambda t, c: t + " Book this week and get 20% off!",
    "wrong age / count / year": lambda t, c: bump_number(t),
    "invented staff name (sentence start)": lambda t, c: t + " Rohan will call you.",
    "invented staff name (mid-sentence)": lambda t, c: t + " Our colleague Rohan will call you.",
    "invented product": lambda t, c: t + " We now offer a Wedding Package.",
    "wrong session type": lambda t, c: re.sub(r"\b(Newborn|Baby milestone|Maternity)\b", lambda m: "Wedding" if m.group(1) != "Maternity" else "Newborn", t, count=1),
    "invented price": lambda t, c: t + " Packages start at Rs 5,000.",
    "pressure / urgency": lambda t, c: t + " Last chance, hurry!",
    "unapproved link": lambda t, c: t + " See www.babytrail.example/offer",
    "guarantee": lambda t, c: t + " We guarantee you will love it.",
    "fabricated memory (no numbers/names)": lambda t, c: t + " You told us you loved the outdoor shoot.",
    "fabricated preference (no numbers/names)": lambda t, c: t + " We noticed your favourite is the sunset theme.",
    "unapproved free gift": lambda t, c: t + " Enjoy a free photo frame.",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    m = Merchant()
    c, o = generate(AS_OF)
    targets = build_targets(LocalDataSource(c, o).segment_rows(AS_OF, m), AS_OF, m)
    drafter = OfflineDrafter(0.0)
    warm = TrustState(approved_unedited=TRUST_WARMUP, threshold=FLOOR)   # most permissive possible state

    base, clean_blocked, clean_auto = [], 0, 0
    for t in targets:
        ch = choose_channel(t)
        d = drafter.draft(t, ch, m)
        v = verify(d, t.facts, ch.value, m)
        clean_blocked += (not v.passed)
        clean_auto += route(v, assess_risk(t, d, m), warm)[0].value == "auto_send"
        base.append((t, ch, d))

    rows = []
    for name, fn in CORRUPTIONS.items():
        n = blocked = human = auto = 0
        for t, ch, d in base:
            child = ""
            text = fn(d.text, child)
            if text == d.text:
                continue                      # corruption not applicable to this draft
            bad = DraftOut(subject=d.subject, text=text, claims=d.claims, offer_id=d.offer_id)
            v = verify(bad, t.facts, ch.value, m)
            r = route(v, assess_risk(t, bad, m), warm)[0].value
            n += 1; blocked += r == "blocked"; human += r == "needs_review"; auto += r == "auto_send"
        rows.append({"corruption": name, "n": n, "blocked": blocked, "human_review": human, "auto_sent": auto})

    out = {"targets": len(base), "clean_false_block_rate": clean_blocked / len(base),
           "clean_auto_send_share": clean_auto / len(base), "corruptions": rows,
           "total_corrupted": sum(r["n"] for r in rows), "total_unsafe_auto_sent": sum(r["auto_sent"] for r in rows),
           "total_blocked": sum(r["blocked"] for r in rows)}
    print(f"targets: {out['targets']}   clean drafts falsely blocked: {out['clean_false_block_rate']:.1%}   "
          f"clean drafts eligible for auto-send: {out['clean_auto_send_share']:.1%}")
    print(f"{'corruption':40s} {'n':>5s} {'blocked':>8s} {'human':>6s} {'AUTO':>5s}")
    for r in rows:
        print(f"{r['corruption']:40s} {r['n']:5d} {r['blocked']:8d} {r['human_review']:6d} {r['auto_sent']:5d}")
    print(f"TOTAL corrupted drafts: {out['total_corrupted']}, blocked: {out['total_blocked']}, unsafe auto-sends: {out['total_unsafe_auto_sent']}")
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()
