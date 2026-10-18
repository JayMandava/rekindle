#!/usr/bin/env bash
# Build from source and deploy to Cloud Run. The service account needs:
#   roles/aiplatform.user, roles/bigquery.dataEditor, roles/bigquery.jobUser, roles/datastore.user
set -euo pipefail
: "${PROJECT:?set PROJECT}"; REGION="${REGION:-us-central1}"; SVC="${SERVICE:-rekindle}"
SA="${SA:-${SVC}@${PROJECT}.iam.gserviceaccount.com}"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create "$SVC"
for r in aiplatform.user bigquery.dataEditor bigquery.jobUser datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="roles/$r" --condition=None >/dev/null
done
gcloud run deploy "$SVC" --source . --region "$REGION" --service-account "$SA" --allow-unauthenticated \
  --set-env-vars "REKINDLE_MODE=gcp,REKINDLE_SEND_MODE=${SEND_MODE:-dry_run},GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash},BQ_DATASET=${BQ_DATASET:-rekindle}"
echo "NOTE: --allow-unauthenticated exposes the cockpit. Put it behind IAP or Firebase Auth before real customer data."
