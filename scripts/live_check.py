"""Preflight for the live Google services. Run this first once credentials exist.

    REKINDLE_MODE=spark GEMINI_API_KEY=... GOOGLE_CLOUD_PROJECT=... python scripts/live_check.py
    REKINDLE_MODE=gcp   GOOGLE_CLOUD_PROJECT=...                    python scripts/live_check.py

Checks only what the chosen mode uses: Gemini (real drafts through the real guardrail), Firestore
(write/read/delete one scratch document), BigQuery (the segmentation query). Prints PASS/FAIL per check
and never prints credentials. Exit code 1 if anything failed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rekindle.config import Merchant, Settings, ensure_credentials
from rekindle.drafting import GeminiDrafter, choose_channel
from rekindle.sample import generate
from rekindle.segmentation import build_targets
from rekindle.datasource import BigQueryDataSource, LocalDataSource
from rekindle.verifier import verify

results: list[tuple[str, bool, str]] = []


def check(name):
    def deco(fn):
        t = time.time()
        try:
            detail = fn() or ""
            results.append((name, True, f"{detail} ({time.time() - t:.1f}s)".strip()))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {str(e)[:300]}"))
        return fn
    return deco


def main() -> int:
    s = Settings()
    ensure_credentials()
    m = Merchant()
    print(f"mode={s.mode} data={s.data} store={s.store} llm={s.llm} model={s.gemini_model} location={s.gemini_location}\n")

    if s.data == "bigquery":
        @check("BigQuery: segmentation query")
        def _bq():
            rows = BigQueryDataSource(s).segment_rows(s.as_of, m)
            return f"{len(rows)} customers segmented"

    if s.store == "firestore":
        @check("Firestore: write/read/delete")
        def _fs():
            from google.cloud import firestore

            ref = firestore.Client(project=s.project or None).collection("_rekindle_check").document("probe")
            ref.set({"ok": True})
            assert ref.get().to_dict() == {"ok": True}
            ref.delete()
            return "round trip ok"

    if s.llm != "offline":
        @check(f"Gemini ({s.llm}): real drafts through the guardrail")
        def _gem():
            c, o = generate(s.as_of)
            rows = LocalDataSource(c, o).segment_rows(s.as_of, m)
            targets = build_targets(rows, s.as_of, m)[:5]
            g = GeminiDrafter(s)
            ok, lines = 0, []
            for t in targets:
                ch = choose_channel(t)
                d = g.draft(t, ch, m)
                v = verify(d, t.facts, ch.value, m)
                ok += v.passed
                lines.append(f"  [{t.segment}] {'PASS' if v.passed else 'BLOCK'} conf={v.confidence:.2f} | {d.text[:110]!r}"
                             + ("" if v.passed else f"\n      why: {v.hard_issues}"))
            print("\n".join(lines))
            if not targets:
                raise RuntimeError("no targets to draft for")
            return f"{ok}/{len(targets)} drafts passed the guardrail (blocked ones are the guardrail working: read the reasons)"

        @check(f"Gemini ({s.llm}): reply-intent classification")
        def _cls():
            got = GeminiDrafter(s).classify_reply("Yes please, do you have a slot this weekend?")
            assert got in {"interested", "question", "not_interested", "stop", "other"}, got
            return f"-> {got}"

    if not results:
        print("local mode: nothing live to check. Set REKINDLE_MODE=spark or gcp.")
        return 0
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
