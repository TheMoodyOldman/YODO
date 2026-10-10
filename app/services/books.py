"""Book search and details.

Google Books has the best Traditional Chinese data but its keyless quota is shared worldwide and
usually exhausted, so it is used only when GOOGLE_BOOKS_API_KEY is set. Otherwise Open Library
(no key) is used; it sometimes lists a work under its original-language title.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from app import zh
from app.config import settings

GOOGLE_URL = "https://www.googleapis.com/books/v1/volumes"
OL_URL = "https://openlibrary.org"
OL_COVER = "https://covers.openlibrary.org/b/id/{}-M.jpg"
GOOGLE, OPENLIBRARY = "googlebooks", "openlibrary"


class BooksError(Exception):
    pass


@dataclass
class Book:
    source: str  # GOOGLE | OPENLIBRARY
    external_id: str  # volume id / "OL123W"
    title: str
    authors: str
    cover_url: str | None
    year: int | None


def active_source() -> str:
    return GOOGLE if settings.google_books_api_key else OPENLIBRARY


async def _get(url: str, params: dict[str, Any]) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(url, params=params, headers={"User-Agent": "YODO/1.0 (interest profile)"})
    except httpx.HTTPError as e:
        raise BooksError(str(e)) from e
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise BooksError(f"HTTP {r.status_code}")
    return r.json()


# ---------- Google Books ----------

def _google_params(extra: dict[str, Any]) -> dict[str, Any]:
    return {**extra, "key": settings.google_books_api_key}


def _google_book(item: dict[str, Any]) -> Book | None:
    info = item.get("volumeInfo") or {}
    if not info.get("title"):
        return None
    links = info.get("imageLinks") or {}
    cover = links.get("thumbnail") or links.get("smallThumbnail")
    date = info.get("publishedDate") or ""
    return Book(
        source=GOOGLE,
        external_id=item["id"],
        title=info["title"] + (f"：{info['subtitle']}" if info.get("subtitle") else ""),
        authors="、".join(info.get("authors") or []),
        cover_url=cover.replace("http://", "https://").replace("&edge=curl", "") if cover else None,
        year=int(date[:4]) if date[:4].isdigit() else None,
    )


# ---------- Open Library ----------

_OL_FIELDS = "key,title,author_name,first_publish_year,cover_i"


def _ol_book(doc: dict[str, Any]) -> Book | None:
    if not doc.get("title") or not doc.get("key"):
        return None
    return Book(
        source=OPENLIBRARY,
        external_id=doc["key"].rsplit("/", 1)[-1],
        title=zh.to_traditional(doc["title"]),
        authors="、".join(zh.to_traditional(a) for a in doc.get("author_name") or []),
        cover_url=OL_COVER.format(doc["cover_i"]) if doc.get("cover_i") else None,
        year=doc.get("first_publish_year"),
    )


# ---------- public API ----------

async def search(query: str) -> list[Book]:
    if active_source() == GOOGLE:
        data = await _get(GOOGLE_URL, _google_params({"q": query, "maxResults": "12", "printType": "books"}))
        return [b for b in (_google_book(i) for i in (data or {}).get("items", [])) if b]
    # Open Library's Chinese records are mostly Simplified: search both scripts, original first.
    query = query.strip()
    found = await asyncio.gather(*(_ol_search(q) for q in dict.fromkeys([query, zh.to_simplified(query)])))
    results: list[Book] = []
    seen: set[str] = set()
    for book in (b for docs in found for b in (_ol_book(d) for d in docs) if b):
        if book.external_id not in seen:
            seen.add(book.external_id)
            results.append(book)
    return results[:12]


async def _ol_search(query: str) -> list[dict[str, Any]]:
    if len(query) < 3:  # Open Library rejects shorter queries; a quoted phrase is fine (三体 → "三体")
        query = f'"{query}"'
    try:
        data = await _get(f"{OL_URL}/search.json", {"q": query, "limit": "12", "fields": _OL_FIELDS})
    except BooksError as e:
        if "422" in str(e):
            return []
        raise
    return (data or {}).get("docs", [])


async def get_book(source: str, external_id: str) -> Book | None:
    if source == GOOGLE:
        data = await _get(f"{GOOGLE_URL}/{external_id}", _google_params({}))
        return _google_book(data) if data else None
    data = await _get(f"{OL_URL}/search.json", {"q": f"key:/works/{external_id}", "limit": "1", "fields": _OL_FIELDS})
    docs = (data or {}).get("docs") or []
    return _ol_book(docs[0]) if docs else None


async def get_details(source: str, external_id: str) -> dict[str, Any] | None:
    """Normalized: description, categories, page_count, publisher, link."""
    if source == GOOGLE:
        data = await _get(f"{GOOGLE_URL}/{external_id}", _google_params({}))
        info = (data or {}).get("volumeInfo")
        if not info:
            return None
        return {
            "description": info.get("description"),
            "categories": [c.split(" / ")[-1] for c in info.get("categories") or []],
            "page_count": info.get("pageCount"),
            "publisher": info.get("publisher"),
            "link": info.get("infoLink") or f"https://books.google.com/books?id={external_id}",
        }
    data = await _get(f"{OL_URL}/works/{external_id}.json", {})
    if not data:
        return None
    desc = data.get("description")
    return {
        "description": desc.get("value") if isinstance(desc, dict) else desc,
        "categories": (data.get("subjects") or [])[:8],
        "page_count": None,
        "publisher": None,
        "link": f"{OL_URL}/works/{external_id}",
    }
