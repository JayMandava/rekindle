# Integrating with Baby Trails

Source reviewed: [JayMandava/baby-trails](https://github.com/JayMandava/baby-trails) at `d3c83e2` (read-only; nothing in that repo was changed).

## What Baby Trails already gives us

| Need | Baby Trails today | ReKindle uses it as |
|---|---|---|
| Customer + order history | SQLite `bookings`, mirrored to the Airtable `Bookings` table (`Ref, Client Name, Phone, Shoot Type, Baby Age, Package, Marketing, Shoot Slot, Total, Advance, Add-ons, Stage, Studio Stage, Advance Paid, Balance Paid, ...`) | Source of `customers` and `orders` via `rekindle/babytrails.py` and `scripts/import_babytrails.py` |
| WhatsApp channel | WhatsApp Cloud API: send, buttons, templates, template-approval checks, 24h-window tracking (`last_inbound_at`) | The same number and the same Meta app, so delivery and templates reuse its setup |
| Catalog | `config/catalog.json`: shoot types (newborn 5-30 days, baby 3-12 months, maternity, mini, ...) and packages | Journey rules: newborn customers are offered the Baby session at about 3-5 months; first-birthday outreach |
| Hosting | e2-micro VM in GCP project `baby-trails-28253` | Same project; ReKindle runs on Cloud Run beside it |
| Re-engagement hook | `mark_collected` already sets `reEngagement: true` when a booking closes | The natural trigger point once consent is captured |

## What the source data does NOT contain (and what we did about it)

1. **No messaging consent.** The `Marketing` field is consent to use photos on social media in exchange for 15% off. It is not consent to receive promotional WhatsApp messages, and ReKindle never treats it as such. `bookings_to_rows` only sets `consent_whatsapp` from a `Re-engagement Opt-in` checkbox, which does not exist yet. **Today, zero customers are eligible.** `import_babytrails.py` prints a warning when that is the case.
2. **No child name.** Only the baby's age at booking ("4 months"). Drafts say "your little one" and never invent a name. A `Child Name` column is read if it ever appears.
3. **No birth date.** We estimate it as shoot date minus age, so milestones are quoted at month granularity ("turns 1 in November 2026"), never as exact dates. Maternity bookings never produce a baby, on purpose.
4. **No email, no language preference.** WhatsApp-only; English-only for the pilot, because WhatsApp templates are approved per language.

## Changes needed on the Baby Trails side before a real pilot

These are proposals. I have not made them (the repo is attached read-only), and they have not been run against Baby Trails' own test suite. Say the word and I will open a PR there.

### 1. Capture opt-in (the blocker)

Ask once, in the chat, with a timestamp, the same way `partnerConsent` is stored. Natural place: right after the marketing-discount question in `flow.js` (`convo === 'pick_marketing'`), as a new `pick_reengage` step:

> "Would you like occasional WhatsApp messages from Baby Trails about milestone sessions for your little one? You can reply STOP at any time." [Yes, please] [No, thanks]

Store `d.reengageConsent = { at, by, answer }`, add a checkbox field `Re-engagement Opt-in` (plus `Opt-in At`) to the Airtable `SCHEMA`, and mirror it in `pushToAirtable`.

For customers who already booked, no promotional message can be sent to ask. Practical routes: a "Get milestone reminders" button on the gallery page and a QR code at the studio, both opening `wa.me/<studio number>?text=REMIND%20ME`. The customer's own inbound message opens the 24h window and is the opt-in, and Baby Trails records it.

### 2. One webhook, so Baby Trails must route inbound messages

A WhatsApp number has a single webhook and Baby Trails owns it. ReKindle cannot receive replies directly. Needed in `handleInbound`:

- Any sender, any booking state: if the text is STOP (see `rekindle/consent.py` for the multilingual list), set the opt-out on every booking for that number and `POST {rekindle}/api/inbound {"phone": "...", "text": "STOP"}`. Today only *partners* can STOP, and a client's "stop" would be fed into the booking flow.
- A returning customer with no open booking who replies within about 7 days of a ReKindle message: forward to `POST {rekindle}/api/inbound`, then start the normal enquiry flow with the name pre-filled instead of asking for it. That reply is the lead.

ReKindle's endpoint returns `{"intent": "interested|question|not_interested|stop|other", ...}`; the WhatsApp Cloud API payload format is also accepted directly at `/webhooks/whatsapp`.

### 3. Templates

ReKindle's message is a **Marketing**-category template (higher per-message cost than the utility templates Baby Trails uses today). Submit it with the same mechanism as `scripts/setup-templates.js`:

- name `rk_reengage_v1`, language `en`
- body: `Hi {{1}}, this is {{2}} with a note about your little one. {{3}} You can reply STOP anytime to opt out.`
- samples: `Priya`, `Baby Trails`, `Your baby is about 4 months old, right in the window for a baby milestone session (babies aged 3 to 12 months). We'd love to see you again.`

Variables cannot contain newlines, tabs or 5+ spaces; the verifier enforces this. Meta may still reject a variable-heavy template; if so, add fixed text around `{{3}}`.

## Open questions for Venkat

- Prices and packages in `catalog.json` are placeholders there. The offers ReKindle may use (`Merchant.offers`: a complimentary mini print set, 10% off milestone sessions) are my placeholders too and need his approval.
- Is a Baby session pitch to newborn customers at about 3-5 months the right timing and wording for the studio?
- Festival mini sessions (a category in the catalog) are an obvious seasonal trigger; what are the dates?
- Is the Tamil-speaking share of customers large enough to justify a Tamil template and native-speaker review?

## Pilot data path

```bash
python scripts/import_babytrails.py --airtable        # needs AIRTABLE_TOKEN and AIRTABLE_BASE_ID
REKINDLE_BOOKINGS_JSON=export.json uvicorn rekindle.api:app_factory --factory   # local cockpit on a saved export
```
