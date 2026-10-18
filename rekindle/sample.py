"""Synthetic Baby Trails-shaped dataset (NOT real customers). Seeded, so runs are reproducible.

Generates rows in the shape of Baby Trails' Airtable `Bookings` table and passes them through the same
adapter real data will use (rekindle.babytrails), so the demo exercises the production ingestion path.
Package names and prices follow Baby Trails' config/catalog.json, whose prices are still placeholders there.
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

from .babytrails import OPT_IN_FIELD, bookings_to_rows

FIRST = ["Priya", "Ananya", "Kavya", "Neha", "Sneha", "Divya", "Pooja", "Ritu", "Meera", "Aditi", "Shruti", "Swati",
         "Isha", "Tanvi", "Nisha", "Rhea", "Anjali", "Lakshmi", "Sana", "Mitali", "Karthik", "Arjun", "Vikram", "Karan",
         "Amit", "Sanjay", "Rahul", "Nikhil", "Deepa", "Revathi", "Janani", "Harini", "Sowmya", "Gayathri"]
LAST = ["Sharma", "Iyer", "Reddy", "Gupta", "Nair", "Menon", "Verma", "Singh", "Pillai", "Rao", "Kulkarni", "Joshi",
        "Kapoor", "Desai", "Patel", "Malhotra", "Bose", "Narayan", "Khan", "Das", "Subramanian", "Krishnan", "Raman"]
# (shoot type, package full name, placeholder price) from Baby Trails' catalog
PACKS = {"newborn": [("NB Classic", 10000), ("NB Elite", 15000), ("NB Grandeur", 22000)],
         "baby": [("Baby Classic", 12000), ("Baby Elite", 18000), ("Baby Grandeur", 25000), ("Baby Legacy", 35000)],
         "maternity": [("Maternity Classic", 9000), ("Maternity Elite", 14000), ("Maternity Grandeur", 20000)]}
OPT_IN_RATE = 0.55   # illustrative: the real rate is 0 until the opt-in question exists


def _age_text(days: int) -> str:
    return f"{days} days" if days < 45 else f"{round(days / 30.4375)} months"


def generate_bookings(as_of: date, n: int = 320, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    seq = 0
    for i in range(n):
        phone = f"9198{rng.randint(10000000, 99999999)}"
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        dob = as_of - timedelta(days=rng.randint(20, 900))
        opt_in = rng.random() < OPT_IN_RATE
        lang = "ta" if rng.random() < 0.3 else "en"
        # journey: optional maternity (before birth) -> newborn -> baby milestone -> repeat visits
        plan = []
        if rng.random() < 0.25:
            plan.append(("maternity", dob - timedelta(days=rng.randint(30, 120))))
        plan.append(("newborn", dob + timedelta(days=rng.randint(6, 28))))
        if rng.random() < 0.55:
            plan.append(("baby", dob + timedelta(days=rng.randint(95, 330))))
        if rng.random() < 0.2:
            plan.append(("baby", dob + timedelta(days=rng.randint(330, 700))))
        for stype, when in plan:
            if when > as_of or when < as_of - timedelta(days=1100):
                continue
            pkg, price = rng.choice(PACKS[stype])
            seq += 1
            age_days = (when - dob).days
            age = "5 months pregnant" if stype == "maternity" else _age_text(max(age_days, 1))
            total = round(price * rng.choice([1, 1, 0.85]) / 100) * 100          # 15% photo-use discount sometimes
            rows.append({
                "Ref": f"BT-{when.strftime('%y%m')}-{seq:03d}", "Client Name": name, "Phone": phone, "Channel": "whatsapp",
                "Shoot Type": stype, "Baby Age": age, "Package": pkg, "Marketing": rng.choice(["Yes", "No"]),
                "Requested Date": when.isoformat(), "Shoot Slot": f"{when.isoformat()}T10:30",
                "Total": total, "Advance": 3000, "Add-ons": rng.choice([0, 0, 0, 1000, 3000]),
                "Stage": "closed", "Studio Stage": "Final", "Advance Paid": True, "Balance Paid": True,
                OPT_IN_FIELD: opt_in, "Language": lang,
            })
        if rng.random() < 0.12:     # a lead that never paid: must not become a customer
            seq += 1
            rows.append({"Ref": f"BT-LEAD-{seq:03d}", "Client Name": name + " (lead)", "Phone": f"9199{rng.randint(10000000, 99999999)}",
                         "Shoot Type": "baby", "Baby Age": "5 months", "Requested Date": (as_of - timedelta(days=40)).isoformat(),
                         "Stage": "lost", "Studio Stage": "Closed - Denied", "Advance Paid": False, "Balance Paid": False})
    return rows


def generate(as_of: date, n: int = 320, seed: int = 7):
    return bookings_to_rows(generate_bookings(as_of, n, seed))


CUSTOMER_COLS = ["customer_id", "merchant_id", "name", "phone", "email", "language", "consent_whatsapp", "consent_email",
                 "anchor_name", "anchor_date"]
ORDER_COLS = ["order_id", "customer_id", "order_date", "amount", "product", "shoot_type"]


def write_csv(out: Path, customers: list[dict], orders: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, cols, rows in (("customers", CUSTOMER_COLS, customers), ("orders", ORDER_COLS, orders)):
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write the synthetic dataset as CSV (e.g. for `bq load`).")
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--as-of", default=date.today().isoformat())
    a = ap.parse_args()
    c, o = generate(date.fromisoformat(a.as_of))
    write_csv(Path(a.out), c, o)
    print(f"wrote {a.out}/customers.csv ({len(c)}) and orders.csv ({len(o)})")
