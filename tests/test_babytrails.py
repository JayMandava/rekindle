from datetime import date

from rekindle.babytrails import OPT_IN_FIELD, bookings_to_rows, parse_age_days
from rekindle.sample import generate, generate_bookings


def row(**kw):
    base = {"Ref": "BT-2605-001", "Client Name": "Priya Sharma", "Phone": "919845012345", "Shoot Type": "newborn",
            "Baby Age": "12 days", "Package": "NB Classic", "Requested Date": "2026-05-10", "Shoot Slot": "2026-05-10T10:30",
            "Total": 10000, "Advance": 3000, "Add-ons": 1000, "Stage": "closed", "Studio Stage": "Final",
            "Advance Paid": True, "Balance Paid": True}
    base.update(kw)
    return base


def test_age_parsing_matches_baby_trails_formats():
    assert parse_age_days("12 days") == 12 and parse_age_days("2 weeks") == 14
    assert parse_age_days("4 months") == 122 and parse_age_days("2 years") == 730
    assert parse_age_days("1 year 3 months") == 457 and parse_age_days("three months") == 91


def test_maternity_ages_never_produce_a_baby():
    for t in ("5 months pregnant", "20 weeks pregnant", "due 2026-12-01", "", "soon"):
        assert parse_age_days(t) is None
    c, _ = bookings_to_rows([row(**{"Shoot Type": "maternity", "Baby Age": "5 months pregnant"})])
    assert c[0]["anchor_date"] == ""


def test_basic_mapping_and_estimated_birth_date():
    c, o = bookings_to_rows([row()])
    assert c[0]["customer_id"] == "919845012345" and c[0]["phone"] == "+919845012345" and c[0]["email"] == ""
    assert c[0]["anchor_date"] == "2026-04-28"                       # 10 May minus 12 days
    assert o[0]["amount"] == 11000.0 and o[0]["shoot_type"] == "newborn" and o[0]["order_date"] == "2026-05-10"


def test_marketing_field_is_not_messaging_consent():
    c, _ = bookings_to_rows([row(Marketing="Yes")])          # photo-use consent only
    assert c[0]["consent_whatsapp"] == 0


def test_opt_in_and_withdrawal():
    c, _ = bookings_to_rows([row(**{OPT_IN_FIELD: True})])
    assert c[0]["consent_whatsapp"] == 1
    later = row(Ref="BT-2609-004", **{"Shoot Slot": "2026-09-01T10:30", "Requested Date": "2026-09-01", OPT_IN_FIELD: False})
    c, _ = bookings_to_rows([row(**{OPT_IN_FIELD: True}), later])
    assert c[0]["consent_whatsapp"] == 0                       # latest answer wins


def test_unpaid_and_lost_bookings_are_not_customers():
    rows = [row(**{"Advance Paid": False, "Balance Paid": False}), row(Phone="919800000002", Stage="lost"),
            row(Phone="919800000003", **{"Studio Stage": "Cancelled"}), row(Phone="")]
    c, o = bookings_to_rows(rows)
    assert c == [] and o == []


def test_repeat_customer_is_one_customer_with_many_orders():
    a = row()
    b = row(Ref="BT-2609-009", **{"Shoot Type": "baby", "Baby Age": "4 months", "Package": "Baby Elite", "Shoot Slot": "2026-09-01T10:30"})
    c, o = bookings_to_rows([b, a])
    assert len(c) == 1 and len(o) == 2
    assert c[0]["anchor_date"] == "2026-05-02"                 # latest booking's age wins: 1 Sep minus 122 days


def test_advance_only_booking_counts_advance_as_revenue():
    _, o = bookings_to_rows([row(**{"Balance Paid": False})])
    assert o[0]["amount"] == 3000.0


def test_synthetic_data_goes_through_the_same_adapter():
    as_of = date(2026, 10, 18)
    rows = generate_bookings(as_of)
    c, o = generate(as_of)
    assert any(str(r["Ref"]).startswith("BT-LEAD") for r in rows)                        # unpaid leads exist in the raw data
    assert not any(x["name"].endswith("(lead)") for x in c)                              # and never become customers
    assert 0 < sum(x["consent_whatsapp"] for x in c) < len(c)
    assert all(x["email"] == "" for x in c) and all(x["anchor_name"] == "" for x in c)   # mirrors what Baby Trails collects
