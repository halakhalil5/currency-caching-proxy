import httpx
from fastapi import HTTPException
import time

from config import UPSTREAM_URL, TIMEOUT
from clients.cache_client import get, set_value, get_age


async def get_rate(base: str, target: str):
    start = time.perf_counter()
    key = f"{base}:{target}"
    cached = get(key)
    if cached is not None:
        print(f"HIT  {key}")
        age = get_age(key)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"HIT  {key}  ({elapsed_ms:.2f} ms)")
        print(f"Cache age: {age} seconds")
        return {"base": base, "target": target, "rate": cached}

    print(f"MISS {key}")

    url = f"{UPSTREAM_URL}/{base}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url)

    data = response.json()
    rates = data.get("rates", {})

    if target not in rates:
        raise HTTPException(status_code=404, detail=f"No rate found for {target}")

    rate = rates[target]
    set_value(key, rate)
    age = get_age(key)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"MISS {key}  ({elapsed_ms:.2f} ms)")
    print(f"Cache age: {age} seconds")
    return {"base": base, "target": target, "rate": rate}
