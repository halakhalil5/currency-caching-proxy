from fastapi import APIRouter

from controllers.rates_controller import get_rate

router = APIRouter()

@router.get("/rates")
async def rates(base: str, target: str):
    return await get_rate(base, target)
