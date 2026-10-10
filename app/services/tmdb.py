"""TMDB (The Movie Database): movie and series search, details in Traditional Chinese."""

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

API_URL = "https://api.themoviedb.org/3"
IMAGE_URL = "https://image.tmdb.org/t/p/w342"
LANGUAGE = "zh-TW"


class TmdbError(Exception):
    pass


@dataclass
class Title:
    external_id: str  # "movie:603" / "tv:1396"
    title: str
    original_title: str | None
    cover_url: str | None
    year: int | None
    kind: str  # "movie" | "tv"

    @property
    def kind_label(self) -> str:
        return "電影" if self.kind == "movie" else "影集"


def configured() -> bool:
    return bool(settings.tmdb_api_key)


def _auth() -> tuple[dict, dict]:
    """v4 read tokens are long JWTs sent as a bearer header; v3 keys go in the query string."""
    key = settings.tmdb_api_key
    if len(key) > 40:
        return {"Authorization": f"Bearer {key}"}, {}
    return {}, {"api_key": key}


async def _get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if not configured():
        raise TmdbError("TMDB_API_KEY is not set")
    headers, auth_params = _auth()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{API_URL}{path}", params={**params, **auth_params, "language": LANGUAGE}, headers=headers)
    except httpx.HTTPError as e:
        raise TmdbError(str(e)) from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise TmdbError(f"HTTP {r.status_code}")
    return r.json()


def _parse(item: dict[str, Any], kind: str | None = None) -> Title | None:
    kind = kind or item.get("media_type")
    if kind not in ("movie", "tv"):
        return None
    title = item.get("title") or item.get("name") or ""
    original = item.get("original_title") or item.get("original_name")
    date = item.get("release_date") or item.get("first_air_date") or ""
    poster = item.get("poster_path")
    return Title(
        external_id=f"{kind}:{item['id']}",
        title=title or original or "",
        original_title=original if original and original != title else None,
        cover_url=f"{IMAGE_URL}{poster}" if poster else None,
        year=int(date[:4]) if date[:4].isdigit() else None,
        kind=kind,
    )


async def search(query: str, prefer: str | None = None) -> list[Title]:
    """Movies and series matching `query`; `prefer` ("movie"/"tv") floats that kind to the top."""
    data = await _get("/search/multi", {"query": query, "include_adult": "false"})
    titles = [t for t in (_parse(i) for i in (data or {}).get("results", [])) if t]
    if prefer:
        titles.sort(key=lambda t: t.kind != prefer)
    return titles[:12]


async def get_title(external_id: str) -> Title | None:
    kind, _, tmdb_id = external_id.partition(":")
    if kind not in ("movie", "tv") or not tmdb_id.isdigit():
        return None
    data = await _get(f"/{kind}/{tmdb_id}", {})
    return _parse(data, kind) if data else None


async def get_details(external_id: str) -> dict[str, Any] | None:
    """Raw details (+ credits) for the work page and genre lookups."""
    kind, _, tmdb_id = external_id.partition(":")
    if kind not in ("movie", "tv") or not tmdb_id.isdigit():
        return None
    data = await _get(f"/{kind}/{tmdb_id}", {"append_to_response": "credits"})
    if data:
        data["_kind"] = kind
    return data
