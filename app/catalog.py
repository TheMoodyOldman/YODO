"""Database-backed cache for lists fetched from external APIs (see models.CatalogCache).

Fresh entries are served without calling the API; stale ones are refreshed, and if the API fails
the stale copy is served instead. Only when nothing was ever cached does the error reach the page.
"""

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from app.models import CatalogCache, utcnow


def _age(row: CatalogCache) -> timedelta:
    fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
    return utcnow() - fetched


def get(session: Session, key: str) -> tuple[Any, datetime] | None:
    row = session.get(CatalogCache, key)
    return (json.loads(row.payload), row.fetched_at) if row else None


def put(session: Session, key: str, value: Any, fetched_at: datetime | None = None) -> None:
    row = session.get(CatalogCache, key) or CatalogCache(key=key, payload="")
    row.payload = json.dumps(value, ensure_ascii=False)
    row.fetched_at = fetched_at or utcnow()
    session.add(row)
    session.commit()


async def cached(
    session: Session,
    key: str,
    max_age: timedelta,
    fetch: Callable[[], Awaitable[Any]],
    errors: tuple[type[BaseException], ...],
) -> Any:
    """The cached value for `key`, refreshed with `fetch()` when older than `max_age`."""
    row = session.get(CatalogCache, key)
    if row is not None and _age(row) < max_age:
        return json.loads(row.payload)
    try:
        value = await fetch()
    except errors:
        if row is not None:
            return json.loads(row.payload)  # stale beats nothing
        raise
    put(session, key, value)
    return value
