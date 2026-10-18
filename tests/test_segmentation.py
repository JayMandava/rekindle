from datetime import date

from rekindle.config import Merchant
from rekindle.datasource import LocalDataSource
from rekindle.segmentation import build_targets, next_milestone

AS_OF = date(2026, 10, 18)


def cust(i, **kw):
    base = {"customer_id": i, "merchant_id": "m", "name": f"Cust {i}", "phone": "+919800000001", "email": f"{i}@x.com",
            "language": "en", "consent_whatsapp": 1, "consent_email": 1, "anchor_name": "Kid", "anchor_date": "2025-01-01"}
    base.update(kw)
    return base


def order(n, cid, d, amt=1000, prod="Newborn session"):
    return {"order_id": f"O{n}", "customer_id": cid, "order_date": d, "amount": amt, "product": prod}


def build(customers, orders):
    ds = LocalDataSource(customers, orders)
    rows = ds.segment_rows(AS_OF, Merchant())
    return rows, {t.customer_id: t for t in build_targets(rows, AS_OF, Merchant())}


def test_segments_and_recency():
    customers = [cust("a"), cust("b"), cust("c"), cust("d")]
    orders = [order(1, "a", "2026-10-01"),                                  # active
              order(2, "b", "2026-02-01"),                                  # 259d, single order -> one_time_lapsed
              order(3, "c", "2024-01-01"),                                  # lost
              *[order(10 + i, "d", f"2026-0{i + 1}-01", 20000) for i in range(0, 5)]]  # frequent & big, last 2026-05-01 -> 170d
    rows, _ = build(customers, orders)
    seg = {r["customer_id"]: r["segment"] for r in rows}
    assert seg["a"] == "active" and seg["b"] == "one_time_lapsed" and seg["c"] == "lost"
    assert seg["d"] in ("champion_dormant", "at_risk")
    assert {r["customer_id"]: r["recency_days"] for r in rows}["b"] == 259


def test_no_consent_no_target():
    customers = [cust("a", consent_whatsapp=0, consent_email=0), cust("b", phone="", consent_email=0)]
    orders = [order(1, "a", "2026-02-01"), order(2, "b", "2026-02-01")]
    _, targets = build(customers, orders)
    assert targets == {}


def test_consent_requires_contact_detail():
    customers = [cust("a", consent_whatsapp=1, phone="", consent_email=1, email="a@x.com")]
    _, targets = build(customers, [order(1, "a", "2026-02-01")])
    assert targets["a"].consent_whatsapp is False and targets["a"].consent_email is True


def test_milestone_window():
    m = Merchant()
    assert next_milestone(date(2025, 10, 30), AS_OF, m) == (12, date(2026, 10, 30))
    assert next_milestone(date(2025, 12, 30), AS_OF, m) is None


def test_milestone_overrides_dormancy_segment_but_not_recent_customers():
    customers = [cust("a", anchor_date="2025-10-30"), cust("b", anchor_date="2025-10-30")]
    orders = [order(1, "a", "2026-02-01"), order(2, "b", "2026-10-10")]
    _, targets = build(customers, orders)
    assert targets["a"].segment == "milestone_due"
    assert "b" not in targets  # ordered 8 days ago, don't nudge
    assert any(f.id == "F5" and "1 year" in f.value for f in targets["a"].facts)
