"""Customer data access. Both engines run sql/segments.sql and return identical row shapes."""
from __future__ import annotations

import csv
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Protocol

from .config import Merchant, Settings

SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "segments.sql"
_DAYS = re.compile(r"\{days_between\(([^,]+),\s*([^)]+)\)\}")


def _sqlite_sql(sql: str) -> str:
    sql = sql.replace("{orders}", "orders").replace("{customers}", "customers")
    sql = _DAYS.sub(lambda m: f"CAST(julianday({m.group(1)}) - julianday({m.group(2)}) AS INTEGER)", sql)
    return re.sub(r"@(\w+)", r":\1", sql)


def _bq_sql(sql: str, dataset: str) -> str:
    sql = sql.replace("{orders}", f"`{dataset}.orders`").replace("{customers}", f"`{dataset}.customers`")
    return _DAYS.sub(lambda m: f"DATE_DIFF({m.group(1)}, {m.group(2)}, DAY)", sql)


class DataSource(Protocol):
    def segment_rows(self, as_of: date, merchant: Merchant) -> list[dict]: ...
    def add_order(self, customer_id: str, order_date: date, amount: float, product: str) -> None: ...


class LocalDataSource:
    """SQLite in memory, loaded from CSV (or the seeded synthetic generator)."""

    def __init__(self, customers: list[dict], orders: list[dict]):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """CREATE TABLE customers (customer_id TEXT PRIMARY KEY, merchant_id TEXT, name TEXT, phone TEXT,
                 email TEXT, language TEXT, consent_whatsapp INT, consent_email INT, anchor_name TEXT, anchor_date TEXT);
               CREATE TABLE orders (order_id TEXT PRIMARY KEY, customer_id TEXT, order_date TEXT, amount REAL, product TEXT);"""
        )
        self.db.executemany(
            "INSERT INTO customers VALUES (:customer_id,:merchant_id,:name,:phone,:email,:language,"
            ":consent_whatsapp,:consent_email,:anchor_name,:anchor_date)", customers)
        self.db.executemany(
            "INSERT INTO orders VALUES (:order_id,:customer_id,:order_date,:amount,:product)", orders)
        self._next = len(orders)

    @classmethod
    def from_csv(cls, folder: Path) -> "LocalDataSource":
        def rd(n):
            with open(folder / f"{n}.csv", newline="") as f:
                return list(csv.DictReader(f))
        return cls(rd("customers"), rd("orders"))

    def segment_rows(self, as_of: date, merchant: Merchant) -> list[dict]:
        cur = self.db.execute(
            _sqlite_sql(SQL_PATH.read_text()),
            {"as_of": as_of.isoformat(), "dormant_days": merchant.dormant_days, "lost_days": merchant.lost_days},
        )
        return [dict(r) for r in cur.fetchall()]

    def add_order(self, customer_id, order_date, amount, product):
        self._next += 1
        self.db.execute("INSERT INTO orders VALUES (?,?,?,?,?)",
                        (f"O{self._next:05d}", customer_id, order_date.isoformat(), amount, product))


class BigQueryDataSource:
    def __init__(self, settings: Settings):
        from google.cloud import bigquery

        self.bq = bigquery
        self.client = bigquery.Client(project=settings.project or None)
        self.ds = f"{settings.project}.{settings.bq_dataset}" if settings.project else settings.bq_dataset

    def segment_rows(self, as_of: date, merchant: Merchant) -> list[dict]:
        sql = _bq_sql(SQL_PATH.read_text(), self.ds)
        params = [
            self.bq.ScalarQueryParameter("as_of", "DATE", as_of),
            self.bq.ScalarQueryParameter("dormant_days", "INT64", merchant.dormant_days),
            self.bq.ScalarQueryParameter("lost_days", "INT64", merchant.lost_days),
        ]
        job = self.client.query(sql, job_config=self.bq.QueryJobConfig(query_parameters=params))
        rows = []
        for r in job.result():
            d = dict(r.items())
            for k in ("last_order_date", "anchor_date"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            d["monetary"] = float(d["monetary"])
            rows.append(d)
        return rows

    def add_order(self, customer_id, order_date, amount, product):
        import uuid

        err = self.client.insert_rows_json(f"{self.ds}.orders", [{
            "order_id": f"live-{uuid.uuid4().hex[:10]}", "customer_id": customer_id,
            "order_date": order_date.isoformat(), "amount": amount, "product": product}])
        if err:
            raise RuntimeError(err)
