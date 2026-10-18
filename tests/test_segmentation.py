from datetime import date

from rekindle.config import Merchant
from rekindle.datasource import LocalDataSource
from rekindle.segmentation import build_targets, consent_summary, journey_trigger

AS_OF = date(2026, 10, 18)


def cust(i, **kw):
    base = {"customer_id": i, "merchant_id": "m", "name": f"Cust {i}", "phone": "+919800000001", "email": f"{i}@x.com",
            "language": "en", "consent_whatsapp": 1, "consent_email": 1, "anchor_name": "", "anchor_date": ""}
    base.update(kw)
    return base


def order(n, cid, d, amt=1000, prod="NB Classic", st="newborn"):
    return {"order_id": f"O{n}", "customer_id": cid, "order_date": d, "amount": amt, "product": prod, "shoot_type": st}


def build(customers, orders):
    ds = LocalDataSource(customers, orders)
    rows = ds.segment_rows(AS_OF, Merchant())
    return rows, {t.customer_id: t for t in build_targets(rows, AS_OF, Merchant())}


def test_segments_and_recency():
    customers = [cust("a"), cust("b"), cust("c"), cust("d")]
    orders = [order(1, "a", "2026-10-01"),                                           # active
              order(2, "b", "2026-02-01"),                                           # 259d, one order -> one_time_lapsed
              order(3, "c", "2024-01-01"),                                           # lost
              *[order(10 + i, "d", f"2026-0{i + 1}-01", 20000) for i in range(0, 3)]]  # repeat + big spend, last 2026-03-01
    rows, _ = build(customers, orders)
    seg = {r["customer_id"]: r["segment"] for r in rows}
    assert seg["a"] == "active" and seg["b"] == "one_time_lapsed" and seg["c"] == "lost"
    assert seg["d"] in ("champion_dormant", "at_risk")
    assert {r["customer_id"]: r["recency_days"] for r in rows}["b"] == 259


def test_no_consent_no_target():
    customers = [cust("a", consent_whatsapp=0, consent_email=0), cust("b", phone="", consent_email=0)]
    _, targets = build(customers, [order(1, "a", "2026-02-01"), order(2, "b", "2026-02-01")])
    assert targets == {}


def test_consent_requires_contact_detail():
    _, targets = build([cust("a", consent_whatsapp=1, phone="", consent_email=1, email="a@x.com")], [order(1, "a", "2026-02-01")])
    assert targets["a"].consent_whatsapp is False and targets["a"].consent_email is True


def test_newborn_customer_is_offered_the_baby_session_at_about_four_months():
    # born ~125 days before AS_OF, last shoot was a newborn session -> 'about 4 months old'
    c = [cust("a", anchor_date="2026-06-15")]
    o = [order(1, "a", "2026-07-10", st="newborn")]
    rows, targets = build(c, o)
    assert journey_trigger(rows[0], AS_OF, Merchant())[1] == "Your baby is about 4 months old"
    t = targets["a"]
    assert t.segment == "milestone_due"
    ids = {f.id: f.value for f in t.facts}
    assert ids["F5"] == "Your baby is about 4 months old" and "3 to 12 months" in ids["F6"]
    assert "F4" not in ids          # Baby Trails does not collect the child's name


def test_baby_session_customers_are_not_pitched_the_baby_session_again():
    rows, _ = build([cust("a", anchor_date="2026-06-15")], [order(1, "a", "2026-07-10", st="baby")])
    assert journey_trigger(rows[0], AS_OF, Merchant()) is None


def test_first_birthday_window():
    rows, targets = build([cust("a", anchor_date="2025-11-20")], [order(1, "a", "2026-02-01", st="baby")])
    assert journey_trigger(rows[0], AS_OF, Merchant())[1] == "Your baby turns 1 in November 2026"
    assert targets["a"].segment == "milestone_due"


def test_child_name_used_when_known():
    rows, _ = build([cust("a", anchor_name="Aarav", anchor_date="2025-11-20")], [order(1, "a", "2026-02-01", st="baby")])
    assert journey_trigger(rows[0], AS_OF, Merchant())[1] == "Aarav turns 1 in November 2026"


def test_no_age_no_journey_trigger():
    rows, targets = build([cust("a", anchor_date="")], [order(1, "a", "2026-02-01", st="maternity")])
    assert journey_trigger(rows[0], AS_OF, Merchant()) is None and targets["a"].segment != "milestone_due"


def test_recent_customer_is_not_nudged_even_at_a_milestone():
    _, targets = build([cust("a", anchor_date="2025-11-20")], [order(1, "a", "2026-10-10", st="baby")])
    assert "a" not in targets


def test_consent_summary():
    rows, _ = build([cust("a"), cust("b", consent_whatsapp=0)], [order(1, "a", "2026-02-01"), order(2, "b", "2026-02-01")])
    assert consent_summary(rows) == {"opted_in": 1, "total": 2}
