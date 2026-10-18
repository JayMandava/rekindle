# ReKindle: team handoff

Everything below is on branch `claude/prototype-and-submission` of `JayMandava/rekindle`. No PR has been opened and `main` is untouched.

## 1. Where things stand

ReKindle is a working POC: a loop that finds dormant customers, drafts a WhatsApp message with Gemini, fact-checks it, and routes it to the owner (or auto-sends once trust is earned). It runs end to end **locally on synthetic data**. Nothing has run against live Google services yet, because the build environment had no credentials.

| Verified (69 tests, plus run in a browser) | Not verified yet |
|---|---|
| Segmentation SQL, opt-in and STOP handling, fact-check guardrail, risk routing, trust learning, API, owner cockpit, Baby Trails adapter | Gemini 3.8 Flash calls (config validated against the SDK, call logic tested with a fake client) |
| Guardrail benchmark: 1,864 deliberately corrupted drafts, all blocked, 0 reached a customer without a human, 0% of clean drafts wrongly blocked (our own test set, on synthetic data, so not an independent benchmark) | Firestore, BigQuery, Cloud Run, Looker Studio, the Dockerfile and deploy scripts |
| SQL parses as valid BigQuery | Real Airtable data, WhatsApp sending, Gmail sending |

**Deadline:** one third-party listing gave the prototype deadline as **18 Oct 2026**, which may already be today. The hackathon site could not be opened from the build environment. **Check the official AI Builder Cup / Hack2skill page first** for dates, rules and judging criteria.

## 2. Do these first (in order)

1. **Confirm the real deadline and rules** on the Hack2skill page.
2. **Run the live check** (section 3). It is the single biggest unknown and takes about 5 minutes.
3. **Fix the opt-in gap** (section 5). Without it no real customer is eligible to be messaged.
4. **Record the 3-minute demo video** and add the links on slide 13: repo, video, product URL. Suggested flow: segments, run campaign, a blocked draft, approve, a STOP reply, dashboard.
5. **Reword two deck lines** that imply live customers (slide 2 "Pilot partner", slide 11 "measured on Babytrail's data at the Nov 6 evaluation"). Baby Trails runs on Meta's test number today, so "POC built with Baby Trails; pilot planned" is accurate.
6. Replace the team circles on slide 15 with photos, and make the repo public if it is not.

## 3. Live check (Firebase Spark plan, no billing needed)

Needs: a Firebase project on the Spark plan, and a Gemini API key. Use **synthetic or masked data only**: Google's free Gemini tier may use requests to improve its products (verify the current terms).

1. Create a project: https://console.firebase.google.com/ (stay on Spark).
2. Create a Gemini key: https://aistudio.google.com/apikey
3. Open Google Cloud Shell (already signed in as you): https://shell.cloud.google.com
4. Run:
   ```bash
   git clone -b claude/prototype-and-submission https://github.com/JayMandava/rekindle.git && cd rekindle && ./deploy/spark_bootstrap.sh YOUR_PROJECT_ID
   ```
   If the clone asks for a password the repo is private: `gh auth login`, then `gh repo clone JayMandava/rekindle -- -b claude/prototype-and-submission`.
5. Paste the Gemini key when asked (input is hidden and not saved).

The script enables Firestore, creates a service account with **only** `roles/datastore.user`, mints a temporary key, runs `scripts/live_check.py`, and **deletes the key**. The live check sends five real drafts through Gemini 3.8 Flash and the guardrail, does a Firestore write/read/delete, and tests reply classification, printing PASS or FAIL for each.

What to expect and what to do:
- Some drafts will show **BLOCK**. That is the guardrail working. Read the reasons; if Gemini keeps tripping the same rule, adjust the prompt (`SYSTEM` in `rekindle/drafting.py`) or the rule, not both blindly.
- The first Firestore check can fail if the IAM grant has not propagated. Rerun.
- If creating the database fails without billing, create it in the Firebase console and rerun.
- The script's control flow was tested against a stubbed `gcloud`, never against real Google Cloud, so expect a small fix or two.

