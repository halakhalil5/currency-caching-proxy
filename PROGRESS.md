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
**Status: Done**

### What was built
- Retry loop: up to 5 attempts with logged failures on each.
- Stale-on-failure: if the upstream is unreachable and a cached value exists, it is returned immediately with `stale: true` in the response.
- 503 returned only when the upstream is down **and** there is nothing in cache to fall back on.
- 404 returned for well-formed but unknown currency codes (e.g. `USD:XYZ`).

### Observed output
```
MISS USD:EUR
attempt 1 failed: [Errno 11001] getaddrinfo failed
attempt 2 failed: [Errno 11001] getaddrinfo failed
attempt 3 failed: [Errno 11001] getaddrinfo failed
attempt 4 failed: [Errno 11001] getaddrinfo failed
attempt 5 failed: [Errno 11001] getaddrinfo failed
STALE USD:EUR  (15175.54 ms)          ← served from cache, flagged stale
GET /rates?base=USD&target=EUR  200 OK

# No cache to fall back on:
GET /rates?base=USD&target=EGP  503 Service Unavailable

# Unknown currency code:
MISS USD:XYZ
GET /rates?base=USD&target=XYZ  404 Not Found
```

### What this proves
- When the upstream is broken, a cached value is still served — the user gets an answer, not an error.
- `stale: true` in the response is honest: the caller knows the data is old.
- Without any cache, the service correctly escalates to 503 rather than hanging forever.
- The retry loop exhausts all attempts before giving up, not after the first failure.

---

## Stage 4 — Observability
**Status: Done**

### What was built
- `metrics.py`: module-level counters for hits, misses, errors, total latency, and per-key last-refresh timestamps.
- `record_hit(latency_ms)`, `record_miss(key, latency_ms)`, `record_error()` called from the service.
- `snapshot()` computes hit rate and average latency on read.
- `GET /stats` route → stats controller → `snapshot()` — returns the live metrics dict.
- `GET /health` already in place from Stage 0.

### Observed output
```
GET /stats  200 OK
GET /rates?base=USD&target=EGP  200 OK   ← MISS / FRESH
GET /rates?base=USD&target=EUR  200 OK   ← MISS / FRESH
GET /rates?base=USD&target=EUR  200 OK   ← HIT
GET /stats  200 OK                        ← hit_rate now climbing
GET /health  200 OK
```

### Sample /stats response
```json
{
  "hits": 1,
  "misses": 2,
  "errors": 0,
  "hit_rate": 0.333,
  "avg_latency_ms": 205.38,
  "last_refresh": {
    "USD:EGP": 1781640396.9707983,
    "USD:EUR": 1781640401.8601954
  }
}
```

### What this proves
- `/stats` responds with live hit/miss counts and hit rate.
- Hit rate climbs with repeat requests, confirming the cache is actually reducing upstream load.
- `last_refresh` records the exact Unix timestamp of the last successful upstream fetch per pair.
- `avg_latency_ms` of 205 ms is pulled down by the 1 cache hit (< 1 ms) averaged against 2 upstream calls (~400 ms each).

---

## Stage 5 — Redis
**Status: Done**

### What was built
- `cache_client.py` now talks to Redis instead of the Python dict.
- Same four functions (`get`, `set_value`, `get_age`, `get_stale`) kept their exact signatures, so `rates_service.py` didn't need to change at all.
- Value stored as a JSON string: `{"value": ..., "stored_at": <unix time>}`, written with `r.set(key, json.dumps(...))`.
- TTL is still enforced in application code (compare `time.time() - stored_at` against `TTL`), not via Redis's own `EX` expiry — keeps the staleness logic identical to Stage 2/3.
- `REDIS_HOST` / `REDIS_PORT` added to `config.py` (default `localhost:6379`), connection created once at module load. *(In Stage 6 this was unified to a single `REDIS_URL` for cloud deployment.)*
- The old in-memory dict implementation is **kept, commented out, directly above the Redis code** — not deleted. It's the reference implementation for what Stage 2 looked like, and makes it trivial to diff "what changed to add Redis" or to roll back during the assignment.

### Why Redis (and why it's still RAM, not disk)
Redis is an **in-memory data store** — same fundamental idea as the Stage 2 dict (data lives in RAM, lookups are sub-millisecond), the difference is *where that RAM lives*:
- The Stage 2 dict lived inside the FastAPI process's own memory. Restart the process (or run two instances) and the cache is gone or inconsistent.
- Redis runs as a **separate server process**. The Python app talks to it over a socket, but Redis itself still holds the data in its own RAM, not on disk. That's why reads/writes stay fast (sub-millisecond, just like the dict) instead of paying disk I/O cost.
- Because Redis is a standalone process, the cache now survives an app restart, and multiple instances of the API (e.g. behind a load balancer, or in separate Docker containers in Stage 6) can all share the exact same cache.
- Redis *can* persist to disk (RDB / AOF) for crash recovery, but that's a backup mechanism — normal operation still reads/writes from RAM. We're not relying on persistence here.

