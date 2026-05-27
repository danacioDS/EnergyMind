import hashlib
import json
from typing import Optional

from redis.asyncio import Redis

_redis: Optional[Redis] = None


def _make_key(question: str, subsector: Optional[str]) -> str:
    raw = f"{question}:{subsector or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def init_redis(host: str = "localhost", port: int = 6379) -> Redis:
    global _redis
    _redis = Redis(host=host, port=port, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


async def get_cached(question: str, subsector: Optional[str] = None) -> Optional[dict]:
    if _redis is None:
        return None
    key = _make_key(question, subsector)
    data = await _redis.get(key)
    if data is not None:
        return json.loads(data)
    return None


async def set_cached(question: str, subsector: Optional[str], response: dict, ttl: int = 3600) -> None:
    if _redis is None:
        return
    key = _make_key(question, subsector)
    await _redis.setex(key, ttl, json.dumps(response))
