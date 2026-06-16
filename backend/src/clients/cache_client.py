import time
from config import TTL

_cache = {}

def get(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    value, timestamp = entry
    if time.time() - timestamp < TTL:
        return value
    del _cache[key]
    return None

def set_value(key, value):
    _cache[key] = (value, time.time())


def get_age(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    _, timestamp = entry
    return time.time() - timestamp