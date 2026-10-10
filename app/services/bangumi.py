"""Bangumi 番組計劃 (bgm.tv) API: Chinese names for anime. No key needed, but it asks for a
descriptive User-Agent. Names are mostly Simplified Chinese."""

from dataclasses import dataclass

import httpx

from app.services.cache import ttl_cache

SEARCH_URL = "https://api.bgm.tv/v0/search/subjects"
HEADERS = {"User-Agent": "YODO/0.1 (https://github.com/TheMoodyOldman/YODO)"}
ANIME = 2  # Bangumi subject type


class BangumiError(Exception):
    pass


@dataclass
class Subject:
    id: int
    name: str  # original (usually Japanese) title
    name_cn: str  # Chinese title, may be empty


@ttl_cache(24 * 3600)
async def search_anime(keyword: str, limit: int = 6) -> list[Subject]:
    try:
        async with httpx.AsyncClient(timeout=10, headers=HEADERS) as client:
            r = await client.post(f"{SEARCH_URL}?limit={limit}", json={"keyword": keyword, "filter": {"type": [ANIME]}})
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise BangumiError(str(e)) from e
    if r.status_code != 200:
        raise BangumiError(f"HTTP {r.status_code}")
    return [
        Subject(id=s["id"], name=s.get("name") or "", name_cn=s.get("name_cn") or "")
        for s in data.get("data") or [] if s.get("id")
    ]
