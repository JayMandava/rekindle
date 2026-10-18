"""Builds the AI Builder Cup submission deck (docs/deck/ReKindle_AI_Builder_Cup.pptx) in the official template style.

Run: python scripts/build_deck.py   (then export to PDF with LibreOffice if needed)
Numbers on the performance slide come from docs/guardrail_eval.json and the seeded demo run.
"""
from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "docs/deck/assets"
SC = ROOT / "docs/screens"
DG = ROOT / "docs/diagrams"
EV = json.loads((ROOT / "docs/guardrail_eval.json").read_text())

import subprocess
import sys
from datetime import date

sys.path.insert(0, str(ROOT))
from rekindle.config import Settings
from rekindle.demo import seed_demo
from rekindle.engine import Engine

_eng = Engine.build(Settings(mode="local", send_mode="dry_run", chaos=0.2, as_of=date(2026, 10, 18)))
seed_demo(_eng)
DEMO = _eng.kpis()
CONSENT = _eng.consent()
N_TESTS = int(subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True).stdout.strip().splitlines()[-1].split()[0])

INK, MUTED = RGBColor(0x14, 0x18, 0x1F), RGBColor(0x5B, 0x64, 0x72)
BRAND, LINE = RGBColor(0xE8, 0x59, 0x0C), RGBColor(0xE3, 0xE7, 0xEE)
BLUE, BLUEBG = RGBColor(0x17, 0x4E, 0xA6), RGBColor(0xE7, 0xEF, 0xFB)
GREENBG, GREEN = RGBColor(0xE6, 0xF4, 0xEA), RGBColor(0x13, 0x73, 0x33)
REDBG, RED = RGBColor(0xFD, 0xE8, 0xE6), RGBColor(0xB3, 0x26, 0x1E)
FONT = "Arial"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = prs.slide_width, prs.slide_height


def text(slide, x, y, w, h, runs, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.1):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    paras = runs if isinstance(runs, list) else [runs]
    for i, p in enumerate(paras):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment, para.line_spacing = align, spacing
        parts = p if isinstance(p, list) else [(p, bold)]
        for t, b in parts:
            r = para.add_run()
            r.text = t
            r.font.size, r.font.bold, r.font.name, r.font.color.rgb = Pt(size), b, FONT, color
        para.space_after = Pt(size * 0.45)
    return tb


def card(slide, x, y, w, h, fill=BLUEBG, line=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    s.adjustments[0] = 0.06
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line; s.line.width = Pt(1.25)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    return s


def base(title):
    s = prs.slides.add_slide(BLANK)
    s.shapes.add_picture(str(A / "header.png"), 0, 0, width=W)
    text(s, Inches(0.5), Inches(0.82), Inches(12.3), Inches(0.6), title, size=28, bold=True)
    return s


def pic_fit(slide, path, x, y, w, h):
    from PIL import Image
    iw, ih = Image.open(path).size
    r = min(w / iw, h / ih)
    pw, ph = int(iw * r), int(ih * r)
    return slide.shapes.add_picture(str(path), x + (w - pw) // 2, y + (h - ph) // 2, pw, ph)


def trimmed(path, top=0.0, name=None):
    """Crop whitespace (and optionally the in-image title band) so diagrams fill the slide."""
    from PIL import Image, ImageChops
    im = Image.open(path).convert("RGB")
    im = im.crop((0, int(im.height * top), im.width, im.height))
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
    pad = 20
    im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad)))
    out = A / (name or Path(path).stem + "_trim.png")
    im.save(out)
    return out


def crop_to(path, box, name):
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    out = A / name
    im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))).save(out)
    return out


def bullets(slide, x, y, w, h, items, size=18, gap=0.5):
    paras = [[("•  ", True), *(it if isinstance(it, list) else [(it, False)])] for it in items]
    tb = text(slide, x, y, w, h, paras, size=size)
    for p in tb.text_frame.paragraphs:
        p.space_after = Pt(size * gap)
    return tb


# 1 ── Cover
s = prs.slides.add_slide(BLANK)
s.shapes.add_picture(str(A / "cover_top.png"), 0, 0, width=W)
text(s, Inches(0.5), Inches(4.55), Inches(12), Inches(0.6), "Team Details", size=30, bold=True)
for i, (k, v) in enumerate([("Team name", "ReKindle"), ("Team leader", "Abhishek Puvvada"),
                            ("Problem statement", "AI-powered customer re-engagement and segmentation for customer-centric commerce")]):
    text(s, Inches(1.2), Inches(5.3 + i * 0.5), Inches(11.5), Inches(0.5), [[(f"{k}: ", True), (v, False)]], size=20)

