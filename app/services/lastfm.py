"""Last.fm API: web sign-in (proves account ownership) and scrobble history."""

import asyncio
import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.importers.youtube import TAIPEI

API_URL = "https://ws.audioscrobbler.com/2.0/"
AUTH_URL = "https://www.last.fm/api/auth/"

PAGE_SIZE = 200  # API maximum
MAX_PAGES = 100  # ~20k scrobbles per sync; keeps one sync under a minute
_PLACEHOLDER_IMAGE = "2a96cbd8b46e442fc41c2b86b821562f"  # Last.fm's grey star "no artwork" image
_ERR_PRIVATE = {17}  # "Login: User required to be logged in" = recent listening is hidden
_ERR_NO_USER = {6}


class LastfmError(Exception):
    pass


class LastfmPrivate(LastfmError):
    pass


@dataclass
class Scrobbles:
    songs: dict[str, tuple[str, str, str | None]]  # key -> (title, artist, cover_url)
    plays: Counter[tuple[str, str]]  # (key, "YYYY-MM") -> plays
    truncated: bool  # hit MAX_PAGES before reaching `since`


def song_key(artist: str, title: str) -> str:
    """Last.fm identifies tracks by name; many have no MBID, so key on normalized artist + title."""
    return f"{artist.casefold().strip()}␟{title.casefold().strip()}"[:500]


def auth_url(callback: str) -> str:
    return f"{AUTH_URL}?{urlencode({'api_key': settings.lastfm_api_key, 'cb': callback})}"


def _sign(params: dict[str, str]) -> str:
    raw = "".join(k + params[k] for k in sorted(params)) + settings.lastfm_shared_secret
    return hashlib.md5(raw.encode()).hexdigest()


async def _call(client: httpx.AsyncClient, params: dict[str, str]) -> dict[str, Any]:
    for attempt in range(2):  # Last.fm returns sporadic 5xx; retry once
        try:
            r = await client.get(API_URL, params={**params, "format": "json"})
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            if attempt:
                raise LastfmError(str(e)) from e
            await asyncio.sleep(1)
            continue
        if "error" in data:
            if data["error"] in _ERR_PRIVATE:
                raise LastfmPrivate(data.get("message", ""))
            if r.status_code >= 500 and not attempt:
                await asyncio.sleep(1)
                continue
            raise LastfmError(f"{data['error']}: {data.get('message')}")
        return data
    raise LastfmError("unreachable")


async def get_session_username(token: str) -> str | None:
    """Exchange the callback token for the signed-in username (auth.getSession)."""
    params = {"method": "auth.getSession", "api_key": settings.lastfm_api_key, "token": token}
    params["api_sig"] = _sign(params)
    async with httpx.AsyncClient(timeout=15) as client:
        data = await _call(client, params)
    return (data.get("session") or {}).get("name")


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _cover(images: Any) -> str | None:
    by_size = {img.get("size"): img.get("#text") for img in _as_list(images) if isinstance(img, dict)}
    url = by_size.get("extralarge") or by_size.get("large") or by_size.get("medium")
    return url if url and _PLACEHOLDER_IMAGE not in url else None


async def get_scrobbles(username: str, since: datetime) -> Scrobbles:
    """All scrobbles since `since`, bucketed by month in Taiwan time. Raises LastfmPrivate
    if the user hides their listening history."""
    if not settings.lastfm_api_key:
        raise LastfmError("LASTFM_API_KEY is not set")
    songs: dict[str, tuple[str, str, str | None]] = {}
    plays: Counter[tuple[str, str]] = Counter()
    base = {
        "method": "user.getrecenttracks",
        "user": username,
        "api_key": settings.lastfm_api_key,
        "limit": str(PAGE_SIZE),
        "from": str(int(since.timestamp())),
    }
    page = total_pages = 1
    async with httpx.AsyncClient(timeout=20) as client:
        while page <= min(total_pages, MAX_PAGES):
            data = (await _call(client, {**base, "page": str(page)})).get("recenttracks", {})
            total_pages = int(data.get("@attr", {}).get("totalPages") or 0)
            for t in _as_list(data.get("track")):
                if (t.get("@attr") or {}).get("nowplaying") or "date" not in t:
                    continue
                artist = (t.get("artist") or {}).get("#text", "").strip()
                title = (t.get("name") or "").strip()
                if not artist or not title:
                    continue
                key = song_key(artist, title)
                if key not in songs:  # newest first, so the latest spelling/artwork wins
                    songs[key] = (title, artist, _cover(t.get("image")))
                month = datetime.fromtimestamp(int(t["date"]["uts"]), TAIPEI).strftime("%Y-%m")
                plays[(key, month)] += 1
            page += 1
            if page <= total_pages:
                await asyncio.sleep(0.25)  # stay well under Last.fm's ~5 requests/second
    return Scrobbles(songs=songs, plays=plays, truncated=total_pages > MAX_PAGES)


async def get_track_info(artist: str, title: str) -> dict[str, Any] | None:
    """track.getInfo (album, tags, global listeners), or None if Last.fm doesn't know the track."""
    if not settings.lastfm_api_key or not artist or not title:
        return None
    params = {
        "method": "track.getinfo",
        "artist": artist,
        "track": title,
        "api_key": settings.lastfm_api_key,
        "autocorrect": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = await _call(client, params)
    except LastfmError:
        return None
    return data.get("track")


async def get_artist_tags(artist: str) -> list[tuple[str, int]] | None:
    """artist.getTopTags as (tag, strength 0-100), or None if unknown / unreachable."""
    if not settings.lastfm_api_key or not artist:
        return None
    params = {"method": "artist.gettoptags", "artist": artist, "api_key": settings.lastfm_api_key, "autocorrect": "1"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = await _call(client, params)
    except LastfmError:
        return None
    tags = _as_list((data.get("toptags") or {}).get("tag"))
    return [(t["name"], int(t.get("count") or 0)) for t in tags if isinstance(t, dict) and t.get("name")]


async def get_track_tags(artist: str, title: str) -> list[tuple[str, int]] | None:
    """track.getTopTags: the title disambiguates artists that share a name."""
    if not settings.lastfm_api_key or not artist or not title:
        return None
    params = {"method": "track.gettoptags", "artist": artist, "track": title, "api_key": settings.lastfm_api_key, "autocorrect": "1"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            data = await _call(client, params)
    except LastfmError:
        return None
    tags = _as_list((data.get("toptags") or {}).get("tag"))
    return [(t["name"], int(t.get("count") or 0)) for t in tags if isinstance(t, dict) and t.get("name")]
