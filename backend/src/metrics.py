import time

_metrics = {
    "hits": 0,
    "misses": 0,
    "errors": 0,
    "total_latency_ms": 0.0,
    "count": 0,
}
_last_refresh = {}   # key -> timestamp of last successful fetch

def record_hit(latency_ms):
    _metrics["hits"] += 1
    _metrics["total_latency_ms"] += latency_ms
    _metrics["count"] += 1

def record_miss(key, latency_ms):
    _metrics["misses"] += 1
    _metrics["total_latency_ms"] += latency_ms
    _metrics["count"] += 1
    _last_refresh[key] = time.time()

def record_error():
    _metrics["errors"] += 1

def snapshot():
    hits = _metrics["hits"]
    misses = _metrics["misses"]
    lookups = hits + misses
    hit_rate = hits / lookups if lookups else 0
    avg_latency = _metrics["total_latency_ms"] / _metrics["count"] if _metrics["count"] else 0
    return {
        "hits": hits,
        "misses": misses,
        "errors": _metrics["errors"],
        "hit_rate": round(hit_rate, 3),
        "avg_latency_ms": round(avg_latency, 2),
        "last_refresh": _last_refresh,
    }