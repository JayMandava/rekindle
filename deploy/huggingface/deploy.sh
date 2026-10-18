#!/usr/bin/env bash
# Deploy ReKindle to a free Hugging Face Space (Gradio SDK; the Docker SDK is paid). No billing needed.
#   HF_TOKEN=<write token> ./deploy/huggingface/deploy.sh jmandava/rekindle
# One-time, in the Space's Settings:
#   secret   GOOGLE_APPLICATION_CREDENTIALS_JSON  (Firebase service-account key, JSON text)
#   variable REKINDLE_MODE=spark  GOOGLE_CLOUD_PROJECT=<project-id>  REKINDLE_SEND_MODE=dry_run  REKINDLE_LLM=offline
#   (drop REKINDLE_LLM and add secret GEMINI_API_KEY to draft with Gemini)
set -euo pipefail
SPACE="${1:?usage: HF_TOKEN=... $0 <owner/space>}"; : "${HF_TOKEN:?set HF_TOKEN}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"; WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cp -r "$ROOT/rekindle" "$ROOT/sql" "$ROOT/requirements.txt" "$ROOT/deploy/huggingface/app.py" "$WORK/"
find "$WORK" -name __pycache__ -prune -exec rm -rf {} +
cat > "$WORK/README.md" <<'EOF'
---
title: ReKindle
emoji: 🕯️
colorFrom: yellow
colorTo: red
sdk: gradio
sdk_version: 5.49.1
python_version: "3.12"
app_file: app.py
pinned: false
---

ReKindle: AI re-engagement for a baby-photography studio (POC, synthetic data, dry-run sending).
Source: https://github.com/JayMandava/rekindle
EOF
cd "$WORK" && git init -q -b main && git add -A
git -c user.name=rekindle -c user.email=rekindle@users.noreply.github.com commit -q -m "Deploy ReKindle"
AUTH="Authorization: Basic $(printf 'hf:%s' "$HF_TOKEN" | base64)"
git -c http.extraheader="$AUTH" push -q --force "https://huggingface.co/spaces/${SPACE}" main
echo "pushed; https://huggingface.co/spaces/${SPACE}"
