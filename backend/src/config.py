import os

UPSTREAM_URL = os.getenv("UPSTREAM", "https://open.er-api.com/v6/latest")
TIMEOUT = int(os.getenv("timeout", "6"))
TTL=int(os.getenv("TTL", "60"))
BACKOFF=1
MAX_RETRIES=5
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
