import sys
import types

import pytest
from fastapi.testclient import TestClient

# Provide lightweight stubs for optional dependencies used during import
if "asyncpg" not in sys.modules:
    sys.modules["asyncpg"] = types.SimpleNamespace()

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_stub.extras = types.SimpleNamespace(RealDictCursor=object, Json=object)
    def _connect_stub(*args, **kwargs):  # pragma: no cover - defensive stub
        raise RuntimeError("psycopg2 stubbed for tests")
    psycopg2_stub.connect = _connect_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_stub.extras

if "numpy" not in sys.modules:
    import math

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.ndarray = list
    numpy_stub.array = lambda seq, dtype=None: list(seq)
    numpy_stub.diff = lambda seq: [seq[i + 1] - seq[i] for i in range(len(seq) - 1)] if len(seq) > 1 else []
    numpy_stub.std = lambda seq: float(math.sqrt(sum((x - (sum(seq) / len(seq))) ** 2 for x in seq) / len(seq))) if seq else 0.0
    numpy_stub.sqrt = math.sqrt
    numpy_stub.sum = lambda seq: float(sum(seq))
    numpy_stub.mean = lambda seq: float(sum(seq) / len(seq)) if seq else 0.0
    sys.modules["numpy"] = numpy_stub

if "scipy" not in sys.modules:
    scipy_stub = types.ModuleType("scipy")
    scipy_stats_stub = types.SimpleNamespace(zscore=lambda seq: 0.0, norm=types.SimpleNamespace())
    scipy_stub.stats = scipy_stats_stub
    sys.modules["scipy"] = scipy_stub
    sys.modules["scipy.stats"] = scipy_stats_stub

if "pandas" not in sys.modules:
    from datetime import datetime

    pandas_stub = types.ModuleType("pandas")
    pandas_stub.DataFrame = object
    pandas_stub.Series = list
    pandas_stub.Timestamp = datetime
    pandas_stub.to_datetime = lambda x: x
    sys.modules["pandas"] = pandas_stub

from src.api.main import app


@pytest.fixture()
def client(monkeypatch):
    """FastAPI test client with external services stubbed out."""

    async def _always_false(*args, **kwargs):
        return False

    async def _fail(*args, **kwargs):
        raise RuntimeError("binance offline (test)")

    async def _noop(*args, **kwargs):
        return None

    # Prevent real network/database calls during app startup
    monkeypatch.setattr("src.core.binance_client.BinanceClient.test_connectivity", _always_false)
    monkeypatch.setattr("src.core.binance_client.BinanceClient.get_ticker_24h", _fail)
    monkeypatch.setattr("src.core.binance_client.BinanceClient.get_klines", _fail)
    monkeypatch.setattr("src.core.binance_client.BinanceClient.get_orderbook", _fail)
    monkeypatch.setattr("src.core.deepseek_client.DeepSeekClient.test_connection", _always_false)
    monkeypatch.setattr("src.core.state_manager.StateManager.restore_state", _noop)
    monkeypatch.setattr("src.core.state_manager.StateManager.save_state", _noop)

    with TestClient(app) as test_client:
        yield test_client


def test_analyze_produces_ai_thought(client):
    """Ensure /analyze returns a decision and records an AI thought even when Binance is down."""
    response = client.post("/analyze", json={"symbol": "BTCUSDT"})
    assert response.status_code == 200

    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["action"] in {"BUY", "SELL", "HOLD"}
    assert payload.get("reasoning") is not None

    thoughts = client.get("/api/v1/ai/thoughts?limit=5").json()
    assert len(thoughts) >= 1
    assert any(t.get("symbol") == "BTCUSDT" for t in thoughts)
