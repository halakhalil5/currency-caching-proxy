
import httpx
import os
import fastapi
from fastapi import HTTPException
from config import UPSTREAM_URL, TIMEOUT

async def get_rate(base: str, target: str):
    if not base or not target:
        raise HTTPException(status_code=422, detail="Base and target currencies are required")
    url= f"{UPSTREAM_URL}/{base}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url)
        
    data = response.json()
    rates = data.get("rates", {})

    if target not in rates:
        raise HTTPException(status_code=404, detail=f"No rate found for {target}")
    

    return {"base": base, "target": target, "rate": rates[target]}
