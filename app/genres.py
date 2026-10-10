"""Style tags per work and per-user style profiles.

Sources: Steam store genres (Traditional Chinese), AniList genres (translated), Last.fm song tags
(falling back to the artist's tags when a song has none). Lookups run in a slow background loop,
most-collected works first, so imports stay fast and rate limits are respected.
"""

import asyncio
import logging
import math
from collections import defaultdict
from dataclasses import dataclass

from sqlmodel import Session, col, func, select

from app.models import Category, CollectionEntry, User, Work, WorkGenre, utcnow
from app.services import anilist, books, lastfm, steam, tmdb

log = logging.getLogger(__name__)

ANILIST_GENRES = {
    "Action": "動作", "Adventure": "冒險", "Comedy": "喜劇", "Drama": "劇情", "Ecchi": "賣肉",
    "Fantasy": "奇幻", "Horror": "恐怖", "Mahou Shoujo": "魔法少女", "Mecha": "機戰", "Music": "音樂",
    "Mystery": "懸疑", "Psychological": "心理", "Romance": "戀愛", "Sci-Fi": "科幻",
    "Slice of Life": "日常", "Sports": "運動", "Supernatural": "超自然", "Thriller": "驚悚",
}
# Last.fm tags that describe listeners, not music.
JUNK_TAGS = {
    "seen live", "favorites", "favourite", "favorite", "favourites", "albums i own", "my favorites",
    "love", "awesome", "beautiful", "all", "under 2000 listeners", "spotify", "owned", "amazing",
    "cool", "good", "best", "fav", "favs", "loved", "check out", "want to see live",
}
MAX_MUSIC_TAGS = 5
MIN_TAG_STRENGTH = 10
DELAY = {"steam": 1.5, "anilist": 0.8, "lastfm": 0.3, "tmdb": 0.3, "books": 1.0}  # seconds between requests
MAX_BOOK_TAGS = 6


def _clean_music_tags(tags: list[tuple[str, int]], artist: str) -> list[tuple[str, float]]:
    out, seen = [], set()
    for name, strength in tags:
        tag = name.strip().lower()
        if strength < MIN_TAG_STRENGTH or tag in JUNK_TAGS or tag == artist.casefold() or tag in seen:
            continue
        seen.add(tag)
        out.append((tag, strength / 100))
        if len(out) == MAX_MUSIC_TAGS:
            break
    return out


def _save(session: Session, works: list[Work], genres: list[tuple[str, float]]) -> None:
    for work in works:
        for genre, weight in genres:
            exists = session.exec(select(WorkGenre).where(WorkGenre.work_id == work.id, WorkGenre.genre == genre)).first()
            if exists is None:
                session.add(WorkGenre(work_id=work.id, genre=genre, weight=weight))
        work.genres_checked_at = utcnow()
        session.add(work)


