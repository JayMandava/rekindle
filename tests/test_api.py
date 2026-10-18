from fastapi.testclient import TestClient

from rekindle.api import create_app


def test_full_flow_over_http(engine):
    c = TestClient(create_app(engine))
    assert c.get("/healthz").json()["ok"]
    assert c.post("/api/campaign/run", json={"limit": 6}).json()["drafted"] == 6
    drafts = c.get("/api/drafts", params={"status": "pending"}).json()
    assert len(drafts) == 6 and drafts[0]["verification"]["passed"] is not None
    did = drafts[0]["id"]
    assert c.post(f"/api/drafts/{did}/approve").json()["status"] == "sent"
    assert c.post(f"/api/drafts/{did}/approve").status_code == 422                  # no double send
    bad = c.post(f"/api/drafts/{drafts[1]['id']}/approve", json={"text": "Free everything, 90% off!"})
    assert bad.status_code == 422
    assert c.post(f"/api/drafts/{drafts[2]['id']}/reject", json={"reason": "tone"}).json()["status"] == "rejected"
    assert c.get("/api/state").json()["kpis"]["sent"] == 1
    assert c.get("/").status_code == 200


def test_whatsapp_webhook_stop(engine):
    c = TestClient(create_app(engine))
    c.post("/api/campaign/run", json={"limit": 3})
    d = engine.store.list_drafts()[0]
    phone = next(r["phone"] for r in engine.rows() if r["customer_id"] == d.customer_id)
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": phone.lstrip("+"), "type": "text", "text": {"body": "STOP"}}]}}]}]}
    out = c.post("/webhooks/whatsapp", json=payload).json()
    assert out["handled"][0]["intent"] == "stop"
    assert d.customer_id in engine.store.suppressed()


def test_demo_seed_runs_and_reports(engine):
    c = TestClient(create_app(engine))
    log = c.post("/api/demo/seed").json()
    k = c.get("/api/state").json()["kpis"]
    assert log["campaign_2"]["auto_sent"] > 0 and k["auto_sent"] > 0 and k["trust"]["auto_enabled"]
    assert k["opt_outs"] >= 1 and k["synthetic"] is True
