"""Small API calls for the 新手教學 cover picker's popular lists and searches (app.quickpick).
Every function raises PopularError on any failure; callers fall back to built-in lists."""

import asyncio
from typing import Any

import httpx

from app.config import settings
from app.services import anilist, tmdb
from app.services.steam import ASSET_URL

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
DEEZER_URL = "https://api.deezer.com"


class PopularError(Exception):
    pass


async def _get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            r = await client.get(url, params=params)
        if r.status_code != 200:
            raise PopularError(f"HTTP {r.status_code}")
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise PopularError(str(e)) from e


def steam_cover(appid: int | str) -> str:
    return f"{ASSET_URL}/{appid}/library_600x900.jpg"


async def steam_search(query: str) -> list[dict]:
    """Steam store search in Traditional Chinese (no key needed)."""
    data = await _get(STEAM_SEARCH_URL, {"term": query, "l": "tchinese", "cc": "TW"})
    return [{"id": str(i["id"]), "title": i["name"], "cover_url": steam_cover(i["id"])}
            for i in data.get("items", []) if i.get("type") == "app" and i.get("id")][:12]


_POPULAR_ANIME = """
query ($perPage: Int) {
  Page(perPage: $perPage) {
    media(type: ANIME, sort: POPULARITY_DESC, format_in: [TV, MOVIE], isAdult: false) {
      id title { romaji english native } coverImage { large } seasonYear format
    }
  }
}"""


async def anilist_popular(per_page: int = 30) -> list[anilist.Anime]:
    try:
        try:
            data = await anilist._query(_POPULAR_ANIME, {"perPage": per_page})
        except anilist.AniListError as e:
            if e.retry_after is None or e.retry_after > 65:
                raise
            await asyncio.sleep(e.retry_after)  # rate limited: wait as AniList asks, once
            data = await anilist._query(_POPULAR_ANIME, {"perPage": per_page})
    except anilist.AniListError as e:
        raise PopularError(str(e)) from e
    return [anilist._parse(m) for m in (data or {}).get("Page", {}).get("media", [])]


async def lastfm_top_artists(country: str = "Taiwan", limit: int = 30) -> list[str]:
    if not settings.lastfm_api_key:
        raise PopularError("no LASTFM_API_KEY")
    data = await _get(LASTFM_URL, {"method": "geo.gettopartists", "country": country, "api_key": settings.lastfm_api_key,
                                   "format": "json", "limit": limit})
    names = [a.get("name") for a in (data.get("topartists") or {}).get("artist", [])]
    if not names:
        raise PopularError("empty chart")
    return [n for n in names if n]


async def deezer_artists(query: str, limit: int = 8) -> list[dict]:
    """Artists with pictures (Last.fm no longer serves artist images)."""
    data = await _get(f"{DEEZER_URL}/search/artist", {"q": query, "limit": limit})
    return [{"name": a["name"], "cover_url": a.get("picture_xl") or a.get("picture_big")}
            for a in data.get("data", []) if a.get("name")]


async def tmdb_trending() -> list[tmdb.Title]:
    try:
        data = await tmdb._get("/trending/all/week", {})
    except tmdb.TmdbError as e:
        raise PopularError(str(e)) from e
    titles = [t for t in (tmdb._parse(i) for i in (data or {}).get("results", [])) if t and not t.is_anime]
    if not titles:
        raise PopularError("empty trending list")
    return titles[:24]