**Without Cloud Shell**, run locally with the same variables:
```bash
export REKINDLE_MODE=spark GEMINI_API_KEY=... GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(cat serviceAccountKey.json)"   # or GOOGLE_APPLICATION_CREDENTIALS=path
pip install -r requirements.txt && python scripts/live_check.py
```

### Gemini specifics (easy to get wrong)
- Model: `gemini-3.8-flash` (GA since Sep 2026, per search results; Google's own docs could not be opened). Override with `GEMINI_MODEL`.
- Gemini 3.x is steered with `thinking_level` (LOW, MEDIUM, HIGH; `MINIMAL` is rejected). Do **not** set `temperature`. The code uses LOW (`GEMINI_THINKING_LEVEL`).
- On Vertex AI it is served from the `global` endpoint, not every region. `GEMINI_LOCATION` defaults to `global`; whether that works for your project is **unconfirmed**. The API-key route (Spark) avoids the question.

## 4. Full Google Cloud route (needs a billing account)

Use hackathon credits if you have them. This is the version the architecture slide describes: BigQuery, Cloud Run, Firestore, Looker Studio.

```bash
export PROJECT=your-test-project REGION=us-central1
./deploy/setup_gcp.sh      # APIs, BigQuery dataset/tables, Firestore, synthetic data, Looker view
./deploy/deploy.sh         # Cloud Run, REKINDLE_MODE=gcp, SEND_MODE=dry_run
REKINDLE_MODE=gcp python scripts/live_check.py
```
Service account roles needed: `aiplatform.user`, `bigquery.dataEditor`, `bigquery.jobUser`, `datastore.user`. Use a **separate test project**, not `baby-trails-28253` (the studio's live system). Then in Looker Studio connect a data source to the BigQuery view `rekindle.v_campaign_performance` and screenshot the dashboard for the deck. The dashboard itself is not built. If your organisation blocks service-account keys (`iam.disableServiceAccountKeyCreation`), run from Cloud Shell with your own login instead.

## 5. Baby Trails: what must change before any real pilot

Full detail and proposed code in [BABYTRAILS_INTEGRATION.md](BABYTRAILS_INTEGRATION.md). Source reviewed: `JayMandava/baby-trails` at `d3c83e2` (read only; nothing there was changed).

1. **Opt-in (blocker).** Baby Trails' `Marketing` flag is consent to use photos on social media, not consent to receive promotional WhatsApp messages, and ReKindle never uses it as such. ReKindle reads a `Re-engagement Opt-in` checkbox that does not exist yet, so **today zero customers are eligible**. Add one question in the booking chat, stored with a timestamp (the way `partnerConsent` is), plus the Airtable field. For past customers: a "get milestone reminders" button or QR code opening `wa.me/<studio number>?text=REMIND%20ME`.
2. **Inbound routing.** Baby Trails owns the single WhatsApp webhook. It must forward STOP and replies to ReKindle's `POST /api/inbound`. Today a client's "STOP" would be fed into the booking flow, and a re-engaged customer's reply would start a fresh enquiry.
3. **Template.** Submit `rk_reengage_v1` (Marketing category, English) with the same mechanism as Baby Trails' `scripts/setup-templates.js`. Body: `Hi {{1}}, this is {{2}} with a note about your little one. {{3}} You can reply STOP anytime to opt out.` Meta has not yet approved any of Baby Trails' templates, so this is the slowest item.
4. **Data limits to design around.** No child name (drafts say "your little one"), no birth date (milestones are estimates from age at booking, quoted by month), no email, no language preference. Maternity-only customers never get a baby message.

Data path once the above exists:
```bash
python scripts/import_babytrails.py --airtable          # needs AIRTABLE_TOKEN and AIRTABLE_BASE_ID (read-only token)
REKINDLE_BOOKINGS_JSON=export.json uvicorn rekindle.api:app_factory --factory --port 8080
```
Mask phone numbers if using real data in the POC.

## 6. Questions for Venkat (Baby Trails)

- Offers ReKindle may use. `Merchant.offers` in `rekindle/config.py` holds **my placeholders** (a complimentary mini print set; 10% off milestone sessions). Real offers and prices are needed; prices in Baby Trails' catalog are also placeholders.
- Is pitching a Baby session to newborn customers at about 3-5 months the right timing and wording?
- Festival mini sessions are an obvious seasonal trigger. What are the dates?
- Is the Tamil-speaking share large enough to justify a Tamil template and native-speaker review? (The pilot is English-only because WhatsApp templates are approved per language.)

## 7. How it behaves (decisions already made)

- **Trust policy.** Nothing auto-sends until the owner has made 20 decisions. After that only low-risk drafts above a learned confidence threshold auto-send. Journey messages (they reference the baby's age) and discounts are always high risk and always go to the owner; VIPs, customers dormant over a year, and maternity history are medium and also go to the owner. Unedited approvals lower the threshold (floor 0.70); edits (+0.02) and rejections (+0.04) raise it (ceiling 0.95).
- **Order of control.** Deterministic SQL decides who and when. Gemini only writes. Opt-in and suppression are checked before any generation. A deterministic guardrail verifies every draft; the owner decides everything sensitive.
- **Guardrail** (`rekindle/verifier.py`): every claim must quote the message verbatim and cite a fact; every number must sit inside a claim whose fact contains it; names, offers (merchant-approved only), links, pressure, guarantees and health claims are blocked; sentences that recall something about the customer must be backed by a cited claim; opt-out lines are added by the system, never the model. One regeneration on failure, then the draft is blocked.
- **Known gaps in the guardrail:** it is rule-based, so a paraphrased falsehood using none of those patterns ("Aarav must be walking by now") can pass. A second-layer Gemini entailment check is the planned fix. Capitalised-name checks do not apply to non-Latin scripts.

## 8. Other known limitations

- The cockpit has no authentication. Put it behind IAP or Firebase Auth before real customer data.
- "Time saved" assumes 3 minutes per hand-written message (`ASSUMED_MINUTES_PER_MESSAGE`). Attribution is last-touch within 30 days.
- All recovered-revenue, reply and order figures in the demo are **simulated** and labelled so. Real figures must come from a pilot, not from this data.
- Package prices, offers and journey timings are placeholders until the studio approves them.

## 9. Map of the repo

```
rekindle/   config, models, babytrails (adapter), segmentation, consent, drafting (Gemini + offline stub),
            verifier, routing, engine, store, channels, api, demo, ui/
sql/        segments.sql (runs on BigQuery and SQLite), schema.sql, dashboard.sql
tests/      69 tests (python -m pytest -q)
scripts/    live_check.py, eval_guardrail.py, import_babytrails.py, build_deck.py
deploy/     spark_bootstrap.sh (Cloud Shell), setup_gcp.sh, deploy.sh
docs/       deck/ (PPTX + PDF), diagrams/, screens/, BABYTRAILS_INTEGRATION.md, SUBMISSION_CHECKLIST.md
```
Modes (`REKINDLE_MODE`): `local` (SQLite, in-memory store, offline stub drafter, no credentials), `spark` (SQLite, Firestore, Gemini by API key), `gcp` (BigQuery, Firestore, Gemini on Vertex AI). `REKINDLE_DATA`, `REKINDLE_STORE` and `REKINDLE_LLM` override one piece at a time.

Rebuild the deck after changes: `python scripts/build_deck.py` (the demo and test numbers are computed from a real run), then export to PDF with LibreOffice.

## 10. Submission checklist

- [ ] Deadline and rules confirmed on the official page
- [ ] Live check passed (section 3), results noted
- [ ] Deck lines reworded to say POC, not live pilot
- [ ] Demo video (3 minutes) recorded; links added on slide 13
- [ ] Looker Studio dashboard screenshot added (only if the full Google Cloud route is used)
- [ ] Team photos on slide 15
- [ ] Repo public
- [ ] Opt-in, inbound routing and template requested from the Baby Trails side (section 5)
