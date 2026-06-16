from metrics import snapshot


async def get_stats():
    return snapshot()
