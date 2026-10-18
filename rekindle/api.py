from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .engine import Engine
from .models import Status

UI = Path(__file__).parent / "ui"


class RunReq(BaseModel):
    limit: int = 40
    segments: Optional[list[str]] = None


class DecideReq(BaseModel):
    text: Optional[str] = None
    reason: Optional[str] = None


class InboundReq(BaseModel):
    text: str
    phone: Optional[str] = None
    email: Optional[str] = None
    customer_id: Optional[str] = None


class OrderReq(BaseModel):
    customer_id: str
    amount: float
    product: str = "Session"


def create_app(engine: Optional[Engine] = None) -> FastAPI:
    app = FastAPI(title="ReKindle", version="0.1.0")
    eng = engine or Engine.build()
    app.state.engine = eng

    @app.get("/healthz")
    def health():
        return {"ok": True, "mode": eng.settings.mode, "send_mode": eng.settings.send_mode, "drafter": eng.drafter.name}

    @app.get("/api/state")
    def state():
        return {"mode": eng.settings.mode, "send_mode": eng.settings.send_mode, "drafter": eng.drafter.name,
                "merchant": eng.merchant.name, "as_of": eng.settings.as_of.isoformat(),
                "segments": eng.segments(), "kpis": eng.kpis()}

    @app.post("/api/campaign/run")
    def run(req: RunReq):
        return eng.run_campaign(limit=min(max(req.limit, 1), 500), segments=req.segments)

    @app.get("/api/drafts")
    def drafts(status: Optional[str] = Query(None), route: Optional[str] = None):
        ds = eng.store.list_drafts()
        if status:
            ds = [d for d in ds if d.status.value == status]
        if route:
            ds = [d for d in ds if d.route.value == route]
        return [d.model_dump(mode="json") for d in reversed(ds)]

    def _decide(draft_id: str, action: str, body: DecideReq):
        try:
            return eng.decide(draft_id, action, text=body.text, reason=body.reason).model_dump(mode="json")
        except KeyError:
            raise HTTPException(404, "draft not found")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/drafts/{draft_id}/approve")
    def approve(draft_id: str, body: DecideReq = DecideReq()):
        return _decide(draft_id, "edit" if body.text else "approve", body)

    @app.post("/api/drafts/{draft_id}/reject")
    def reject(draft_id: str, body: DecideReq = DecideReq()):
        return _decide(draft_id, "reject", body)

    @app.post("/api/inbound")
    def inbound(req: InboundReq):
        return eng.inbound(req.text, req.phone, req.email, req.customer_id)

    @app.post("/api/orders")
    def order(req: OrderReq):
        eng.record_order(req.customer_id, req.amount, req.product)
        return {"ok": True}

    # WhatsApp Cloud API webhook (verification handshake + inbound messages)
    @app.get("/webhooks/whatsapp")
    def wa_verify(request: Request):
        q = request.query_params
        if q.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN", "change-me") and q.get("hub.challenge"):
            return PlainTextResponse(q["hub.challenge"])
        raise HTTPException(403, "verify token mismatch")

    @app.post("/webhooks/whatsapp")
    async def wa_inbound(request: Request):
        body = await request.json()
        handled = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                for m in change.get("value", {}).get("messages", []):
                    if m.get("type") == "text":
                        handled.append(eng.inbound(m["text"]["body"], phone=m.get("from")))
        return {"handled": handled}

    # Local-mode demo helpers (never exposed in gcp mode)
    @app.post("/api/demo/seed")
    def demo_seed():
        if eng.settings.is_gcp:
            raise HTTPException(404)
        from .demo import seed_demo
        return seed_demo(eng)

    @app.post("/api/demo/reset")
    def demo_reset():
        if eng.settings.is_gcp:
            raise HTTPException(404)
        eng.store.reset()
        eng.sender.outbox.clear() if hasattr(eng.sender, "outbox") else None
        return {"ok": True}

    @app.get("/")
    def index():
        return FileResponse(UI / "index.html")

    return app


def app_factory() -> FastAPI:  # uvicorn --factory rekindle.api:app_factory
    return create_app()
