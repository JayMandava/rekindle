# Before you submit (things only the team can do)

- [ ] Confirm the real deadline and rules on the official AI Builder Cup / Hack2skill page. They could not be fetched from the build environment.
- [ ] Deploy: `./deploy/setup_gcp.sh && ./deploy/deploy.sh`, put the Cloud Run URL on slide 13, and protect it (IAP) if it will hold real data.
- [ ] Run the live path once: set `REKINDLE_MODE=gcp`, run a campaign, confirm Gemini drafts pass the guardrail. Tune `GEMINI_MODEL` if needed. Expect some drafts to be blocked on the first real run; that is the guardrail working, but check the reasons.
- [ ] Build the Looker Studio dashboard on `rekindle.v_campaign_performance` and add a screenshot.
- [ ] Submit the WhatsApp template `reengage_v1` for approval: "Hi {{1}}, this is {{2}}. {{3}} Reply STOP to opt out."
- [ ] Load Babytrail's real customers and consent flags (`bq load`), run a small pilot, and replace the simulated figures on the performance slide with measured ones (auto-send rate, approval latency, time saved, recovered revenue).
- [ ] Record the 3-minute demo video (suggested flow: segments -> run campaign -> blocked draft -> approve -> STOP reply -> dashboard) and add the link.
- [ ] Replace the team circles with photos. Make the repo public.
