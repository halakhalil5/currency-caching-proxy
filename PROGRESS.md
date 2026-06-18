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
- `REDIS_HOST` / `REDIS_PORT` added to `config.py` (default `localhost:6379`), connection created once at module load: `r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)`.
- The old in-memory dict implementation is **kept, commented out, directly above the Redis code** — not deleted. It's the reference implementation for what Stage 2 looked like, and makes it trivial to diff "what changed to add Redis" or to roll back during the assignment.

### Why Redis (and why it's still RAM, not disk)
Redis is an **in-memory data store** — same fundamental idea as the Stage 2 dict (data lives in RAM, lookups are sub-millisecond), the difference is *where that RAM lives*:
- The Stage 2 dict lived inside the FastAPI process's own memory. Restart the process (or run two instances) and the cache is gone or inconsistent.
- Redis runs as a **separate server process**. The Python app talks to it over a socket (TCP to `localhost:6379`), but Redis itself still holds the data in its own RAM, not on disk. That's why reads/writes stay fast (sub-millisecond, just like the dict) instead of paying disk I/O cost.
- Because Redis is a standalone process, the cache now survives an app restart, and multiple instances of the API (e.g. behind a load balancer, or in separate Docker containers in Stage 6) can all share the exact same cache instead of each having its own cold, inconsistent dict.
- Redis *can* persist to disk (RDB snapshots / AOF log) for crash recovery, but that's a backup mechanism — normal operation still reads/writes from RAM. We're not relying on persistence here; if Redis restarts, the cache is allowed to be cold again (same tradeoff as Stage 2).

### Installation needed
Redis is a separate server, not just a pip package, so two things had to be installed:
1. **Python client**: `pip install redis` (the `redis` package was missing — `ModuleNotFoundError: No module named 'redis'` — and `requirements.txt` was empty). Added to `requirements.txt` along with the other runtime deps (`fastapi`, `uvicorn`, `httpx`) that were also unpinned.
2. **Redis server itself** must be running and reachable at `REDIS_HOST:REDIS_PORT` (defaults to `localhost:6379`) before the app starts — the Python client only talks to an existing server, it doesn't bundle one. On Windows this typically means running Redis via Docker (`docker run -p 6379:6379 redis`) or WSL, since there's no native Windows Redis build.

### What this proves
- Same cache-aside contract as Stage 2 (`get`/`set_value`/`get_age`/`get_stale`), now backed by a process that's independent of the API server.
- Sets up Stage 6 cleanly: once Redis runs as its own container, multiple API containers can share one cache.

---

## Stage 6 — Dockerize + deploy
**Status: Not started**

---

## Stage 7 — Tests + CI
**Status: Not started**
