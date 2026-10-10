"""Apple iTunes Search API: free 30-second song previews, no key (about 20 requests/minute)."""

import re
import unicodedata

import httpx

SEARCH_URL = "https://itunes.apple.com/search"
_NOISE = re.compile(r"[\(\[（【].*?[\)\]）】]|official|music video|mv|lyric(s)?|audio|ver(sion)?\.?", re.I)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _NOISE.sub(" ", text)
    return re.sub(r"[\W_]+", "", text)


def _matches(result: dict, artist: str, title: str) -> bool:
    want_title, want_artist = _norm(title), _norm(artist)
    got_title, got_artist = _norm(result.get("trackName", "")), _norm(result.get("artistName", ""))
    title_ok = bool(want_title) and (want_title in got_title or got_title in want_title)
    artist_ok = not want_artist or want_artist in got_artist or got_artist in want_artist
    return title_ok and artist_ok


class ItunesUnavailable(Exception):
    """Rate-limited or unreachable: try again later instead of caching "no preview"."""


# The JP store keeps original artist names (サカナクション, ASIAN KUNG-FU GENERATION); the TW store
# translates them (魚韻, 亞細亞功夫世代) and romanizes titles, so it is tried last.
COUNTRIES = ("JP", "US", "TW")


async def find_preview(artist: str, title: str) -> str | None:
    """Preview URL for the best-matching song, or None if no store has it."""
    async with httpx.AsyncClient(timeout=10) as client:
        for country in COUNTRIES:
            params = {"term": f"{artist} {title}".strip(), "entity": "song", "limit": "10", "country": country}
            try:
                r = await client.get(SEARCH_URL, params=params)
            except httpx.HTTPError as e:
                raise ItunesUnavailable(str(e)) from e
            if r.status_code in (403, 429) or r.status_code >= 500:
                raise ItunesUnavailable(f"HTTP {r.status_code}")
            try:
                results = r.json().get("results", [])
            except ValueError:
                continue
            for result in results:
                if result.get("previewUrl") and _matches(result, artist, title):
                    return result["previewUrl"]
    return None
