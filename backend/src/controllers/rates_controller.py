from fastapi import Query

from services import rates_service


async def get_rate(base: str = Query(...), target: str = Query(...)):
    base = base.upper()
    target = target.upper()
    return await rates_service.get_rate(base, target)


