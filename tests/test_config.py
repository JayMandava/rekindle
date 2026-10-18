import json
import os

from rekindle.config import Settings, ensure_credentials


def test_presets(monkeypatch):
    for k in ("REKINDLE_DATA", "REKINDLE_STORE", "REKINDLE_LLM"):
        monkeypatch.delenv(k, raising=False)
    local, spark, gcp = Settings(mode="local"), Settings(mode="spark"), Settings(mode="gcp")
    assert (local.data, local.store, local.llm) == ("local", "memory", "offline") and not local.is_gcp
    assert (spark.data, spark.store, spark.llm) == ("local", "firestore", "apikey") and spark.is_gcp   # no BigQuery, no Vertex
    assert (gcp.data, gcp.store, gcp.llm) == ("bigquery", "firestore", "vertex")


def test_single_piece_override(monkeypatch):
    monkeypatch.setenv("REKINDLE_LLM", "apikey")
    s = Settings(mode="local")
    assert s.llm == "apikey" and s.store == "memory" and s.is_gcp      # real LLM in use: demo helpers off


def test_service_account_json_secret_becomes_private_file(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", json.dumps({"type": "service_account"}))
    ensure_credentials()
    path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    assert json.load(open(path)) == {"type": "service_account"} and oct(os.stat(path).st_mode)[-3:] == "600"
    os.remove(path)


def test_spark_mode_never_touches_bigquery():
    from rekindle.store import FirestoreStore
    import inspect
    assert "bq_dataset: Optional[str] = None" in inspect.getsource(FirestoreStore.__init__)