async def enrich_batch(session: Session, limit: int = 20) -> int:
    """Look up genres for up to `limit` works nobody has checked yet, most-collected first.
    Returns how many works were processed."""
    popularity = func.count(CollectionEntry.id)
    candidates = session.exec(
        select(Work)
        .join(CollectionEntry, col(CollectionEntry.work_id) == Work.id)
        .where(col(Work.genres_checked_at).is_(None))
        .group_by(col(Work.id))
        .order_by(popularity.desc(), col(Work.id))
        .limit(limit)
    ).all()
    done = 0
    artist_tags: dict[str, list[tuple[str, float]]] = {}  # fallback cache for this pass
    for work in candidates:
        try:
            if work.source == "steam":
                data = await steam.get_app_details(work.external_id)
                names = [g["description"] for g in (data or {}).get("genres") or [] if g.get("description")]
                _save(session, [work], [(n, 1.0) for n in names])
                await asyncio.sleep(DELAY["steam"])
            elif work.source == "anilist":
                names = await anilist.get_genres(int(work.external_id)) or []
                _save(session, [work], [(ANILIST_GENRES.get(n, n), 1.0) for n in names if n != "Hentai"])
                await asyncio.sleep(DELAY["anilist"])
            elif work.category == Category.music and work.creator:
                # Song tags first (title disambiguates same-name artists); artist tags only as a fallback.
                tags = _clean_music_tags(await lastfm.get_track_tags(work.creator, work.title) or [], work.creator)
                await asyncio.sleep(DELAY["lastfm"])
                if not tags:
                    key = work.creator.casefold()
                    if key not in artist_tags:
                        artist_tags[key] = _clean_music_tags(await lastfm.get_artist_tags(work.creator) or [], work.creator)
                        await asyncio.sleep(DELAY["lastfm"])
                    tags = artist_tags[key]
                _save(session, [work], tags)
            elif work.source == "tmdb":
                data = await tmdb.get_details(work.external_id)
                _save(session, [work], [(g["name"], 1.0) for g in (data or {}).get("genres") or [] if g.get("name")])
                await asyncio.sleep(DELAY["tmdb"])
            elif work.source in (books.GOOGLE, books.OPENLIBRARY):
                data = await books.get_details(work.source, work.external_id)
                names = [c for c in (data or {}).get("categories") or [] if ":" not in c][:MAX_BOOK_TAGS]
                _save(session, [work], [(n if not n.isascii() else n.lower(), 1.0) for n in names])
                await asyncio.sleep(DELAY["books"])
            else:
                _save(session, [work], [])
            session.commit()
            done += 1
        except Exception:  # one bad lookup mustn't stop the rest; it is retried on a later pass
            session.rollback()
            log.exception("genre lookup failed for work %s", work.id)
    return done


async def background_loop(session_factory, interval: float = 30) -> None:
    while True:
        try:
            with session_factory() as session:
                processed = await enrich_batch(session)
        except Exception:
            log.exception("genre enrichment pass failed")
            processed = 0
        await asyncio.sleep(1 if processed else interval)


# ---------- per-user style profile ----------

TOP_GENRES = 8


@dataclass
class GenreShare:
    genre: str
    pct: int


@dataclass
class StyleProfile:
    category: Category
    genres: list[GenreShare]
    analysed: int  # entries with at least one genre
    total: int


def _investment(entry: CollectionEntry, category: Category) -> float:
    if category == Category.game:
        return math.log1p((entry.playtime_minutes or 0) / 60)
    if category == Category.music:
        return math.log1p(entry.play_count or 0)
    from app.matching import TIER_WEIGHT

    return TIER_WEIGHT.get(entry.tier or "", 1.0)


def style_profiles(session: Session, rows: list[tuple[CollectionEntry, Work]]) -> dict[Category, StyleProfile]:
    """Genre mix per category, weighted by how invested the user is in each work."""
    work_ids = [w.id for _, w in rows]
    genres: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for i in range(0, len(work_ids), 500):
        for g in session.exec(select(WorkGenre).where(col(WorkGenre.work_id).in_(work_ids[i : i + 500]))):
            genres[g.work_id].append((g.genre, g.weight))

    by_cat: dict[Category, list[tuple[CollectionEntry, Work]]] = defaultdict(list)
    for e, w in rows:
        by_cat[w.category].append((e, w))
    out = {}
    for category, cat_rows in by_cat.items():
        top = max((_investment(e, category) for e, _ in cat_rows), default=0) or 1
        scores: dict[str, float] = defaultdict(float)
        analysed = 0
        for e, w in cat_rows:
            if not genres.get(w.id):
                continue
            analysed += 1
            share = 0.3 + _investment(e, category) / top  # everything counts a little, favourites a lot
            for genre, weight in genres[w.id]:
                scores[genre] += share * weight
        total = sum(scores.values()) or 1
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:TOP_GENRES]
        out[category] = StyleProfile(
            category, [GenreShare(g, max(1, round(100 * v / total))) for g, v in ranked], analysed, len(cat_rows)
        )
    return out


def user_style(session: Session, user: User, categories: set[Category]) -> dict[Category, StyleProfile]:
    rows = session.exec(
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(
            CollectionEntry.user_id == user.id,
            col(CollectionEntry.hidden).is_(False),
            col(CollectionEntry.pending_review).is_(False),
        )
    ).all()
    return style_profiles(session, [(e, w) for e, w in rows if w.category in categories])
