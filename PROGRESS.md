# Currency Caching Proxy — Build Progress

---

## Stage 0 — Setup
**Status: Done**

- Chose `open.er-api.com` as the upstream (no API key needed).
- Set up FastAPI + uvicorn + httpx.
- Created the layered folder structure: routes → controllers → services → clients.
- Confirmed a `/health` endpoint returns `{"status": "ok"}`.

---

## Stage 1 — Naive proxy (no cache)
**Status: Done**

- `GET /rates?base=USD&target=EUR` flows through all layers and returns a live rate.
- Every request hit the upstream — no caching yet.

---

## Stage 2 — In-memory cache
**Status: Done**

### What was built
- `cache_client.py`: in-memory dict with `get(key)`, `set_value(key, value)`, and `get_age(key)`.
- TTL is read from the `TTL` env var (default 60 seconds).
- Cache key format: `"BASE:TARGET"` (e.g. `"USD:EUR"`).
- Cache-aside logic in `rates_service.py`: check cache → on miss fetch upstream and store → on hit return directly.
- HIT/MISS logging with elapsed time and cache age printed to the terminal.

### Observed output
```
MISS USD:EUR
MISS USD:EUR  (278.78 ms)      ← upstream round-trip
Cache age: 0.0 seconds
GET /rates?base=USD&target=EUR  200 OK

HIT  USD:EUR
HIT  USD:EUR  (0.20 ms)        ← served from dict, ~1400x faster
Cache age: 7.88 seconds
GET /rates?base=USD&target=EUR  200 OK
```

### What this proves
- First request: 278 ms — the full upstream call.
- Second request: 0.20 ms — pure memory lookup, no network.
- Cache age confirms the TTL clock is running correctly.
- The cache is working exactly as designed.

### Known limitation at this stage
In-memory cache resets on every server restart and is not shared across multiple processes. That gets fixed in Stage 5 when Redis replaces the dict.

---

## Stage 3 — Resilience
**Status: Not started**

---

## Stage 4 — Observability
**Status: Not started**

---

## Stage 5 — Redis
**Status: Not started**

---

## Stage 6 — Dockerize + deploy
**Status: Not started**

---

## Stage 7 — Tests + CI
**Status: Not started**
