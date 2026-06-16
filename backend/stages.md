# Caching Proxy — Staged Build Plan

A currency exchange-rate caching proxy built with FastAPI and Redis, deployed to a live URL.

**The one rule:** do one new thing at a time. Each stage runs on its own before you start the next, so you're never debugging two new things at once. Every stage ends with something you can actually run and check.

---

## Stage 0 — Mental model + setup

**Goal:** Understand the problem and get a "hello world" endpoint running.

**Build:**
- Pick a free, no-key upstream API (e.g. open.er-api.com or frankfurter.app).
- Set up a git repo, a virtual environment, and install `fastapi`, `uvicorn`, `httpx`.
- Create the layered folder structure (routes / controllers / services / clients).

**Understand:** Why does anyone put a cache in front of an API? (Two reasons: speed, and not exceeding the upstream's rate limit.) What's the difference between *your* API and the *upstream* API?

**Done when:** A trivial FastAPI endpoint runs locally and you can open it in the browser.

---

## Stage 1 — The naive proxy (no cache)

**Goal:** Prove a request travels through all your layers and returns a live rate.

**Build:**
- `GET /rates?base=USD&target=EGP` flowing routes → controller → service → upstream client.
- The upstream client calls the currency API every time and returns the rate.
- Validate the inputs; reject nonsense currency codes.

**Understand:** Every call currently goes to the upstream. If 1,000 users hit you, that's 1,000 upstream calls. Hold that picture — the next stage fixes it.

**Done when:** The endpoint returns a correct, live rate by proxying the upstream.

---

## Stage 2 — Add caching (in-memory first)

**Goal:** Stop calling the upstream for data you already have.

**Build:**
- A `cache_client` backed by an in-memory dictionary, with `get(key)` and `set(key, value)`.
- Cache-aside logic in the service: build the key (`"USD:EGP"`), check the cache; on a hit return it; on a miss fetch from upstream, store it, return it.
- Expire entries after a configurable TTL (e.g. 60 seconds).
- Log "HIT" or "MISS" so you can see it working.

**Understand:** How do you choose the TTL? A 60-second-stale exchange rate is fine; a stock price might not be. The TTL is a judgment call about how fresh "fresh enough" is.

**Done when:** The second identical request within the TTL logs HIT, skips the upstream, and is noticeably faster.

---

## Stage 3 — Resilience

**Goal:** Behave well when the upstream is slow or down. (This is the stage that makes the project impressive.)

**Build:**
- A timeout on every upstream call.
- A retry with backoff (try again after 1s, then 2s, then give up).
- Stale-while-error: if the upstream is unreachable, serve the last cached value flagged as `stale: true` instead of erroring.
- (Optional) a circuit breaker: stop calling a dead upstream for a short window after repeated failures.

**Understand:** What's better for a user — an error, or a slightly old answer with a warning? That single decision is the difference between a fragile service and a resilient one.

**Done when:** You can break the upstream (point it at a bad URL) and still get a stale-flagged value back.

---

## Stage 4 — Observability

**Goal:** Be able to answer "is the cache actually helping?"

**Build:**
- Track cache hit rate, average upstream latency, and error count.
- Expose them at `GET /stats`, along with the last successful refresh time per currency pair.
- Add a `GET /health` endpoint.

**Understand:** If someone asked "is the cache helping?", which number answers that? (Hit rate. If it's near zero, your cache is useless and you'd want to know.)

**Done when:** `/stats` shows a hit ratio that climbs as you make repeat requests.

---

## Stage 5 — Swap in-memory for Redis

**Goal:** Use a real, shared, restart-surviving cache.

**Build:**
- Run Redis locally (via Docker).
- Replace the dict inside `cache_client` with Redis (`redis` package). Same `get`/`set` interface — only the insides change.
- Use Redis's built-in expiry instead of manual timestamp checks.

**Understand:** Restart your server — the in-memory cache vanishes, Redis survives. Run two copies of your app and they share one Redis cache instead of each having their own. That's why real systems use it.

**Done when:** Your cache survives a server restart.

---

## Stage 6 — Dockerize and deploy

**Goal:** A live URL you can open on your phone.

**Build:**
- A Dockerfile for the app.
- A docker-compose that runs app + Redis together.
- Deploy to Render, Railway, or Fly.io.
- Read all config (upstream URL, TTL, Redis connection) from environment variables.

**Understand:** Secrets and config shouldn't live in your code — so you can change them per environment and never commit a password to git.

**Done when:** A live URL returns a real rate.

---

## Stage 7 — Tests + CI (optional polish)

**Goal:** Stop looking student-built.

**Build:**
- A handful of tests: one proving a cache hit, one proving stale-fallback works.
- A GitHub Actions workflow that runs the tests on every push.

**Done when:** A green check appears on your commits.

---

## Project structure reference

```
backend/
└── src/
    ├── main.py              creates the app, registers routes
    ├── config.py            loads settings from env (upstream URL, TTL, Redis URL)
    ├── routes/              declares paths, points them at controllers
    ├── controllers/         reads/validates the request, shapes the response (HTTP layer)
    ├── services/            the cache-aside brain (business logic, no HTTP)
    ├── clients/             cache_client + upstream_client (hide Redis and httpx)
    ├── schemas/             response shapes (Pydantic models)
    └── metrics.py           tracks hits/misses/latency for /stats
tests/
Dockerfile · docker-compose.yml · requirements.txt · .env.example
```

**Dependency direction never reverses:** routes → controllers → services → clients → external systems. Nothing points back up. If you ever import `httpx` inside a controller, that's the smell that something's in the wrong file.

---

## HTTP status codes by case

- **200** — a rate came back (cache hit or miss — same code either way).
- **200 + `stale: true`** — upstream down, served last cached value. The request still succeeded.
- **422** — a required parameter is missing (FastAPI returns this automatically).
- **400** — input present but malformed.
- **404** — well-formed currency code, but that rate doesn't exist.
- **504** — upstream timed out and no cache to fall back on.
- **502** — upstream returned garbage and no cache to fall back on.
- **500** — a bug in your own code (FastAPI returns this automatically).

Reason from the families: **2xx** = success, **4xx** = the caller's mistake, **5xx** = your side (or a dependency) failed.
