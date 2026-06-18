from fastapi.testclient import TestClient
from main import app
import httpx
import respx,asyncio
from httpx import Response
from config import UPSTREAM_URL


client = TestClient(app)

def test_cache_hit(monkeypatch):
    monkeypatch.setattr("services.rates_service.get", lambda key: 49.5)
    monkeypatch.setattr("services.rates_service.get_age", lambda key: 5.0)
    r = client.get("/rates?base=USD&target=EGP")
    assert r.status_code == 200
    assert r.json()["rate"] == 49.5



@respx.mock
def test_cache_miss(monkeypatch):
    monkeypatch.setattr("services.rates_service.get", lambda key: None)
    monkeypatch.setattr("services.rates_service.set_value", lambda k, v: None)
    monkeypatch.setattr("services.rates_service.get_age", lambda key: 0)
    respx.get(f"{UPSTREAM_URL}/USD").mock(
        return_value=Response(200, json={"rates": {"EGP": 49.5}})
    )
    r = client.get("/rates?base=USD&target=EGP")
    assert r.status_code == 200
    assert r.json()["rate"] == 49.5  



@respx.mock
def test_unknown_currency(monkeypatch):
    monkeypatch.setattr("services.rates_service.get", lambda key: None)
    respx.get(f"{UPSTREAM_URL}/USD").mock(
        return_value=Response(200, json={"rates": {"EUR": 0.9}})
    )
    r = client.get("/rates?base=USD&target=XYZ")
    assert r.status_code == 404


@respx.mock
def test_stale_fallback(monkeypatch):
    monkeypatch.setattr("services.rates_service.get", lambda key: None)
    monkeypatch.setattr("services.rates_service.get_stale", lambda key: 49.0)

    async def _no_sleep(*a, **k):   # skip the backoff waits
        pass
    monkeypatch.setattr("asyncio.sleep", _no_sleep)

    respx.get(f"{UPSTREAM_URL}/USD").mock(side_effect=httpx.ConnectError("down"))

    r = client.get("/rates?base=USD&target=EGP")
    assert r.status_code == 200
    assert "warning" in r.json()        # the stale flag