### What this proves
- Same cache-aside contract as Stage 2 (`get`/`set_value`/`get_age`/`get_stale`), now backed by a process that's independent of the API server.
- Sets up Stage 6 cleanly: once Redis runs as its own container/service, multiple API containers can share one cache.

---

## Stage 6 — Dockerize + deploy
**Status: Done**

### What was built
- A `Dockerfile` for the app (Python base, installs `requirements.txt`, runs `uvicorn`), plus a `docker-compose.yml` that brings up the **app and a Redis container together**, so the whole stack runs locally with one command.
- All configuration moved into **environment variables** (no hardcoded hosts or URLs), read in `config.py` with sensible defaults.
- The Redis connection was **unified to a single `REDIS_URL`** parsed by `redis.from_url(REDIS_URL, decode_responses=True)`, replacing the separate `REDIS_HOST` / `REDIS_PORT`. That one string carries host, port, password, and TLS (`rediss://`), so the *same code* runs locally (`redis://localhost:6379`), under Compose (`redis://redis:6379`), and against cloud Redis — only the variable's value changes.
- Dockerfile `CMD` set to listen on **port 7860** (the port Hugging Face Spaces expects).

### Deployment
- Deployed to **Hugging Face Spaces** (Docker SDK) — chosen because it requires **no credit card**. Render, Koyeb, Railway, and Fly.io were all ruled out: each needs an international card (processed via Stripe), and a domestic Egyptian Meeza card is rejected.
- Redis hosted on **Upstash** (serverless, free tier, no card). The `rediss://` connection string is set as a Space **secret**, alongside `UPSTREAM_URL`, `TTL`, `MAX_RETRIES`, `BACKOFF`.
- App files placed at the **repo root** of the Space (not nested under `src/`) so `uvicorn main:app` resolves; deployed by pushing to the Space's own git repo using a write token.

### Observed output
The app is live and responding:
- `https://halahk-currency-caching-proxy.hf.space/docs`
- `https://halahk-currency-caching-proxy.hf.space/rates?base=USD&target=EGP`
- `https://halahk-currency-caching-proxy.hf.space/stats`

### What this proves
- The exact same image runs locally and in the cloud, with behavior controlled entirely by environment variables.
- A separate Redis service is shared by the app rather than bundled into it — the multi-process cache design from Stage 5 realized in deployment.
- The service is reachable at a public URL with live, interactive API docs.

---

## Stage 7 — Tests + CI
**Status: Done**

### What was built
- A **pytest** suite (5 tests) run through FastAPI's `TestClient` (calls endpoints in-process, no live server needed):
  - `test_health` — `/health` returns `{"status": "ok"}` (no mocking needed).
  - `test_cache_hit` — cache pre-populated (mocked) → returns the cached rate without calling the upstream.
  - `test_cache_miss` — cache empty + mocked upstream success → fetches, stores, returns.
  - `test_unknown_currency` — mocked upstream response lacking the target → `404`.
  - `test_stale_fallback` — mocked upstream failure + a stale cached value → `200` with a `warning` flag (the headline Stage 3 feature).
- **Mocking approach:**
  - Cache functions mocked with pytest's `monkeypatch`, patched **where they're used** (`services.rates_service.get`, etc.), since the service imported them by name.
  - Upstream httpx calls mocked with **respx** — a fake `Response(...)` for the success and missing-target cases, and an `httpx.ConnectError` side-effect for the failure case.
  - `asyncio.sleep` patched to a no-op in the stale test so the retry backoff doesn't make the test wait ~15 s.
- **CI:** a GitHub Actions workflow at `.github/workflows/ci.yml` that, on every push and pull request, spins up a fresh Ubuntu runner, installs Python 3.13 and the dependencies (plus `pytest` and `respx`), and runs the suite from `backend/src`. Required env vars are set in the workflow so `config.py` imports cleanly.
- A CI status **badge** added to the README.

### Observed output
```
tests/test_health.py::test_health PASSED                     [ 20%]
tests/test_rates.py::test_cache_hit PASSED                   [ 40%]
tests/test_rates.py::test_cache_miss PASSED                  [ 60%]
tests/test_rates.py::test_unknown_currency PASSED            [ 80%]
tests/test_rates.py::test_stale_fallback PASSED              [100%]
===================== 5 passed =====================
```

### What this proves
- The core behaviors — caching, miss-and-fetch, unknown-currency handling, and the stale-while-error fallback — are verified automatically, without depending on a live Redis or a live upstream.
- Every push re-runs the suite in a clean environment, so a regression is caught immediately rather than discovered later.