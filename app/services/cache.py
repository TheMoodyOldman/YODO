"""Tiny in-process TTL cache for slow, rate-limited metadata lookups (store pages, AniList, Last.fm)."""

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

_MAX_ENTRIES = 2000


def ttl_cache(seconds: int) -> Callable:
    def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        store: dict[tuple, tuple[float, Any]] = {}

        @wraps(fn)
        async def wrapper(*args: Any) -> Any:
            hit = store.get(args)
            if hit and hit[0] > time.monotonic():
                return hit[1]
            value = await fn(*args)
            if len(store) >= _MAX_ENTRIES:
                store.clear()
            store[args] = (time.monotonic() + seconds, value)
            return value

        return wrapper

    return decorate
