
---
title: Currency Caching Proxy
emoji: 💱
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
# 💱 Currency Caching Proxy

![CI](https://github.com/halakhalil5/currency-caching-proxy/actions/workflows/ci.yml/badge.svg)

A resilient, observable caching proxy for live currency exchange rates, built with **FastAPI** and **Redis**. It sits between clients and a public exchange-rate API, caching responses to cut latency and upstream load, retrying transient failures, and degrading gracefully — serving slightly stale data rather than an error — when the upstream is unreachable.

**Live demo:**
- Interactive docs — `https://halahk-currency-caching-proxy.hf.space/docs`
- Example rate — `https://halahk-currency-caching-proxy.hf.space/rates?base=USD&target=EGP`
- Live metrics — `https://halahk-currency-caching-proxy.hf.space/stats`

---

## Overview

Calling a third-party exchange-rate API on every request is slow and wasteful: the same rate is requested over and over, each call costs a network round-trip, and if the upstream goes down, every request fails. This service solves that by acting as a smart middleman:

- On a **cache hit**, it returns the rate instantly from Redis — no upstream call.
- On a **cache miss**, it fetches once from the upstream, stores the result, and returns it.
- When the upstream is **slow or down**, it retries with backoff, and if it still can't reach it, serves the last cached value flagged as stale instead of failing.
- It exposes **live metrics** (hit rate, latency, errors) so you can see the cache earning its keep.

---

## Features

- ⚡ **Cache-aside caching** backed by Redis — repeat lookups served in well under a millisecond.
- 🛡️ **Resilience** — timeouts, retries with exponential backoff, and a stale-while-error fallback.
- 📊 **Observability** — a `/stats` endpoint with live hit rate, average latency, error count, and per-pair last-refresh timestamps.
- 🧱 **Clean layered architecture** — routes → controllers → services → clients, with strict separation of concerns.
- 🔌 **Pluggable cache backend** — Redis lives behind a thin client, so swapping the storage engine touches one file.
- ✅ **Tested & CI** — a pytest suite (with mocked Redis and upstream) runs automatically on every push via GitHub Actions.
- 🐳 **Dockerized** and deployed to a public URL.

---

## Architecture

The codebase is organized in layers, and a request only ever flows downward through them:

```
            HTTP request
                 │
            routes/         declares URLs, points them at controllers
                 │
          controllers/      reads/validates input, shapes the HTTP response
                 │
           services/        the cache-aside brain (business logic, no HTTP)
                 │
      ┌──────────┴───────────┐
 cache_client            upstream_client
 (Redis: get/set)        (httpx call + retries)
      │                       │
   Redis                 Upstream API
```

- **Controllers** know about HTTP (query params, status codes) but nothing about Redis or httpx.
- **Services** hold the business logic (the cache-aside flow, the stale-fallback decision) and know nothing about HTTP.
- **Clients** hide the external systems: `cache_client` wraps Redis, `upstream_client` wraps the API call. Swapping Redis for another store changes only `cache_client`.
- **`metrics.py`** keeps running counters that `/stats` reads.

### The cache-aside flow

```
request → check cache (fresh?)
   ├── hit  → return rate
   └── miss → call upstream (with timeout + retries)
              ├── success → store in cache, return rate
              └── all retries fail →
                     ├── stale value exists → return it, flagged stale
                     └── nothing cached    → return 503
```

---

## Tech Stack

| Concern          | Choice |
|------------------|--------|
| Web framework    | FastAPI |
| HTTP client      | httpx (async) |
| Cache            | Redis |
| Containerization | Docker + Docker Compose |
| Hosting          | Hugging Face Spaces (Docker SDK) |
| Managed Redis    | Upstash (serverless, free tier) |
| Tests            | pytest + respx |
| CI               | GitHub Actions |

---

## Project Structure

```
.
├── main.py              # creates the app, registers routes
├── config.py            # loads settings from environment variables
├── routes/              # URL declarations
├── controllers/         # HTTP layer: validate request, shape response
├── services/            # cache-aside orchestration (business logic)
├── clients/
│   ├── cache_client.py  # Redis wrapper: get / set_value / get_age / get_stale
│   └── upstream_client.py
├── metrics.py           # hit/miss/error counters for /stats
├── tests/               # pytest suite (health, cache, resilience)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
└── .github/workflows/
    └── ci.yml           # CI pipeline: runs the tests on every push
```

---

## Getting Started

### Prerequisites — what to install

- **Python 3.12+**
- **Docker** (used to run Redis locally, and to run the whole stack)
- The Python dependencies (installed via `requirements.txt`): `fastapi`, `uvicorn`, `httpx`, `redis`

### Installation

```bash
git clone <your-repo-url>
cd currency-caching-proxy
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration

All settings are read from environment variables (with sensible defaults):

| Variable      | Description                                  | Example |
|---------------|----------------------------------------------|---------|
| `REDIS_URL`   | Redis connection string                      | `redis://localhost:6379` |
| `UPSTREAM_URL`| Base URL of the exchange-rate API            | `https://open.er-api.com/v6/latest` |
| `TTL`         | Cache freshness window, in seconds           | `60` |
| `MAX_RETRIES` | Upstream retry attempts before giving up     | `5` |
| `BACKOFF`     | Initial backoff between retries, in seconds  | `1` |

### Running locally

**Option A — Docker Compose (recommended).** Runs the app and Redis together:

```bash
docker compose up --build
```

The app is then at `http://localhost:8000`. Inside compose, the app reaches Redis via the service name (`REDIS_URL=redis://redis:6379`).

**Option B — bare uvicorn.** Start a Redis container first, then run the app:

```bash
docker run -d --name redis -p 6379:6379 redis
uvicorn main:app --reload
```

With no `REDIS_URL` set, the app defaults to `redis://localhost:6379`. Then open `http://localhost:8000/docs`.

### Running the tests

From the folder that contains `main.py`:

```bash
python -m pytest -v
```

The tests mock the cache and the upstream, so they need neither a live Redis nor a live network.

---

## API Reference

### `GET /rates`

Returns the exchange rate for a currency pair.

| Query param | Required | Example |
|-------------|----------|---------|
| `base`      | yes      | `USD`   |
| `target`    | yes      | `EGP`   |

**Example**

```
GET /rates?base=USD&target=EGP
```

```json
{ "base": "USD", "target": "EGP", "rate": 49.32 }
```

When the upstream is down but a cached value exists, the response is still `200 OK` with a stale flag:

```json
{ "base": "USD", "target": "EGP", "rate": 49.10, "warning": "Data may be stale due to upstream issues" }
```

**Status codes:** `200` success (fresh or stale) · `404` unknown currency · `503` upstream down and nothing cached.

### `GET /stats`

Live cache metrics.

```json
{
  "hits": 1,
  "misses": 2,
  "errors": 0,
  "hit_rate": 0.333,
  "avg_latency_ms": 205.38,
  "last_refresh": {
    "USD:EGP": 1781640396.97,
    "USD:EUR": 1781640401.86
  }
}
```

### `GET /health`

```json
{ "status": "ok" }
```

---

## Deployment

The app is containerized and deployed to **Hugging Face Spaces** using the Docker SDK, with Redis provided by **Upstash** (serverless, free tier).

Key points:

- The Dockerfile listens on **port 7860** (Hugging Face's expected port).
- Configuration (the `REDIS_URL` Upstash connection string, `UPSTREAM_URL`, `TTL`, etc.) is supplied through the Space's **Secrets/Variables**, never committed to the repo.
- For cloud Redis, the connection uses a single `REDIS_URL` parsed by `redis.from_url(...)`, which carries the host, port, password, and TLS (`rediss://`) in one string — so the same code runs locally (`redis://localhost:6379`), in Compose (`redis://redis:6379`), and in the cloud, with only the variable's value changing.

---

## How It Was Built — Development Stages

The project was built incrementally, one concept at a time, with each stage runnable on its own before the next.

### Stage 0 — Setup ✅
Chose `open.er-api.com` as the upstream (no API key needed). Set up FastAPI + uvicorn + httpx and the layered folder structure. A `/health` endpoint returns `{"status": "ok"}`.

### Stage 1 — Naive proxy (no cache) ✅
`GET /rates?base=USD&target=EUR` flows through all layers and returns a live rate. Every request hit the upstream — no caching yet.

### Stage 2 — In-memory cache ✅
A `cache_client` backed by a Python dict with `get` / `set_value` / `get_age`. TTL read from the `TTL` env var (default 60s). Cache key format `"BASE:TARGET"`. Cache-aside logic added to the service, with HIT/MISS logging.

```
MISS USD:EUR  (278.78 ms)      ← upstream round-trip
HIT  USD:EUR  (0.20 ms)        ← served from memory, ~1400× faster
```

The first request took 278 ms (the full upstream call); the second took 0.20 ms (pure memory lookup). **Known limitation:** an in-memory cache resets on restart and isn't shared across processes — fixed in Stage 5.

### Stage 3 — Resilience ✅
A retry loop (up to 5 attempts, each failure logged) with exponential backoff. Stale-on-failure: if the upstream is unreachable and a cached value exists, it's returned with `stale: true`. A `503` is returned only when the upstream is down **and** nothing is cached; a `404` for well-formed but unknown currencies.

```
attempt 1 failed: getaddrinfo failed
...
attempt 5 failed: getaddrinfo failed
STALE USD:EUR  (15175.54 ms)   ← served from cache, flagged stale
```

This proves the user gets an answer rather than an error when the upstream breaks, the retry loop exhausts all attempts before giving up, and the service escalates to 503 only when it truly has nothing to serve.

### Stage 4 — Observability ✅
A `metrics.py` module with counters for hits, misses, errors, total latency, and per-key last-refresh timestamps. `record_hit` / `record_miss` / `record_error` are called from the service; `snapshot()` computes hit rate and average latency on read; `GET /stats` exposes them.

```json
{ "hits": 1, "misses": 2, "errors": 0, "hit_rate": 0.333, "avg_latency_ms": 205.38, "last_refresh": { "USD:EGP": 1781640396.97, "USD:EUR": 1781640401.86 } }
```

The hit rate climbs with repeat requests, confirming the cache is actually reducing upstream load.

### Stage 5 — Redis ✅
`cache_client.py` now talks to Redis instead of the dict. The four functions (`get`, `set_value`, `get_age`, `get_stale`) kept their exact signatures, so the service didn't change at all. Values are stored as JSON (`{"value": ..., "stored_at": <unix time>}`), and **TTL is still enforced in application code** rather than via Redis's own expiry — this keeps expired values available for the Stage 3 stale-fallback.

Why Redis, and why it's still RAM: Redis is an in-memory store (sub-millisecond, like the dict) but runs as a **separate process**, so the cache survives an app restart and can be shared across multiple API instances — exactly what's needed once the app runs in containers.

### Stage 6 — Dockerize + Deploy ✅
The app was packaged with a Dockerfile and a docker-compose that runs the app and Redis together locally. Configuration moved fully into environment variables. The Redis connection was unified to a single `REDIS_URL` (`redis.from_url`) so the same code works locally and against cloud Redis. Deployed to **Hugging Face Spaces** (Docker SDK, port 7860) with Redis hosted on **Upstash**, and secrets set in the Space settings.

### Stage 7 — Tests + CI ✅
A **pytest** suite of 5 tests run through FastAPI's `TestClient`: `/health`, a cache hit, a cache miss, an unknown currency (404), and the stale-while-error fallback. The cache is mocked with `monkeypatch` and the upstream with **respx** (including an `httpx.ConnectError` side-effect to simulate an outage); `asyncio.sleep` is patched to a no-op so the retry backoff doesn't slow the suite. A **GitHub Actions** workflow (`.github/workflows/ci.yml`) runs all five tests on every push and pull request.

```
tests/test_health.py::test_health PASSED
tests/test_rates.py::test_cache_hit PASSED
tests/test_rates.py::test_cache_miss PASSED
tests/test_rates.py::test_unknown_currency PASSED
tests/test_rates.py::test_stale_fallback PASSED
===================== 5 passed =====================
```

---

## Roadmap

- [x] Automated tests (pytest) and CI (GitHub Actions)
- [ ] Optional stats dashboard (small frontend reading `/stats`)
- [ ] Semantic / multi-pair batch endpoints

---

## License

MIT