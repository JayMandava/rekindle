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
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
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
    name: str = "Babytrail Photography"
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
    milestone_months: tuple[int, ...] = (6, 12, 18, 24)
    milestone_window_days: int = 30
    whatsapp_template: str = "reengage_v1"
