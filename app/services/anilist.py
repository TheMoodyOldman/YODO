"""AniList GraphQL API (no key needed, ~90 requests/min)."""

from dataclasses import dataclass
from typing import Any

import httpx

API_URL = "https://graphql.anilist.co"

_FIELDS = "id title { romaji english native } coverImage { large } seasonYear format"
_SEARCH = f"""
query ($search: String) {{
  Page(perPage: 12) {{
    media(search: $search, type: ANIME, sort: SEARCH_MATCH, isAdult: false) {{ {_FIELDS} }}
  }}
}}"""
_GET = f"query ($id: Int) {{ Media(id: $id, type: ANIME) {{ {_FIELDS} }} }}"

FORMAT_LABELS = {
    "TV": "TV 動畫",
    "TV_SHORT": "短篇",
    "MOVIE": "劇場版",
    "SPECIAL": "特別篇",
    "OVA": "OVA",
    "ONA": "ONA",
    "MUSIC": "MV",
}


class AniListError(Exception):
    pass


@dataclass
class Anime:
    id: int
    title: str
    original_title: str | None
    cover_url: str | None
    year: int | None
    format: str | None

    @property
    def format_label(self) -> str | None:
        return FORMAT_LABELS.get(self.format or "", self.format)


def _parse(media: dict[str, Any]) -> Anime:
    t = media["title"]
    return Anime(
        id=media["id"],
        title=t.get("english") or t.get("romaji") or t.get("native") or "",
        original_title=t.get("native"),
        cover_url=(media.get("coverImage") or {}).get("large"),
        year=media.get("seasonYear"),
        format=media.get("format"),
    )


async def _query(query: str, variables: dict[str, Any]) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(API_URL, json={"query": query, "variables": variables})
        payload = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise AniListError(str(e)) from e
    if r.status_code == 404:
        return None
    if r.status_code != 200 or payload.get("errors"):
        raise AniListError(f"HTTP {r.status_code}: {payload.get('errors')}")
    return payload["data"]


async def search_anime(text: str) -> list[Anime]:
    data = await _query(_SEARCH, {"search": text})
    return [_parse(m) for m in data["Page"]["media"]] if data else []


async def get_anime(anilist_id: int) -> Anime | None:
    data = await _query(_GET, {"id": anilist_id})
    return _parse(data["Media"]) if data and data.get("Media") else None


_DETAILS = """
query ($id: Int) {
  Media(id: $id, type: ANIME) {
    siteUrl description(asHtml: false) genres episodes season seasonYear format averageScore
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge color }
  }
}"""


async def get_details(anilist_id: int) -> dict[str, Any] | None:
    """Full AniList record for an anime page, or None."""
    data = await _query(_DETAILS, {"id": anilist_id})
    return data.get("Media") if data else None