# 2 ── Brief
s = base("Brief about the idea")
text(s, Inches(0.5), Inches(1.55), Inches(12.3), Inches(1.2),
     [[("ReKindle turns a merchant's past-customer database into recurring revenue. ", True),
       ("It finds customers who have gone quiet, writes a personal WhatsApp message for each (email optional), and sends only what has been fact-checked. "
        "Human-supervised first; autonomy is earned.", False)]], size=20)
cols = [("1  Find", "BigQuery SQL scores recency, frequency and spend from Baby Trails bookings and spots the next natural session, like a newborn reaching baby-session age. No LLM.", BLUEBG),
        ("2  Write", "Gemini on Vertex AI drafts the message. Every claim must cite a fact from that customer's own record. It never invents a name, price or memory.", RGBColor(0xFE, 0xF3, 0xE0)),
        ("3  Verify", "A deterministic guardrail blocks anything ungrounded. Only customers who opted in are ever drafted for, and STOP is honoured before any generation.", REDBG),
        ("4  Earn trust", "Nothing auto-sends until the owner has reviewed 20 drafts. Then only low-risk drafts do. Milestones and discounts always go to the owner.", GREENBG)]
for i, (h, b, f) in enumerate(cols):
    x = Inches(0.5 + i * 3.1)
    card(s, x, Inches(3.1), Inches(2.9), Inches(3.05), f)
    text(s, x + Inches(0.12), Inches(3.25), Inches(2.66), Inches(0.5), h, size=20, bold=True)
    text(s, x + Inches(0.12), Inches(3.85), Inches(2.66), Inches(2.2), b, size=15)
text(s, Inches(0.5), Inches(6.25), Inches(12.3), Inches(0.9),
     "Built on Google Cloud: BigQuery, Gemini on Vertex AI, Cloud Run, Firestore, Looker Studio. POC built with Babytrail Photography (Baby Trails), whose booking system already runs on GCP; a pilot is planned. A studio is the hardest test of personalization because every message touches a family milestone; the same engine generalizes to apparel, D2C, salons and clinics.",
     size=14, color=MUTED)

# 3 ── Opportunities
s = base("Opportunities")
blocks = [("How is it different?",
           "Re-engagement tools blast templates. Most AI entries are chat wrappers or static dashboards. ReKindle is a hybrid agent: deterministic logic decides who, when and what is allowed; Gemini only writes; a deterministic verifier and the owner decide what is sent."),
          ("How does it solve the problem?",
           "Past customers are a merchant's cheapest revenue but nobody has time to write 300 personal messages. ReKindle segments the base, drafts each message grounded in that customer's history, and routes it: low-risk drafts go out automatically once trust is earned, everything else lands in a one-tap cockpit."),
          ("What is the USP?",
           f"AI speed without the hallucination risk that keeps merchants from letting AI near their customers. In our adversarial test, {EV['total_corrupted']:,} corrupted drafts were all stopped before sending, and 0 reached a customer without a human.")]
for i, (h, b) in enumerate(blocks):
    y = Inches(1.6 + i * 1.85)
    card(s, Inches(0.5), y, Inches(12.3), Inches(1.7), RGBColor(0xF6, 0xF7, 0xF9), LINE)
    text(s, Inches(0.7), y + Inches(0.08), Inches(3.3), Inches(1.5), h, size=20, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, Inches(4.0), y + Inches(0.08), Inches(8.6), Inches(1.55), b, size=15, anchor=MSO_ANCHOR.MIDDLE)

# 4 ── Features
s = base("List of features offered by the solution")
feats = [("Automated segmentation", "RFM scoring and dormancy triggers in one BigQuery query; journey triggers from the baby's estimated age"),
         ("Grounded drafts with citations", "Gemini structured output: every claim quotes the message and cites a fact id"),
         ("Fact-verification guardrail", "Blocks invented numbers, names, offers, links, pressure and fabricated memories"),
         ("Risk-tiered routing", "Low / medium / high. Milestones and discounts always need the owner"),
         ("Earned autonomy", "Auto-send unlocks after 20 owner decisions; threshold learns from approvals, edits and rejections"),
         ("Opt-in first", "No opt-in, no draft: the photo-use flag is never treated as messaging consent. STOP suppresses before generation and cancels queued drafts"),
         ("WhatsApp-first delivery", "Approved Marketing template for dormant customers (24h rule); email optional; opt-out line added by the system"),
         ("Owner cockpit + dashboard", "Real-time Firestore queue with claims shown next to facts; BigQuery view for Looker Studio")]
