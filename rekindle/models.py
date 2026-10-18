from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Channel(str, Enum):
    whatsapp = "whatsapp"
    email = "email"


class Route(str, Enum):
    auto_send = "auto_send"
    needs_review = "needs_review"
    blocked = "blocked"


class Status(str, Enum):
    pending = "pending"
    sent = "sent"
    rejected = "rejected"
    failed = "failed"


class Fact(BaseModel):
    id: str
    label: str
    value: str


class Target(BaseModel):
    """One customer selected for re-engagement, with the facts the draft may use."""

    customer_id: str
    name: str
    first_name: str
    language: str = "en"
    phone: Optional[str] = None
    email: Optional[str] = None
    consent_whatsapp: bool = False
    consent_email: bool = False
    segment: str
    r_score: int
    f_score: int
    m_score: int
    recency_days: int
    frequency: int
    monetary: float
    last_order_date: date
    last_product: str
    priority: float = 0.0
    vip: bool = False
    milestone_label: Optional[str] = None
    facts: list[Fact] = Field(default_factory=list)


class Claim(BaseModel):
    span: str = Field(description="Exact words copied verbatim from the message text")
    fact_id: str = Field(description="ID of the fact that supports this span")


class DraftOut(BaseModel):
    """Structured output requested from Gemini (response_schema)."""

    subject: Optional[str] = Field(default=None, description="Email subject; null for WhatsApp")
    text: str
    claims: list[Claim]
    offer_id: Optional[str] = Field(default=None, description="ID of an approved offer used, if any")


class Verification(BaseModel):
    passed: bool
    hard_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    grounding: float = 0.0
    richness: float = 0.0
    style: float = 0.0
    confidence: float = 0.0


class Risk(BaseModel):
    tier: str  # low | medium | high
    reasons: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    segment: str
    channel: Channel
    language: str
    subject: Optional[str] = None
    text: str
    rendered: str = ""  # exactly what the customer receives (template + opt-out line)
    claims: list[Claim] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    offer_id: Optional[str] = None
    verification: Verification
    risk: Risk
    route: Route
    status: Status = Status.pending
    drafter: str = "offline-stub"
    created_at: datetime
    decided_at: Optional[datetime] = None
    decision: Optional[str] = None  # approved | edited | rejected | auto
    reject_reason: Optional[str] = None
    sent_at: Optional[datetime] = None
