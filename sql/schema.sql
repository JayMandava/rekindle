-- BigQuery DDL. Replace `rekindle` with your dataset (BQ_DATASET).
CREATE SCHEMA IF NOT EXISTS rekindle;

CREATE TABLE IF NOT EXISTS rekindle.customers (
  customer_id STRING NOT NULL,
  merchant_id STRING NOT NULL,
  name STRING, phone STRING, email STRING, language STRING,
  consent_whatsapp BOOL, consent_email BOOL, consent_ts TIMESTAMP,
  anchor_name STRING,   -- child's first name (optional; Baby Trails does not collect it today)
  anchor_date DATE      -- ESTIMATED birth date = shoot date - age at shoot; drives milestone triggers
);

CREATE TABLE IF NOT EXISTS rekindle.orders (
  order_id STRING NOT NULL,
  customer_id STRING NOT NULL,
  order_date DATE NOT NULL,
  amount NUMERIC NOT NULL,
  product STRING,
  shoot_type STRING   -- newborn | baby | maternity | ...
);

-- Append-only audit log written by the agent (draft, route, decision, send, reply, order).
CREATE TABLE IF NOT EXISTS rekindle.events (
  ts TIMESTAMP NOT NULL,
  kind STRING NOT NULL,
  customer_id STRING,
  draft_id STRING,
  segment STRING,
  channel STRING,
  route STRING,
  risk_tier STRING,
  confidence FLOAT64,
  amount NUMERIC,
  detail STRING
);
