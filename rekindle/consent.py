"""Consent + opt-out. STOP is handled deterministically, before any generation or LLM call."""
from __future__ import annotations

import re
import unicodedata

# Exact-match opt-out keywords across languages (after normalisation). Deliberately conservative
# match-on-whole-message, plus a few phrase patterns, so "don't stop the album order" is not an opt-out.
STOP_WORDS = {
    "stop", "unsubscribe", "cancel", "optout", "opt out", "quit", "end", "remove me", "no more",
    "रोको", "बंद", "बंद करो", "बंद करें", "रुकिए", "मत भेजो", "हटाओ", "सदस्यता रद्द",
    "நிறுத்து", "நிறுத்தவும்", "ఆపండి", "ఆపు", "നിർത്തുക", "ನಿಲ್ಲಿಸಿ",
    "停止", "退订", "やめて", "停止して", "配信停止", "중지", "수신거부",
    "berhenti", "hentikan", "arrêtez", "arreter", "para", "detener", "stopp", "หยุด",
}
STOP_PHRASES = re.compile(
    r"(do not|don't|dont|stop)\s+(message|text|contact|send|whatsapp)\b|"
    r"\bunsubscribe\b|मुझे मैसेज (मत|न) |हमें संदेश न भेजें|संदेश भेजना बंद",
    re.IGNORECASE,
)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).strip().lower()
    return re.sub(r"[\s\.\!\?,;:]+$", "", re.sub(r"\s+", " ", t))


def is_stop(text: str) -> bool:
    t = _norm(text)
    return t in STOP_WORDS or bool(STOP_PHRASES.search(t))


def classify_reply_offline(text: str) -> str:
    """Keyword fallback used in local mode (Gemini classifies in gcp mode). Returns an intent label."""
    if is_stop(text):
        return "stop"
    t = _norm(text)
    if re.search(r"\b(book|slot|available|schedule|yes|interested|sure|please)\b|हाँ|हां|बुक", t):
        return "interested"
    if re.search(r"\b(price|cost|how much|package|when|where|what)\b|\?|कितना|कीमत", t):
        return "question"
    if re.search(r"\b(no thanks|not interested|not now|later)\b|नहीं", t):
        return "not_interested"
    return "other"
