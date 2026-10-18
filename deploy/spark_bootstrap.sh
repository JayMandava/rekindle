#!/usr/bin/env bash
# One-paste live test of ReKindle on the Firebase Spark plan. Run it in Google Cloud Shell
# (https://shell.cloud.google.com), where gcloud is already signed in as you.
#
#   ./deploy/spark_bootstrap.sh YOUR_FIREBASE_PROJECT_ID
#
# What it does: enables Firestore, creates the database if missing, creates a service account holding ONLY
# roles/datastore.user, mints a temporary key, asks you for a Gemini API key (typed hidden, never echoed or
# written to disk), runs scripts/live_check.py, then DELETES the key. Nothing secret appears in the output,
# so it is safe to paste the output back to whoever is helping.
set -euo pipefail

PROJECT="${1:-${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}}"
[ -n "$PROJECT" ] || { echo "usage: $0 <firebase-project-id>" >&2; exit 2; }
LOCATION="${FIRESTORE_LOCATION:-nam5}"        # Firestore multi-region; pick the one you chose in the Firebase console if it exists
SA="rekindle-poc"; SA_EMAIL="${SA}@${PROJECT}.iam.gserviceaccount.com"
WORK="$(mktemp -d)"; KEY="${WORK}/key.json"; KEY_ID=""
cd "$(dirname "$0")/.."

cleanup() {
  if [ -n "$KEY_ID" ]; then
    gcloud iam service-accounts keys delete "$KEY_ID" --iam-account="$SA_EMAIL" --quiet >/dev/null 2>&1 \
      && echo "temporary service-account key deleted" || echo "WARNING: could not delete key $KEY_ID; delete it in the console" >&2
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "== project: $PROJECT"
gcloud config set project "$PROJECT" >/dev/null
gcloud services enable firestore.googleapis.com iam.googleapis.com >/dev/null

if gcloud firestore databases describe >/dev/null 2>&1; then
  echo "== firestore database exists"
else
  echo "== creating firestore database ($LOCATION)"
  gcloud firestore databases create --location="$LOCATION" --type=firestore-native >/dev/null
fi

gcloud iam service-accounts describe "$SA_EMAIL" >/dev/null 2>&1 \
  || gcloud iam service-accounts create "$SA" --display-name="ReKindle POC (temporary)" >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/datastore.user" --condition=None >/dev/null
gcloud iam service-accounts keys create "$KEY" --iam-account="$SA_EMAIL" >/dev/null
KEY_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['private_key_id'])" "$KEY")"

if [ -z "${GEMINI_API_KEY:-}" ]; then
  read -rsp "Gemini API key from https://aistudio.google.com/apikey (input hidden): " GEMINI_API_KEY; echo
fi

echo "== installing dependencies"
python3 -m venv "${WORK}/venv" && . "${WORK}/venv/bin/activate"
pip install -q -r requirements.txt

echo "== waiting 20s for the IAM grant to propagate"; sleep 20
echo "== live check"
REKINDLE_MODE=spark GOOGLE_CLOUD_PROJECT="$PROJECT" GOOGLE_APPLICATION_CREDENTIALS="$KEY" GEMINI_API_KEY="$GEMINI_API_KEY" \
  python scripts/live_check.py || STATUS=$?
echo
echo "== done (exit ${STATUS:-0}). The output above contains no credentials."
exit "${STATUS:-0}"
