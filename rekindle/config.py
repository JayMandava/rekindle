from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Settings:
    mode: str = field(default_factory=lambda: os.getenv("REKINDLE_MODE", "local"))
    send_mode: str = field(default_factory=lambda: os.getenv("REKINDLE_SEND_MODE", "dry_run"))
    project: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    location: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    # Gemini 3.x on Vertex AI is served from the global endpoint (and us/eu multi-regions), not every regional one.
    # Kept separate from the Cloud Run region so the two can differ.
    gemini_location: str = field(default_factory=lambda: os.getenv("GEMINI_LOCATION", "global"))
    # Gemini 3.x is steered with thinking_level (LOW | MEDIUM | HIGH), not temperature. LOW suits short drafts.
    gemini_thinking: str = field(default_factory=lambda: os.getenv("GEMINI_THINKING_LEVEL", "LOW"))
    bq_dataset: str = field(default_factory=lambda: os.getenv("BQ_DATASET", "rekindle"))
    # Demo only: probability that the offline drafter emits a deliberately bad draft
    # so the guardrail can be seen working. Always 0 in gcp mode.
    chaos: float = field(default_factory=lambda: float(os.getenv("REKINDLE_CHAOS", "0.2")))
    as_of: date = field(
        default_factory=lambda: date.fromisoformat(os.environ["REKINDLE_AS_OF"])
        if os.getenv("REKINDLE_AS_OF")
        else date.today()
    )

    @property
    def is_gcp(self) -> bool:
        return self.mode == "gcp"


@dataclass(frozen=True)
class Merchant:
    """Per-merchant configuration. One document per merchant in Firestore."""

    merchant_id: str = "babytrail"
    name: str = "Baby Trails"
    voice: str = (
        "Warm, personal and unhurried, like a studio that remembers your family. "
        "No pressure, no urgency, no exclamation-mark spam. At most one emoji."
    )
    dormant_days: int = 120
    lost_days: int = 540
    cooldown_days: int = 30
    # Offers the merchant has pre-approved. The model may only use these.
    offers: tuple[dict, ...] = (
        {"id": "O1", "text": "a complimentary mini print set with your next session", "discount": False},
        {"id": "O2", "text": "10% off milestone sessions booked this month", "discount": True},
    )
    # Journey rules taken from Baby Trails' catalog: newborn customers are the natural audience for a
    # Baby (3-12 months) session; a first birthday is the other natural moment. Ages are estimates.
    newborn_to_baby_days: tuple[int, int] = (90, 150)
    birthday_window_days: int = 45
    baby_session_fact: str = "Baby milestone sessions are for babies aged 3 to 12 months"
    whatsapp_template: str = "rk_reengage_v1"
    # WhatsApp templates are approved per language, so the pilot writes English only. Tamil is roadmap, pending
    # an approved Tamil template and native review of the wording.
    languages: tuple[str, ...] = ("en",)