for i, (h, b) in enumerate(feats):
    x, y = Inches(0.5 + (i % 2) * 6.2), Inches(1.55 + (i // 2) * 1.37)
    card(s, x, y, Inches(6.0), Inches(1.25), BLUEBG if i % 2 == 0 else GREENBG)
    text(s, x + Inches(0.15), y + Inches(0.06), Inches(5.7), Inches(0.4), h, size=17, bold=True)
    text(s, x + Inches(0.15), y + Inches(0.46), Inches(5.7), Inches(0.8), b, size=13)

# 5 ── Process flow
s = base("Process flow diagram")
pic_fit(s, trimmed(DG / "flow.png", top=0.12), Inches(0.4), Inches(1.5), Inches(12.5), Inches(5.8))

# 6 ── Wireframes (annotated real UI)
s = base("Wireframes: the owner cockpit (live prototype)")
pic_fit(s, SC / "cockpit-review.png", Inches(0.3), Inches(1.5), Inches(8.6), Inches(5.7))
notes = [("Highlighted words", "each claim in the message, hover to see its source fact"),
         ("Fact chips", "the customer-record fields the draft is allowed to use"),
         ("Risk + confidence", "why this draft needs a human"),
         ("Autonomy meter", "warm-up progress, then the learned auto-send threshold"),
         ("Approve / Edit / Reject", "edits are re-verified; every decision tunes the threshold")]
for i, (h, b) in enumerate(notes):
    y = Inches(1.6 + i * 1.1)
    text(s, Inches(9.1), y, Inches(3.9), Inches(1.0), [[(f"{i+1}  {h}: ", True), (b, False)]], size=14)

# 7 ── Architecture
s = base("Architecture diagram of the proposed solution")
pic_fit(s, trimmed(DG / "architecture.png", top=0.16), Inches(0.4), Inches(1.5), Inches(12.5), Inches(5.8))

# 7b ── Baby Trails integration
s = base("Built on a real studio: the Baby Trails integration")
cols = [("What we read", GREENBG, [
            "Baby Trails' Airtable Bookings: phone, shoot type, baby age, package, totals, paid flags",
            "Its catalog: newborn 5-30 days, baby 3-12 months, maternity",
            "Same WhatsApp number and GCP project; ReKindle runs beside it"]),
        ("What we never assume", REDBG, [
            "Its photo-use flag is not messaging consent",
            "No child name on file, so drafts say 'your little one'",
            "Only an age at booking, so milestones are estimates, quoted by month",
            "Maternity history never produces a baby message"]),
        ("What the pilot needs", BLUEBG, [
            "An opt-in question at booking: today none of the studio's customers are eligible",
            "Inbound routing: STOP and replies forwarded to ReKindle",
            "An approved Marketing template (rk_reengage_v1)",
            "Venkat's real prices and approved offers"])]
for i, (h, f, items) in enumerate(cols):
    x = Inches(0.5 + i * 4.2)
    card(s, x, Inches(1.6), Inches(4.0), Inches(4.7), f)
    text(s, x + Inches(0.15), Inches(1.7), Inches(3.7), Inches(0.5), h, size=20, bold=True)
    bullets(s, x + Inches(0.15), Inches(2.3), Inches(3.7), Inches(3.9), items, size=16, gap=0.55)
text(s, Inches(0.5), Inches(6.5), Inches(12.3), Inches(0.6), "Reviewed against the Baby Trails repo. Details and proposed changes: docs/BABYTRAILS_INTEGRATION.md", size=13, color=MUTED)

# 8 ── Technologies
s = base("Technologies used in the solution")
rows = [("Technology", "Role in ReKindle"),
        ("Gemini 3.8 Flash on Vertex AI", "Message drafting with structured output (response_schema) that forces claim-to-fact citations; reply-intent classification"),
        ("BigQuery", "Source of truth for customers and orders; deterministic RFM + dormancy SQL; append-only event log"),
        ("Cloud Run", "Agent orchestration (FastAPI), owner cockpit UI, WhatsApp webhook"),
        ("Firestore", "Real-time draft queue, trust state and suppression list for the cockpit"),
        ("Looker Studio", "Dashboard over a BigQuery view: recovered revenue, auto-send and reply rates"),
        ("Baby Trails (existing)", "Airtable bookings are the customer and order source; its server owns the WhatsApp number and webhook"),
        ("Gmail API (optional)", "Email with the system-added opt-out line; Baby Trails holds no emails today"),
        ("WhatsApp Cloud API", "Delivery channel only (Meta-run), approved templates; the rest of the stack is Google")]
tbl = s.shapes.add_table(len(rows), 2, Inches(0.5), Inches(1.55), Inches(12.3), Inches(5.5)).table
tbl.columns[0].width, tbl.columns[1].width = Inches(3.2), Inches(9.1)
for r, (a, b) in enumerate(rows):
    for c, v in enumerate((a, b)):
        cell = tbl.cell(r, c)
        cell.text = v
        p = cell.text_frame.paragraphs[0]
        p.runs[0].font.size, p.runs[0].font.name = Pt(16 if r == 0 else 13), FONT
        p.runs[0].font.bold = r == 0 or c == 0
        p.runs[0].font.color.rgb = RGBColor(255, 255, 255) if r == 0 else INK
        cell.fill.solid(); cell.fill.fore_color.rgb = INK if r == 0 else (RGBColor(0xF6, 0xF7, 0xF9) if r % 2 else RGBColor(255, 255, 255))
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

# 9 ── Cost
s = base("Estimated implementation cost")
text(s, Inches(0.5), Inches(1.55), Inches(12.3), Inches(1.0),
     "The MVP runs within Google Cloud hackathon credits. Every cost driver is consumption-based, and the design keeps the expensive part (the LLM) to one call per message, two at most.", size=18)
bullets(s, Inches(0.7), Inches(2.9), Inches(11.8), Inches(3.8), [
    [("Gemini on Vertex AI: ", True), ("scales with messages drafted; one call per message, plus one regeneration only when the guardrail blocks a draft", False)],
    [("BigQuery: ", True), ("scales with customer records scanned; segmentation is one query per campaign run", False)],
    [("Cloud Run: ", True), ("pay-per-request, scales to zero between campaigns", False)],
    [("Firestore: ", True), ("scales with cockpit activity (drafts written, decisions made)", False)],
    [("WhatsApp Business API: ", True), ("per-conversation fees from the provider; email via Gmail API has no per-message fee", False)]], size=19)

# 10 ── Snapshots
s = base("Snapshots of the prototype")
pic_fit(s, SC / "cockpit-review.png", Inches(0.3), Inches(1.5), Inches(7.0), Inches(4.9))
text(s, Inches(0.3), Inches(6.4), Inches(7.0), Inches(0.6), "Owner review queue: claims highlighted against their source facts; autonomy meter shows trust earned", size=13, color=MUTED, align=PP_ALIGN.CENTER)
pic_fit(s, SC / "blocked-card.png", Inches(7.5), Inches(1.7), Inches(5.5), Inches(4.5))
text(s, Inches(7.5), Inches(6.4), Inches(5.5), Inches(0.6), "Guardrail at work: an invented 20% discount is blocked and never reaches the customer", size=13, color=MUTED, align=PP_ALIGN.CENTER)
text(s, Inches(0.5), Inches(6.95), Inches(12.3), Inches(0.4), "Running prototype on synthetic customer data, not real customers.", size=12, color=MUTED)

# 11 ── Performance
s = base("Prototype performance report / benchmarking")
kp = [(f"{EV['total_corrupted']:,}", "adversarial drafts tested"), (f"{EV['total_blocked']:,}", "stopped by the guardrail"),
      (str(EV["total_unsafe_auto_sent"]), "reached a customer without a human"), (f"{EV['clean_false_block_rate']:.0%}", "good drafts wrongly blocked")]
for i, (v, l) in enumerate(kp):
    x = Inches(0.5 + i * 3.1)
    card(s, x, Inches(1.55), Inches(2.9), Inches(1.45), GREENBG if i in (1, 2, 3) else BLUEBG)
    text(s, x, Inches(1.6), Inches(2.9), Inches(0.8), v, size=34, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + Inches(0.1), Inches(2.4), Inches(2.7), Inches(0.6), l, size=13, align=PP_ALIGN.CENTER)
bullets(s, Inches(0.5), Inches(3.2), Inches(12.3), Inches(2.6), [
    f"{len(EV['corruptions'])} corruption types a hallucinating model could produce (invented discount, wrong age, invented name, fake product, pressure, links, guarantees, fabricated memories) applied to all {EV['targets']} outreach targets, with auto-send fully unlocked and the threshold at its floor.",
    f"Seeded demo run on synthetic Baby Trails-shaped data ({CONSENT['total']} customers, {CONSENT['opted_in']} opted in): {DEMO['drafted']} drafts, {DEMO['sent']} sent ({DEMO['auto_sent']} auto-sent, {DEMO['sent'] - DEMO['auto_sent']} owner-approved), {DEMO['blocked']} blocked, {DEMO['opt_outs']} opt-outs honoured. Owner decisions, replies and orders are simulated; the opt-in rate is illustrative.",
    f"{N_TESTS} automated tests cover the Baby Trails adapter, segmentation, opt-in and STOP, the guardrail, routing and the approval API."], size=15, gap=0.3)
card(s, Inches(0.5), Inches(5.95), Inches(12.3), Inches(1.25), REDBG)
text(s, Inches(0.7), Inches(6.0), Inches(11.9), Inches(1.2),
     [[("Honest scope. ", True), ("This tests the guardrail with our own corruption set on synthetic data, not Gemini's real output or real customers. "
       "Pilot metrics (auto-send rate, approval latency, time saved, recovered revenue) are planned for the pilot with Baby Trails and will replace the simulated figures.", False)]], size=14)

# 12 ── Future
s = base("Additional details / future development")
bullets(s, Inches(0.6), Inches(1.6), Inches(12.1), Inches(5.4), [
    [("Second-layer semantic verifier: ", True), ("a Gemini entailment check on top of the deterministic one, for paraphrased claims no rule can see", False)],
    [("Native integrations: ", True), ("Shopify, WooCommerce and Unicommerce for one-click onboarding", False)],
    [("Context-aware retrieval: ", True), ("Vertex AI Search over catalog and order history for richer personalization", False)],
    [("Inventory-aware campaigns: ", True), ("promote what is in stock, pause what is not", False)],
    [("More channels: ", True), ("SMS and Instagram DMs alongside WhatsApp and email", False)],
    [("Predictive intelligence: ", True), ("churn and lifetime-value scoring with BigQuery ML beyond RFM", False)],
    [("Trust-earning autonomy at scale: ", True), ("merchant edits teach the model; the cockpit becomes an exception-handling tool, not a daily chore", False)]], size=18, gap=0.6)

# 13 ── Links
s = base("Provide links to your")
for i, (k, v) in enumerate([("GitHub Public Repository", "https://github.com/JayMandava/rekindle"),
                            ("Demo Video Link (under 90 seconds)", "https://github.com/JayMandava/rekindle/blob/main/docs/demo/rekindle_demo.mp4"),
                            ("Final Product Link", "https://jmandava-rekindle.hf.space")]):
    text(s, Inches(0.7), Inches(1.8 + i * 0.9), Inches(12), Inches(0.7), [[(f"{k}: ", True), (v, False)]], size=22)
s.shapes.add_movie(str(ROOT / "docs/demo/rekindle_demo.mp4"), Inches(0.7), Inches(4.45), Inches(4.8), Inches(2.7),
                   poster_frame_image=str(ROOT / "docs/deck/assets/demo_poster.png"), mime_type="video/mp4")

# 14 ── Team
s = base("Team")
for i, n in enumerate(["Abhishek", "Rishub", "Jeyanth", "Pratheek"]):
    cx = Inches(1.4 + i * 2.9)
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, cx, Inches(2.2), Inches(2.0), Inches(2.0))
    c.fill.solid(); c.fill.fore_color.rgb = BLUEBG; c.line.fill.background()
    text(s, cx, Inches(2.2), Inches(2.0), Inches(2.0), n[0], size=54, bold=True, color=BLUE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, cx - Inches(0.3), Inches(4.4), Inches(2.6), Inches(0.5), n, size=22, bold=True, align=PP_ALIGN.CENTER)
text(s, Inches(0.5), Inches(6.2), Inches(12.3), Inches(0.5), "Replace circles with team photos before submission.", size=14, color=MUTED, align=PP_ALIGN.CENTER)

# 15 ── Thank you
s = prs.slides.add_slide(BLANK)
s.shapes.add_picture(str(A / "thanks.png"), 0, 0, width=W, height=H)

out = ROOT / "docs/deck/ReKindle_AI_Builder_Cup.pptx"
prs.save(out)
print("saved", out)
