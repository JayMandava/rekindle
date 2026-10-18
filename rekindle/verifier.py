"""Deterministic fact-verification guardrail. No LLM judges its own output here.

Hard failures block the draft. Warnings lower confidence. Confidence then drives routing.
"""
from __future__ import annotations

import re

from .config import Merchant
from .models import DraftOut, Fact, Verification

NUM = re.compile(r"\d[\d,\.]*%?")
WORD = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
COMMON_CAPS = {"Hi", "Hello", "Hey", "Dear", "Warm", "Regards", "Thanks", "Thank", "Team", "Best", "Namaste", "Whatsapp", "WhatsApp"}
BANNED = [
    (re.compile(r"\b(guarantee[sd]?|100%|risk[- ]free)\b", re.I), "makes a guarantee"),
    (re.compile(r"\b(last chance|hurry|act now|don't miss|expires? (today|soon|tonight)|only \d+ (slots|spots) left)\b", re.I), "uses pressure/urgency"),
    (re.compile(r"\b(cure|diagnos|doctor|medical|therapy)\w*\b", re.I), "health-related claim"),
    (re.compile(r"https?://|www\.", re.I), "contains a link (not in approved template)"),
]
RECALL = re.compile(
    r"\b(you (told|said|mentioned|loved|liked|enjoyed|asked|wanted|chose|picked|requested|shared|prefer)|"
    r"your (favou?rite|choice|preference)s?|we noticed|we know you|as you (said|requested|mentioned)|"
    r"last time you|you('ve| have) (always|told|mentioned))\b", re.I)
