import httpx
from fastapi import HTTPException
import time
import asyncio
from config import MAX_RETRIES, BACKOFF, TIMEOUT
from metrics import record_hit, record_miss, record_error
from config import UPSTREAM_URL, TIMEOUT
from clients.cache_client import get, set_value, get_age, get_stale


async def get_rate(base: str, target: str):
    start = time.perf_counter()
    key = f"{base}:{target}"
    cached = get(key)
    if cached is not None:
        age = get_age(key)
        elapsed_ms = (time.perf_counter() - start) * 1000
        record_hit(elapsed_ms)
        print(f"HIT  {key}  ({elapsed_ms:.2f} ms)")
        print(f"Cache age: {age} seconds")
        return {"base": base, "target": target, "rate": cached}
    return await fetch_rate(base, target, start, key)


async def fetch_rate(base: str, target: str, start: float, key: str):
    print(f"MISS {key}")

    url = f"{UPSTREAM_URL}/{base}"
    delay = BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()
                rates = data.get("rates", {})

                if target not in rates:
                    raise HTTPException(status_code=404, detail=f"No rate found for {target}")

                rate = rates[target]
                set_value(key, rate)
                age = get_age(key)
                elapsed_ms = (time.perf_counter() - start) * 1000
                record_miss(key, elapsed_ms)
                print(f"FRESH {key}  ({elapsed_ms:.2f} ms)")
                print(f"Cache age: {age} seconds")
                return {"base": base, "target": target, "rate": rate}
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            print(f"attempt {attempt} failed: {e}")
            if attempt == MAX_RETRIES:
                record_error()
                stale = get_stale(key)
                if stale is not None:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    print(f"STALE {key}  ({elapsed_ms:.2f} ms)")
                    return {"base": base, "target": target, "rate": stale,
                            "warning": "Data may be stale due to upstream issues"}
                print(f"FAIL {key} — upstream down, no cache")
                raise HTTPException(status_code=503, detail="Upstream unavailable and no cached data")

            print(f"retrying in {delay}s...")
            await asyncio.sleep(delay)
            delay *= 2