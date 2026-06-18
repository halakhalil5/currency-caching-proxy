import time
from config import REDIS_URL, TTL ,REDIS_HOST, REDIS_PORT
import json
import redis

r = redis.from_url(REDIS_URL, decode_responses=True)
# this commented section was the simple in-memory cache implementation. It was replaced with Redis for better performance and scalability.
# _cache = {}

# def get(key):
#     entry = _cache.get(key)
#     if entry is None:
#         return None
#     value, timestamp = entry
#     if time.time() - timestamp < TTL:
#         return value
#     return None

# def set_value(key, value):
#     _cache[key] = (value, time.time())


# def get_age(key):
#     entry = _cache.get(key)
#     if entry is None:
#         return None
#     _, timestamp = entry
#     return time.time() - timestamp

# def get_stale(key):
#     entry = _cache.get(key)
#     if entry is None:
#         return None
#     value, _ = entry
#     return value


# /////////////////////////////////////////////////////////////////////////////////////////////////

# the Redis-based cache client implementation

def get(key):
    entry = r.get(key)
    if entry is None:
        return None
    entry = json.loads(entry)
    value, timestamp = entry["value"], entry["stored_at"]
    if time.time() - timestamp < TTL:
        return value
    return None



def set_value(key, value):
    r.set(key, json.dumps({"value": value, "stored_at": time.time()}))


def get_age(key):
    entry = r.get(key)
    if entry is None:
        return None
    entry = json.loads(entry)
    return time.time() - entry["stored_at"]

def get_stale(key):
    entry = r.get(key)
    if entry is None:
        return None
    entry = json.loads(entry)
    value, _ = entry["value"], entry["stored_at"]
    return value