SENT_SPLIT = re.compile(r"(?<=[.!?\u0964])\s+")
DISCOUNT_WORDS = re.compile(r"\b(\d+\s?%|off|discount|free|complimentary|offer)\b", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
MAX_LEN = {"whatsapp": 220, "email": 900}


STARTERS = {
    "we", "our", "it", "its", "i", "here", "there", "your", "you", "if", "whenever", "book", "come", "let", "visit",
    "reply", "thank", "thanks", "looking", "just", "every", "each", "capture", "bring", "treat", "ready", "time",
    "this", "that", "the", "a", "an", "and", "but", "so", "now", "today", "soon", "whether", "since", "when", "with",
    "for", "as", "hope", "hoping", "would", "could", "please", "warm", "best", "say", "have", "happy", "it's", "we'd",
    "we'll", "we've", "imagine", "memories", "moments", "little", "growing", "celebrate", "congratulations", "family",
    "ahead", "thinking", "hello", "hi", "hey", "dear", "also", "maybe", "perhaps", "see", "meet", "get", "take", "bring", "they", "he", "she", "his", "her", "their", "how", "what", "why", "no", "yes", "one", "two",
}


def _tokens(text: str) -> set[str]:
    return {t.strip(".,").lower() for t in NUM.findall(text) if t.strip(".,")}


def _caps(text: str, include_sentence_start: bool = False) -> set[str]:
    """Capitalised words. By default skips sentence-initial ones (ordinary English), since without a
    dictionary we cannot tell 'Warm' from 'Rohan' there. Known limitation, see README."""
    out = set()
    for m in WORD.finditer(text):
        before = text[: m.start()].rstrip()
        if not include_sentence_start and (not before or before[-1] in ".!?\n"):
            continue
        out.add(m.group())
    return out


def allowed_vocab(facts: list[Fact], merchant: Merchant) -> tuple[set[str], set[str]]:
    blob = " ".join(f.value for f in facts) + " " + merchant.name + " " + " ".join(o["text"] for o in merchant.offers)
    return _tokens(blob), set(WORD.findall(blob))


def verify(draft: DraftOut, facts: list[Fact], channel: str, merchant: Merchant) -> Verification:
    by_id = {f.id: f for f in facts}
    hard: list[str] = []
    warn: list[str] = []
    text = draft.text.strip()
    _, allowed_caps = allowed_vocab(facts, merchant)

    # 1. Every claim must quote the message verbatim and be supported by the fact it cites.
    verified = 0
    covered: list[tuple[int, int, set[str]]] = []   # (start, end, numbers the cited fact supports)
    low = text.lower()
    if not draft.claims:
        hard.append("no claims cited: personalisation is not grounded")
    for c in draft.claims:
        fact = by_id.get(c.fact_id)
        if fact is None:
            hard.append(f"claim cites unknown fact '{c.fact_id}'")
            continue
        at = low.find(c.span.lower())
        if at < 0:
            hard.append(f"claim span not found verbatim in message: '{c.span[:40]}'")
            continue
        extra_nums = _tokens(c.span) - _tokens(fact.value)
        extra_caps = {w for w in _caps(c.span, True) if w not in COMMON_CAPS} - set(WORD.findall(fact.value))
        if extra_nums or extra_caps:
            hard.append(f"claim not supported by {fact.id}: unsupported {sorted(extra_nums | extra_caps)}")
            continue
        verified += 1
        while at >= 0:
            covered.append((at, at + len(c.span), _tokens(fact.value)))
            at = low.find(c.span.lower(), at + 1)

    # 2. Every number in the message must sit inside a verified claim whose fact contains it
    #    (or belong to the approved offer in use). A number that is true elsewhere is still wrong here.
    offer_nums = _tokens(next((o["text"] for o in merchant.offers if o["id"] == draft.offer_id), ""))
    stray_nums = set()
    for m in NUM.finditer(text):
        tok = m.group().strip(".,").lower()
        if not tok or tok in offer_nums:
            continue
        if not any(a <= m.start() and m.end() <= b + 1 and tok in nums for a, b, nums in covered):
            stray_nums.add(tok)
    if stray_nums:
        hard.append(f"numbers not supported by a cited fact: {sorted(stray_nums)}")
    stray_caps = {w for w in _caps(text) if w not in COMMON_CAPS and w not in allowed_caps}
    if stray_caps:
        hard.append(f"names not in source data: {sorted(stray_caps)}")

    starters = {m.group() for m in WORD.finditer(text) if (not text[: m.start()].rstrip() or text[: m.start()].rstrip()[-1] in ".!?\n")}
    for w in sorted(starters):
        if w not in allowed_caps and w not in COMMON_CAPS and w.lower() not in STARTERS:
            hard.append(f"unrecognised capitalised word at sentence start (possible invented name): {w}")

    # 2b. A sentence that recalls something about the customer must be backed by a cited claim, and no
    #     long sentence may be entirely uncited. This catches fabricated memories/preferences that have no
    #     numbers or names for the lexical checks to find.
    pos = 0
    for sent in SENT_SPLIT.split(text):
        start = text.find(sent, pos)
        pos = start + len(sent)
        if any(a < pos and start < b for a, b, _ in covered):
            continue
        if RECALL.search(sent):
            hard.append(f"unsupported recollection (no cited fact): '{sent[:50]}'")
        elif len(sent.split()) > 14:
            hard.append(f"long sentence with no cited fact: '{sent[:50]}'")

    # 3. Offers: only merchant-approved, and any discount language must map to the declared offer.
    offer = next((o for o in merchant.offers if o["id"] == draft.offer_id), None)
    if draft.offer_id and offer is None:
        hard.append(f"unknown offer '{draft.offer_id}'")
    if offer is None and DISCOUNT_WORDS.search(text):
        hard.append("offer/discount language without an approved offer")

    # 4. Policy checks.
    for pat, why in BANNED:
        if pat.search(text) or (draft.subject and pat.search(draft.subject)):
            hard.append(why)
    if len(text) > MAX_LEN[channel]:
        hard.append(f"too long for {channel} ({len(text)} > {MAX_LEN[channel]})")
    if channel == "email" and not (draft.subject and draft.subject.strip()):
        hard.append("email needs a subject")
    if len(EMOJI.findall(text)) > 1:
        warn.append("more than one emoji")
    if text.count("!") > 1:
        warn.append("multiple exclamation marks")
    if channel == "email" and "F1" in by_id and by_id["F1"].value not in text:
        warn.append("does not address the customer by name")

    grounding = (verified / len(draft.claims)) if draft.claims else 0.0
    cited = len({c.fact_id for c in draft.claims if c.fact_id in by_id})
    richness = min(1.0, cited / max(1, min(len(facts), 4)))
    style = max(0.0, 1.0 - 0.25 * len(warn))
    confidence = 0.5 * grounding + 0.3 * richness + 0.2 * style
    if hard:
        confidence = min(confidence, 0.2)
    return Verification(passed=not hard, hard_issues=hard, warnings=warn,
                        grounding=round(grounding, 3), richness=round(richness, 3),
                        style=round(style, 3), confidence=round(confidence, 3))
