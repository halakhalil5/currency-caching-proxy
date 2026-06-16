from fastapi import APIRouter

from controllers.stats_controller import get_stats

router = APIRouter()

@router.get("/stats")
async def stats():
    return await get_stats()
