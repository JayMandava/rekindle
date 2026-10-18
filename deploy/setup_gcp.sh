#!/usr/bin/env bash
# One-time Google Cloud setup: APIs, BigQuery dataset + tables, Firestore, sample data.
# Usage: PROJECT=my-project REGION=us-central1 ./deploy/setup_gcp.sh
set -euo pipefail
: "${PROJECT:?set PROJECT}"; REGION="${REGION:-us-central1}"; DS="${BQ_DATASET:-rekindle}"
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com \
  firestore.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com storage.googleapis.com
gcloud firestore databases create --location="$REGION" --type=firestore-native 2>/dev/null || echo "firestore exists"
sed "s/rekindle/${DS}/g" sql/schema.sql | bq query --use_legacy_sql=false --project_id="$PROJECT"
# Synthetic Baby Trails-shaped data so the pipeline runs end to end. For the pilot, replace with the real bookings:
#   python3 scripts/import_babytrails.py --airtable --out data/sample   (needs AIRTABLE_TOKEN, AIRTABLE_BASE_ID)
python3 -m rekindle.sample --out data/sample --as-of "$(date +%F)"
bq load --source_format=CSV --skip_leading_rows=1 --replace "${DS}.customers" data/sample/customers.csv \
  customer_id:STRING,merchant_id:STRING,name:STRING,phone:STRING,email:STRING,language:STRING,consent_whatsapp:BOOL,consent_email:BOOL,anchor_name:STRING,anchor_date:DATE
bq load --source_format=CSV --skip_leading_rows=1 --replace "${DS}.orders" data/sample/orders.csv \
  order_id:STRING,customer_id:STRING,order_date:DATE,amount:NUMERIC,product:STRING,shoot_type:STRING
sed "s/rekindle/${DS}/g" sql/dashboard.sql | bq query --use_legacy_sql=false --project_id="$PROJECT"
echo "done. Next: ./deploy/deploy.sh"
