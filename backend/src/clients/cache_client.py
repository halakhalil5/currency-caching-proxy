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
    return None

def set_value(key, value):
    _cache[key] = (value, time.time())


def get_age(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    _, timestamp = entry
    return time.time() - timestamp

def get_stale(key):
    entry = _cache.get(key)
    if entry is None:
        return None
    value, _ = entry
    return value