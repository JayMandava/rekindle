"""State: drafts, suppressions, trust state, audit events. In-memory locally, Firestore (+ BigQuery events) in gcp."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Protocol

from .models import Draft
from .routing import TrustState


def now() -> datetime:
    return datetime.now(timezone.utc)


class Store(Protocol):
    def put_draft(self, d: Draft) -> None: ...
    def get_draft(self, draft_id: str) -> Optional[Draft]: ...
    def list_drafts(self) -> list[Draft]: ...
    def suppress(self, customer_id: str, reason: str) -> None: ...
    def suppressed(self) -> set[str]: ...
    def get_trust(self) -> TrustState: ...
    def set_trust(self, t: TrustState) -> None: ...
    def add_event(self, kind: str, **fields) -> None: ...
    def list_events(self) -> list[dict]: ...
    def reset(self) -> None: ...


class MemoryStore:
    def __init__(self):
        self.reset()

    def reset(self):
        self._drafts: dict[str, Draft] = {}
        self._suppressed: dict[str, str] = {}
        self._trust = TrustState()
        self._events: list[dict] = []

    def put_draft(self, d): self._drafts[d.id] = d
    def get_draft(self, draft_id): return self._drafts.get(draft_id)
    def list_drafts(self): return sorted(self._drafts.values(), key=lambda d: d.created_at)
    def suppress(self, customer_id, reason): self._suppressed[customer_id] = reason
    def suppressed(self): return set(self._suppressed)
    def get_trust(self): return self._trust
    def set_trust(self, t): self._trust = t
    def list_events(self): return list(self._events)

    def add_event(self, kind, **fields):
        self._events.append({"ts": now(), "kind": kind, **fields})


class FirestoreStore:
    """Firestore is the real-time source for the cockpit; events are also appended to BigQuery for Looker Studio."""

    def __init__(self, project: str, bq_dataset: Optional[str] = None):
        from google.cloud import firestore

        self.db = firestore.Client(project=project or None)
        self.bq = None   # BigQuery is optional: without it (Spark plan) events live only in Firestore
        if bq_dataset:
            from google.cloud import bigquery

            self.bq = bigquery.Client(project=project or None)
            self.events_table = f"{project}.{bq_dataset}.events" if project else f"{bq_dataset}.events"

    def put_draft(self, d): self.db.collection("drafts").document(d.id).set(d.model_dump(mode="json"))

    def get_draft(self, draft_id):
        s = self.db.collection("drafts").document(draft_id).get()
        return Draft.model_validate(s.to_dict()) if s.exists else None

    def list_drafts(self):
        return sorted((Draft.model_validate(s.to_dict()) for s in self.db.collection("drafts").stream()),
                      key=lambda d: d.created_at)

    def suppress(self, customer_id, reason):
        self.db.collection("suppressions").document(customer_id).set({"reason": reason, "ts": now()})

    def suppressed(self): return {s.id for s in self.db.collection("suppressions").stream()}

    def get_trust(self):
        s = self.db.collection("meta").document("trust").get()
        d = s.to_dict() if s.exists else {}
        return TrustState(**{k: d[k] for k in ("threshold", "approved_unedited", "edited", "rejected") if k in d})

    def set_trust(self, t): self.db.collection("meta").document("trust").set(t.to_dict())

    def add_event(self, kind, **fields):
        ev = {"ts": now(), "kind": kind, **fields}
        self.db.collection("events").add(ev)
        if self.bq is None:
            return
        row = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in ev.items()
               if k in ("ts", "kind", "customer_id", "draft_id", "segment", "channel", "route",
                        "risk_tier", "confidence", "amount", "detail")}
        self.bq.insert_rows_json(self.events_table, [row])

    def list_events(self):
        return [s.to_dict() for s in self.db.collection("events").order_by("ts").stream()]

    def reset(self):
        raise RuntimeError("reset is disabled outside local mode")
