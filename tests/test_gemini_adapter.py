"""The live Gemini call can't run in CI (no credentials), so exercise the adapter with a fake client."""
import json
from types import SimpleNamespace

from rekindle.config import Merchant, Settings
from rekindle.drafting import GeminiDrafter, OfflineDrafter
from rekindle.models import Channel, DraftOut
from rekindle.segmentation import build_targets
from rekindle.engine import Engine
from datetime import date


class FakeModels:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def generate_content(self, model, contents, config):
        self.calls.append((model, json.loads(contents), config))
        return SimpleNamespace(parsed=None, text=self.reply)


def make(reply):
    g = GeminiDrafter.__new__(GeminiDrafter)
    g.types = __import__("google.genai.types", fromlist=["types"])
    g.model, g.name = "gemini-test", "gemini:gemini-test"
    g.client = SimpleNamespace(models=FakeModels(reply))
    return g


def test_payload_grounding_and_parse():
    e = Engine.build(Settings(mode="local", chaos=0.0, as_of=date(2026, 10, 18)))
    t = build_targets(e.rows(), e.settings.as_of, e.merchant)[0]
    reply = json.dumps({"subject": None, "text": "Aarav is growing fast.", "claims": [{"span": "Aarav", "fact_id": "F4"}], "offer_id": None})
    g = make(reply)
    out = g.draft(t, Channel.whatsapp, Merchant(), feedback=["too long"])
    assert isinstance(out, DraftOut) and out.claims[0].fact_id == "F4"
    model, payload, cfg = g.client.models.calls[0]
    assert model == "gemini-test" and payload["previous_attempt_rejected_because"] == ["too long"]
    assert {f["id"] for f in payload["facts"]} >= {"F1", "F2", "F3"}
    assert [o["id"] for o in payload["approved_offers"]] == ["O1", "O2"]
    assert cfg.response_mime_type == "application/json" and cfg.response_schema is DraftOut


def test_gemini_output_still_goes_through_the_guardrail():
    """Even a fluent, confident model reply is blocked if it invents something."""
    e = Engine.build(Settings(mode="local", chaos=0.0, as_of=date(2026, 10, 18)))
    reply = json.dumps({"subject": None, "text": "Book now and save 35%!", "claims": [], "offer_id": None})
    e.drafter = make(reply)
    out = e.run_campaign(limit=5)
    assert out["blocked"] == 5 and e.sender.outbox == []
