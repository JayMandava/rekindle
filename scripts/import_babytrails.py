"""Import Baby Trails bookings into ReKindle's tables.

Sources (pick one):
  --airtable            read the Bookings table via the Airtable API (AIRTABLE_TOKEN, AIRTABLE_BASE_ID)
  --json bookings.json  a JSON list of Airtable-style rows (e.g. a saved export)
Outputs data/babytrails/customers.csv and orders.csv, ready for `bq load` (see deploy/setup_gcp.sh),
or run the local cockpit straight on the export:  REKINDLE_BOOKINGS_JSON=bookings.json uvicorn ...

Customers come out with consent_whatsapp=0 unless the booking row has the `Re-engagement Opt-in` checkbox.
That is deliberate: Baby Trails' existing `Marketing` field is photo-use consent, not messaging consent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rekindle.babytrails import bookings_to_rows
from rekindle.sample import write_csv


def fetch_airtable() -> list[dict]:
    import httpx

    base, token = os.environ["AIRTABLE_BASE_ID"], os.environ["AIRTABLE_TOKEN"]
    rows, offset = [], None
    while True:
        r = httpx.get(f"https://api.airtable.com/v0/{base}/Bookings", headers={"Authorization": f"Bearer {token}"},
                      params={"pageSize": 100, **({"offset": offset} if offset else {})}, timeout=30)
        r.raise_for_status()
        j = r.json()
        rows += [rec["fields"] for rec in j["records"]]
        offset = j.get("offset")
        if not offset:
            return rows


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--airtable", action="store_true")
    g.add_argument("--json")
    ap.add_argument("--out", default="data/babytrails")
    a = ap.parse_args()
    bookings = fetch_airtable() if a.airtable else json.loads(Path(a.json).read_text())
    customers, orders = bookings_to_rows(bookings)
    write_csv(Path(a.out), customers, orders)
    opted = sum(c["consent_whatsapp"] for c in customers)
    print(f"{len(bookings)} bookings -> {len(customers)} paying customers, {len(orders)} orders, {opted} opted in to re-engagement")
    if customers and not opted:
        print("WARNING: nobody has opted in, so ReKindle will not draft for anyone. See docs/BABYTRAILS_INTEGRATION.md.")


if __name__ == "__main__":
    main()
