"""Synthetic studio dataset (NOT real Babytrail data). Seeded, so runs are reproducible."""
from __future__ import annotations

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

NAMES = [
    ("Priya Sharma", "hi"), ("Ananya Iyer", "en"), ("Kavya Reddy", "en"), ("Neha Gupta", "hi"),
    ("Sneha Nair", "en"), ("Divya Menon", "en"), ("Pooja Verma", "hi"), ("Ritu Singh", "hi"),
    ("Meera Pillai", "en"), ("Aditi Rao", "en"), ("Shruti Kulkarni", "en"), ("Swati Joshi", "hi"),
    ("Isha Kapoor", "en"), ("Tanvi Desai", "en"), ("Nisha Patel", "en"), ("Rhea Malhotra", "en"),
    ("Anjali Bose", "en"), ("Lakshmi Narayan", "en"), ("Sana Khan", "hi"), ("Mitali Das", "en"),
]
SURNAMES = ["Sharma", "Iyer", "Reddy", "Gupta", "Nair", "Menon", "Verma", "Singh", "Pillai", "Rao",
            "Kulkarni", "Joshi", "Kapoor", "Desai", "Patel", "Malhotra", "Bose", "Narayan", "Khan", "Das"]
FIRST = ["Priya", "Ananya", "Kavya", "Neha", "Sneha", "Divya", "Pooja", "Ritu", "Meera", "Aditi",
         "Shruti", "Swati", "Isha", "Tanvi", "Nisha", "Rhea", "Anjali", "Lakshmi", "Sana", "Mitali",
         "Rohit", "Arjun", "Vikram", "Karan", "Amit", "Sanjay", "Rahul", "Nikhil"]
CHILDREN = ["Aarav", "Vihaan", "Anaya", "Kiara", "Reyansh", "Myra", "Ishaan", "Saanvi", "Advik", "Diya",
            "Kabir", "Aadhya", "Arnav", "Navya", "Veer", "Prisha"]
PRODUCTS = [
    ("Newborn session", 9500), ("Sitter session", 7500), ("Cake smash session", 11000),
    ("Family portrait session", 8500), ("Maternity session", 9000), ("Annual album", 4500),
]


def generate(as_of: date, n: int = 320, seed: int = 7):
    rng = random.Random(seed)
    customers, orders = [], []
    oid = 0
    for i in range(1, n + 1):
        cid = f"C{i:04d}"
        first = rng.choice(FIRST)
        last = rng.choice(SURNAMES)
        lang = "hi" if rng.random() < 0.25 else "en"
        child = rng.choice(CHILDREN)
        # child age 2 months .. 30 months; makes milestone windows non-empty
        dob = as_of - timedelta(days=rng.randint(60, 900))
        wa = rng.random() > 0.12
        em = rng.random() > 0.15
        customers.append({
            "customer_id": cid, "merchant_id": "babytrail", "name": f"{first} {last}",
            "phone": f"+9198{rng.randint(10000000, 99999999)}" if wa or rng.random() > 0.3 else "",
            "email": f"{first.lower()}.{last.lower()}{i}@example.com" if em or rng.random() > 0.5 else "",
            "language": lang, "consent_whatsapp": int(wa), "consent_email": int(em),
            "anchor_name": child, "anchor_date": dob.isoformat(),
        })
        # order history: first session typically near birth; loyal families return
        n_orders = rng.choices([1, 2, 3, 4, 5, 6], weights=[40, 25, 15, 10, 6, 4])[0]
        d = dob + timedelta(days=rng.randint(5, 40))
        for _ in range(n_orders):
            if d > as_of:
                break
            prod, price = rng.choice(PRODUCTS)
            oid += 1
            orders.append({
                "order_id": f"O{oid:05d}", "customer_id": cid, "order_date": d.isoformat(),
                "amount": round(price * rng.uniform(0.9, 1.25), 2), "product": prod,
            })
            d += timedelta(days=rng.randint(60, 260))
        if not any(o["customer_id"] == cid for o in orders):
            oid += 1
            orders.append({"order_id": f"O{oid:05d}", "customer_id": cid,
                           "order_date": (as_of - timedelta(days=rng.randint(130, 400))).isoformat(),
                           "amount": 9500.0, "product": "Newborn session"})
    return customers, orders


def write_csv(out: Path, as_of: date) -> None:
    out.mkdir(parents=True, exist_ok=True)
    customers, orders = generate(as_of)
    for name, rows in (("customers", customers), ("orders", orders)):
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write the synthetic dataset as CSV (e.g. for `bq load`).")
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--as-of", default=date.today().isoformat())
    a = ap.parse_args()
    write_csv(Path(a.out), date.fromisoformat(a.as_of))
    print(f"wrote {a.out}/customers.csv and orders.csv")
