"""Public facts about a work for its detail page, from the source it came from. Always best-effort:
any lookup failure just yields a sparser page."""

import html
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from app.models import Work
from app.services import anilist, books, lastfm, steam, tmdb
from app.services.cache import ttl_cache

SEASONS = {"WINTER": "冬", "SPRING": "春", "SUMMER": "夏", "FALL": "秋"}
_TAG_RE = re.compile(r"<[^>]+>")
_LASTFM_READ_MORE = re.compile(r"\s*Read more on Last\.fm.*$", re.S)


@dataclass
class WorkInfo:
    description: str | None = None
    facts: list[tuple[str, str]] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    link: tuple[str, str] | None = None  # (url, label)
    color: str | None = None  # accent color for the page backdrop, e.g. "#e4a15d"
    image: str | None = None  # higher-resolution cover, if the source has one


def _clean(text: str | None, limit: int = 600) -> str | None:
    if not text:
        return None
    text = html.unescape(_TAG_RE.sub("", text)).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


@ttl_cache(6 * 3600)
async def _steam(appid: str) -> WorkInfo:
    info = WorkInfo(link=(f"https://store.steampowered.com/app/{appid}", "Steam 商店頁"))
    data = await steam.get_app_details(appid)
    if not data:
        return info
    info.description = _clean(data.get("short_description"))
    if data.get("developers"):
        info.facts.append(("開發", "、".join(data["developers"])))
    if data.get("publishers"):
        info.facts.append(("發行", "、".join(data["publishers"])))
    if (data.get("release_date") or {}).get("date"):
        info.facts.append(("上市", data["release_date"]["date"]))
    if (data.get("metacritic") or {}).get("score"):
        info.facts.append(("Metacritic", str(data["metacritic"]["score"])))
    info.genres = [g["description"] for g in data.get("genres") or [] if g.get("description")]
    return info


@ttl_cache(6 * 3600)
async def _anilist(anilist_id: str) -> WorkInfo:
    info = WorkInfo(link=(f"https://anilist.co/anime/{anilist_id}", "AniList"))
    try:
        data = await anilist.get_details(int(anilist_id))
    except anilist.AniListError:
        return info
    if not data:
        return info
    info.description = _clean(data.get("description"))
    if data.get("format"):
        info.facts.append(("類型", anilist.FORMAT_LABELS.get(data["format"], data["format"])))
    if data.get("episodes"):
        info.facts.append(("集數", f"{data['episodes']} 集"))
    if data.get("seasonYear"):
        season = SEASONS.get(data.get("season") or "", "")
        info.facts.append(("播出", f"{data['seasonYear']} {season}".strip()))
    studios = [s["name"] for s in (data.get("studios") or {}).get("nodes") or []]
    if studios:
        info.facts.append(("動畫公司", "、".join(studios)))
    if data.get("averageScore"):
        info.facts.append(("AniList 評分", f"{data['averageScore']}%"))
    info.genres = data.get("genres") or []
    cover = data.get("coverImage") or {}
    info.color, info.image = cover.get("color"), cover.get("extraLarge")
    return info


@ttl_cache(6 * 3600)
async def _music(source: str, external_id: str, artist: str, title: str) -> WorkInfo:
    if source == "youtube":
        link = (f"https://music.youtube.com/watch?v={external_id}", "在 YouTube Music 播放")
    else:
        link = (f"https://www.last.fm/music/{quote(artist)}/_/{quote(title)}", "Last.fm")
    info = WorkInfo(link=link)
    track = await lastfm.get_track_info(artist, title)
    if not track:
        return info  # music metadata is optional
    album = (track.get("album") or {}).get("title")
    if album:
        info.facts.append(("專輯", album))
    if track.get("listeners"):
        info.facts.append(("Last.fm 聽眾", f"{int(track['listeners']):,}"))
    if track.get("playcount"):
        info.facts.append(("全球播放", f"{int(track['playcount']):,}"))
    tags = ((track.get("toptags") or {}).get("tag")) or []
    info.genres = [t["name"] for t in (tags if isinstance(tags, list) else [tags])][:5]
    info.description = _clean(_LASTFM_READ_MORE.sub("", (track.get("wiki") or {}).get("summary") or ""))
    return info


@ttl_cache(6 * 3600)
async def _tmdb(external_id: str) -> WorkInfo:
    kind, _, tmdb_id = external_id.partition(":")
    info = WorkInfo(link=(f"https://www.themoviedb.org/{kind}/{tmdb_id}", "TMDB"))
    try:
        data = await tmdb.get_details(external_id)
    except tmdb.TmdbError:
        return info
    if not data:
        return info
    info.description = _clean(data.get("overview"))
    info.facts.append(("類型", "電影" if kind == "movie" else "影集"))
    date = data.get("release_date") or data.get("first_air_date")
    if date:
        info.facts.append(("上映" if kind == "movie" else "首播", date))
    if data.get("runtime"):
        info.facts.append(("片長", f"{data['runtime']} 分鐘"))
    if data.get("number_of_seasons"):
        info.facts.append(("季數", f"{data['number_of_seasons']} 季 · {data.get('number_of_episodes') or '?'} 集"))
    crew = (data.get("credits") or {}).get("crew") or []
    directors = [c["name"] for c in crew if c.get("job") == "Director"][:2]
    creators = [c["name"] for c in data.get("created_by") or []][:2]
    if directors or creators:
        info.facts.append(("導演" if directors else "主創", "、".join(directors or creators)))
    cast = [c["name"] for c in ((data.get("credits") or {}).get("cast") or [])[:3]]
    if cast:
        info.facts.append(("主演", "、".join(cast)))
    if data.get("vote_average"):
        info.facts.append(("TMDB 評分", f"{data['vote_average']:.1f} / 10"))
    info.genres = [g["name"] for g in data.get("genres") or [] if g.get("name")]
    return info


@ttl_cache(6 * 3600)
async def _book(source: str, external_id: str) -> WorkInfo:
    info = WorkInfo()
    try:
        data = await books.get_details(source, external_id)
    except books.BooksError:
        return info
    if not data:
        return info
    info.link = (data["link"], "Google Books" if source == books.GOOGLE else "Open Library")
    info.description = _clean(data.get("description"))
    if data.get("publisher"):
        info.facts.append(("出版", data["publisher"]))
    if data.get("page_count"):
        info.facts.append(("頁數", f"{data['page_count']} 頁"))
    info.genres = data.get("categories") or []
    return info


async def get_work_info(work: Work) -> WorkInfo:
    try:
        if work.source == "steam":
            return await _steam(work.external_id)
        if work.source == "anilist":
            return await _anilist(work.external_id)
        if work.source in ("youtube", "lastfm"):
            return await _music(work.source, work.external_id, work.creator or "", work.title)
        if work.source == "tmdb":
            return await _tmdb(work.external_id)
        if work.source in (books.GOOGLE, books.OPENLIBRARY):
            info = await _book(work.source, work.external_id)
            if work.creator and not any(label == "作者" for label, _ in info.facts):
                info.facts.insert(0, ("作者", work.creator))
            return info
    except Exception:  # never let a metadata hiccup break the page
        pass
    return WorkInfo()
