"""Adapter from the Baby Trails booking system (github.com/JayMandava/baby-trails) to ReKindle's tables.

Baby Trails mirrors every booking to an Airtable `Bookings` table (see its src/adapters/airtable.js).
This module turns those rows into ReKindle `customers` and `orders`. Things worth knowing about that source:

* It stores the baby's AGE at booking ("4 months"), not a birth date, and never the child's name.
  We estimate a birth date as shoot date minus age, so every derived milestone is approximate.
* Its `Marketing` field is consent to use photos on social media (for a discount). It is NOT consent to be
  messaged. Re-engagement needs its own opt-in: the `Re-engagement Opt-in` checkbox (proposed, see
  docs/BABYTRAILS_INTEGRATION.md). Until that exists no customer is eligible, by design.
* It has no email, no language preference, and one WhatsApp number per customer (`Phone`, digits only).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Iterable, Optional

OPT_IN_FIELD = "Re-engagement Opt-in"
CHILD_NAME_FIELD = "Child Name"      # optional, not collected today
LANGUAGE_FIELD = "Language"          # optional, not collected today

SHOOT_LABEL = {"newborn": "Newborn", "baby": "Baby milestone", "maternity": "Maternity",
               "mini": "Mini", "hospital": "Hospital", "events": "Event", "others": "Family"}

_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_UNITS = [(re.compile(r"^(d|day|days)$"), 1.0), (re.compile(r"^(w|wk|wks|week|weeks)$"), 7.0),
          (re.compile(r"^(m|mo|mos|month|months)$"), 30.4375), (re.compile(r"^(y|yr|yrs|year|years)$"), 365.25)]


def parse_age_days(text: str) -> Optional[int]:
    """'4 months', '12 days', '1.5 years', '1 year 3 months' -> days. None for maternity or unparseable text.

    Baby Trails normalises ages to forms like '4 months' / '12 days' / '2 years' (src/validate.js parseAge).
    Maternity values ('5 months pregnant', 'due 2026-12-01') deliberately return None: see build note below.
    """
    t = (text or "").lower().strip()
    if not t or "pregnan" in t or t.startswith("due"):
        return None
    t = re.sub(r"\b(" + "|".join(_WORDS) + r")\b(?=\s*(?:-|\s)\s*[a-z])", lambda m: str(_WORDS[m.group(1)]), t)
    days, n = 0.0, 0
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", t):
        for pat, mult in _UNITS:
            if pat.match(unit):
                days += float(num) * mult
                n += 1
                break
    return round(days) if n and days > 0 else None


def _digits(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _shoot_date(row: dict) -> Optional[date]:
    for key in ("Shoot Slot", "Requested Date"):
        v = str(row.get(key) or "")
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", v)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _truthy(v) -> bool:
    return v is True or str(v).strip().lower() in ("1", "true", "yes", "y", "checked")


def bookings_to_rows(bookings: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """Airtable Bookings rows (field names as in Baby Trails' SCHEMA) -> (customers, orders)."""
    customers: dict[str, dict] = {}
    orders: list[dict] = []
    for r in sorted(bookings, key=lambda x: str(x.get("Shoot Slot") or x.get("Requested Date") or "")):
        phone = _digits(r.get("Phone"))
        shot = _shoot_date(r)
        if not phone or not shot:
            continue
        # A customer is someone who paid. Unpaid leads and cancelled/lost bookings are not customers.
        paid = _truthy(r.get("Advance Paid")) or _truthy(r.get("Balance Paid"))
        if not paid or str(r.get("Stage") or "").lower() == "lost" or str(r.get("Studio Stage") or "") == "Cancelled":
            continue
        stype = str(r.get("Shoot Type") or "").lower()
        total = float(r.get("Total") or 0) + float(r.get("Add-ons") or 0)
        amount = total if _truthy(r.get("Balance Paid")) else float(r.get("Advance") or 0)
        orders.append({"order_id": str(r.get("Ref") or f"{phone}-{shot}"), "customer_id": phone,
                       "order_date": shot.isoformat(), "amount": round(amount, 2),
                       "product": str(r.get("Package") or SHOOT_LABEL.get(stype, "Session")), "shoot_type": stype})
        c = customers.setdefault(phone, {
            "customer_id": phone, "merchant_id": "babytrail", "name": "", "phone": f"+{phone}", "email": "",
            "language": "en", "consent_whatsapp": 0, "consent_email": 0, "anchor_name": "", "anchor_date": ""})
        c["name"] = str(r.get("Client Name") or c["name"]).strip()
        if r.get(LANGUAGE_FIELD):
            c["language"] = str(r[LANGUAGE_FIELD]).strip().lower()[:5]
        if r.get(CHILD_NAME_FIELD):
            c["anchor_name"] = str(r[CHILD_NAME_FIELD]).strip()
        # Consent is the latest answer. Withdrawing (unchecked on a later booking) wins over an earlier yes.
        c["consent_whatsapp"] = int(_truthy(r.get(OPT_IN_FIELD)))
        # Estimated birth date = shoot date - age at shoot. Maternity bookings give no usable age on purpose:
        # we never infer or mention a baby from a pregnancy booking.
        days = parse_age_days(str(r.get("Baby Age") or ""))
        if days is not None and stype != "maternity":
            c["anchor_date"] = (shot - timedelta(days=days)).isoformat()
    return list(customers.values()), orders
