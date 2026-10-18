# ReKindle: instructions for Claude Code

A working POC for the Google Cloud x Hack2skill AI Builder Cup. It finds dormant customers of a baby-photography studio (Baby Trails), drafts WhatsApp re-engagement with Gemini, fact-checks every draft, and routes it to the owner (or auto-sends once trust is earned). Read `docs/TEAM_HANDOFF.md` first: it has the full status, to-do order and open questions.

## Commands
```bash
pip install -r requirements-dev.txt
python -m pytest -q                                        # 69 tests, no credentials needed
REKINDLE_AS_OF=2026-10-18 uvicorn rekindle.api:app_factory --factory --port 8080   # cockpit; click "Load demo scenario"
python scripts/live_check.py                               # preflight for live Gemini / Firestore / BigQuery (mode-dependent)
python scripts/eval_guardrail.py --json docs/guardrail_eval.json
python scripts/build_deck.py                               # rebuilds docs/deck/*.pptx (computes numbers from a real run)
```
Modes via `REKINDLE_MODE`: `local` (default; SQLite, in-memory, offline stub drafter), `spark` (SQLite + Firestore + Gemini by API key, no billing), `gcp` (BigQuery + Firestore + Vertex AI, needs billing). `REKINDLE_DATA`, `REKINDLE_STORE`, `REKINDLE_LLM` (`offline|apikey|vertex`) override one piece.

## What is verified and what is not
Verified: everything in `local` mode (69 tests, run in a browser). **Not yet run live:** Gemini 3.8 Flash, Firestore, BigQuery, Cloud Run, the Dockerfile and deploy scripts, the Airtable fetch, WhatsApp and Gmail sending. The first live run will likely need small fixes. Do the live check first; it is the biggest unknown.

## Rules for working here
- **Never print, log, commit or ask me to paste secrets** (API keys, service-account JSON, tokens). Read them from environment variables only. List variable names, never values.
- **Synthetic or masked data only** with the free Gemini API tier (Google may use free-tier requests to improve its products).
- Use a **separate test project**. Never touch `baby-trails-28253` (the studio's live system) and never send a real WhatsApp message: keep `REKINDLE_SEND_MODE=dry_run`.
- Prefer the minimum IAM roles (`datastore.user`, `bigquery.dataEditor`, `bigquery.jobUser`, `aiplatform.user`). Delete any service-account key you create when done.
- Do not open PRs or push to `main` unless asked. Work on branch `claude/prototype-and-submission`.
- Do not claim something works unless you ran it. Report failures with the output. Label demo figures as simulated.

## Gemini facts that are easy to get wrong
Model `gemini-3.8-flash`. Steer with `thinking_level` (LOW|MEDIUM|HIGH; MINIMAL is rejected); do **not** set `temperature`. On Vertex it is served from the `global` endpoint (`GEMINI_LOCATION`), which is unconfirmed for this project. Structured output uses `response_schema=DraftOut`.

## Design invariants (do not weaken without asking)
Deterministic SQL decides who and when; Gemini only writes; the verifier (`rekindle/verifier.py`) and the owner decide what is sent. Opt-in and suppression are checked before any generation. Baby Trails' `Marketing` field is photo-use consent, **never** messaging consent; ReKindle only reads a `Re-engagement Opt-in` flag, which does not exist yet, so no real customer is eligible today (see `docs/BABYTRAILS_INTEGRATION.md`). Nothing auto-sends until 20 owner decisions; milestone messages and discounts always go to the owner; the opt-out line is added by the system, never the model. Guardrail failures should fail closed.

## Layout
`rekindle/` engine, verifier, routing, drafting (Gemini + offline stub), store, channels, api, `ui/index.html` (cockpit) · `sql/` · `tests/` · `scripts/` · `deploy/` (`spark_bootstrap.sh`, `setup_gcp.sh`, `deploy.sh`) · `docs/`.

## Suggested first tasks, in order
1. Confirm the hackathon deadline and rules on the official Hack2skill page (they could not be fetched earlier).
2. Run `python -m pytest -q`, then `scripts/live_check.py` in the cheapest live mode available (`REKINDLE_LLM=apikey` with `GEMINI_API_KEY`), and fix what fails. Read any BLOCK reasons before changing prompts or rules.
3. If a Firebase project exists: `./deploy/spark_bootstrap.sh <project-id>` or the `spark` mode. If billing exists: `deploy/setup_gcp.sh` then `deploy/deploy.sh`.
4. Reword the two deck lines that imply live customers ("Pilot partner" on slide 2, "measured on Babytrail's data at the Nov 6 evaluation" on the performance slide) to "POC built with Baby Trails; pilot planned", then rebuild the deck.
