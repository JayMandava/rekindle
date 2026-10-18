"""Draft generation. Gemini (Vertex AI) with a response_schema in gcp mode; deterministic offline stub otherwise."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Optional, Protocol

from .config import Merchant, Settings
from .consent import classify_reply_offline
from .models import Channel, Claim, DraftOut, Target

SYSTEM = """You write re-engagement messages for a small merchant. You are NOT free to invent anything.
Rules:
- Use ONLY the facts provided. Never state a number, date, name, price or product that is not in a fact.
- Every personalised statement must appear in `claims`: copy the exact words (`span`) from your message
  and give the id of the fact that supports it.
- You may mention an offer only if it is in `approved_offers`; set `offer_id` and use its wording. Otherwise offer_id is null.
- No urgency, pressure, guarantees, links, or health claims. At most one emoji. Warm, short, human.
- Write in English (the approved template language).
- WhatsApp: `text` is ONE short paragraph (max 200 chars) that fills a template variable. Do NOT include a
  greeting, sign-off or opt-out line; the template adds them. Set subject to null.
- Email: `text` is 2-4 short sentences (max 700 chars) starting with a greeting by first name; include a subject.
  Do NOT add a sign-off or unsubscribe line; the system appends them."""


class Drafter(Protocol):
    name: str

    def draft(self, t: Target, channel: Channel, merchant: Merchant, feedback: Optional[list[str]] = None) -> DraftOut: ...
    def classify_reply(self, text: str) -> str: ...


class GeminiDrafter:
    def __init__(self, settings: Settings):
        from google import genai

        self.types = __import__("google.genai.types", fromlist=["types"])
        self.client = genai.Client(vertexai=True, project=settings.project, location=settings.gemini_location)
        self.thinking = settings.gemini_thinking
        self.model = settings.gemini_model
        self.name = f"gemini:{settings.gemini_model}"

    def draft(self, t, channel, merchant, feedback=None) -> DraftOut:
        payload = {
            "merchant": merchant.name, "voice": merchant.voice, "channel": channel.value,
            "language": t.language, "segment": t.segment,
            "facts": [f.model_dump() for f in t.facts],
            "approved_offers": [{"id": o["id"], "text": o["text"]} for o in merchant.offers],
        }
        if feedback:
            payload["previous_attempt_rejected_because"] = feedback
        resp = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=self.types.GenerateContentConfig(
                system_instruction=SYSTEM, response_mime_type="application/json", response_schema=DraftOut,
                thinking_config=self.types.ThinkingConfig(thinking_level=self.thinking),   # no temperature: not the control on Gemini 3.x
            ),
        )
        return resp.parsed if isinstance(resp.parsed, DraftOut) else DraftOut.model_validate_json(resp.text)

    def classify_reply(self, text: str) -> str:
        from pydantic import BaseModel

        class Intent(BaseModel):
            intent: str  # interested | question | not_interested | stop | other

        resp = self.client.models.generate_content(
            model=self.model,
            contents=f"Classify this customer reply (any language) as one of: interested, question, not_interested, stop, other.\nReply: {text}",
            config=self.types.GenerateContentConfig(response_mime_type="application/json", response_schema=Intent,
                                                    thinking_config=self.types.ThinkingConfig(thinking_level="LOW")),
        )
        return resp.parsed.intent if resp.parsed else classify_reply_offline(text)


class OfflineDrafter:
    """Deterministic stand-in so the whole loop runs without cloud credentials. Not an LLM.

    `chaos` makes a seeded fraction of drafts deliberately wrong (invented discount, wrong age,
    invented name) so the verification guardrail is visible in demos.
    """

    name = "offline-stub"
    languages = {"en"}   # the stub only writes English; Gemini handles the rest

    def __init__(self, chaos: float = 0.0):
        self.chaos = chaos

    def _bad(self, t: Target) -> bool:
        h = int(hashlib.sha256(t.customer_id.encode()).hexdigest(), 16) % 1000
        return h < self.chaos * 1000

    @staticmethod
    def _clean_on_retry(t: Target) -> bool:
        # most bad drafts are fixed by regenerating with the verifier's feedback; a few persist
        return int(hashlib.sha256((t.customer_id + "r").encode()).hexdigest(), 16) % 3 != 0

    def draft(self, t, channel, merchant, feedback=None) -> DraftOut:
        f = {x.id: x.value for x in t.facts}
        child = f.get("F4", "your little one")
        email = channel == Channel.email
        greet = f"Hi {t.first_name}, " if email else ""
        cap = lambda x: x[0].upper() + x[1:]
        claims: list[Claim] = []
        offer_id = None

        if t.segment == "milestone_due" and "F5" in f:
            m = f["F5"]
            if "F6" in f:
                span = f["F6"].replace("Baby milestone sessions are for ", "")
                text = f"{greet}{cap(m)}, right in the window for a baby milestone session ({span}). We'd love to see you again."
                claims = [Claim(span=m, fact_id="F5"), Claim(span=span, fact_id="F6")]
            else:
                text = f"{greet}{cap(m)}, and we'd love to celebrate with you."
                claims = [Claim(span=m, fact_id="F5")]
        elif t.segment == "champion_dormant":
            text = (f"{greet}it's been a while since your {f['F2']}, and you've booked {f['F3']} sessions with us. "
                    f"We'd love to see {child} again, with {merchant.offers[0]['text']}.")
            claims = [Claim(span=f["F2"], fact_id="F2"), Claim(span=f["F3"], fact_id="F3")]
            offer_id = merchant.offers[0]["id"]
        else:
            text = f"{greet}we still remember your {f['F2']}, and would love to see how {child} has grown."
            claims = [Claim(span=f["F2"], fact_id="F2")]
        if "F4" in f:
            claims.append(Claim(span=f["F4"], fact_id="F4")) if f["F4"] in text else None
        subject = f"A note from {merchant.name}" if email else None

        if self._bad(t) and not (feedback and self._clean_on_retry(t)):
            kind = int(hashlib.sha256((t.customer_id + "k").encode()).hexdigest(), 16) % 3
            if kind == 1 and "F5" in f and f["F5"] in text:
                text = text.replace(f["F5"], re.sub(r"\b(\d+)\b", lambda m: str(int(m.group(1)) + 5), f["F5"], count=1))
            elif kind == 2:
                text += " Rohan from our team will call you."
            else:
                text += " Book this week and get 20% off!"
                offer_id = None
        if not email:
            text = text[0].upper() + text[1:]
        return DraftOut(subject=subject, text=text, claims=claims, offer_id=offer_id)

    def classify_reply(self, text: str) -> str:
        return classify_reply_offline(text)


def make_drafter(settings: Settings) -> Drafter:
    return GeminiDrafter(settings) if settings.is_gcp else OfflineDrafter(settings.chaos)


# --- deterministic rendering (template + compliance lines are never LLM-written) -----------------

WA_TEMPLATE = "Hi {{1}}, this is {{2}} with a note about your little one. {{3}} You can reply STOP anytime to opt out."
OPT_OUT = {"en": "You can reply STOP anytime to opt out."}   # other languages need an approved template + native review


def render(channel: Channel, t: Target, d: DraftOut, merchant: Merchant) -> str:
    opt = OPT_OUT.get(t.language, OPT_OUT["en"])
    if channel == Channel.whatsapp:
        return WA_TEMPLATE.replace("{{1}}", t.first_name).replace("{{2}}", merchant.name).replace("{{3}}", d.text.strip())
    return f"{d.text.strip()}\n\n— {merchant.name}\n{opt}"


def choose_channel(t: Target) -> Optional[Channel]:
    if t.consent_whatsapp:
        return Channel.whatsapp
    if t.consent_email:
        return Channel.email
    return None
