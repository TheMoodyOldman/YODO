"""Anime search that understands Chinese titles, and Traditional Chinese names for anime works.

AniList (the source of record) has no Chinese titles, so a Chinese query is first looked up on
Bangumi, and AniList is then searched with the Japanese titles Bangumi returns."""

import asyncio
import logging
import re
import unicodedata

from sqlmodel import Session, col, func, select

from app import zh
from app.models import Category, CollectionEntry, Work, utcnow
from app.services import anilist, bangumi

log = logging.getLogger(__name__)

BANGUMI_DELAY = 1.0  # seconds between background lookups
_PUNCT = re.compile(r"[\s\W_]+")


def _norm(title: str | None) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFKC", title or "").casefold())


def _chinese_name(subjects: list[bangumi.Subject], native: str | None) -> str | None:
    """The Chinese name of the subject whose original title is `native`, in Traditional Chinese."""
    if not native:
        return None
    for s in subjects:
        if s.name_cn and _norm(s.name) == _norm(native):
            return zh.to_traditional(s.name_cn)
    return None


async def search(query: str) -> list[anilist.Anime]:
    if not zh.is_chinese(query):
        return await anilist.search_anime(query)
    try:
        subjects = await bangumi.search_anime(zh.to_simplified(query))
    except bangumi.BangumiError:
        subjects = []
    names = list(dict.fromkeys(s.name for s in subjects[:3] if s.name))
    if not names:  # not on Bangumi: AniList synonyms occasionally include Chinese
        return await anilist.search_anime(query)

    found = await asyncio.gather(*(anilist.search_anime(n) for n in names), return_exceptions=True)
    errors = [f for f in found if isinstance(f, BaseException)]
    if len(errors) == len(found):
        raise errors[0] if isinstance(errors[0], anilist.AniListError) else anilist.AniListError(str(errors[0]))
    results: list[anilist.Anime] = []
    seen: set[int] = set()
    for i, hits in enumerate(found):
        if isinstance(hits, BaseException):
            continue
        for anime in hits[: 6 if i == 0 else 2]:  # the best Bangumi match gets the most room
            if anime.id in seen:
                continue
            seen.add(anime.id)
            anime.title = _chinese_name(subjects, anime.original_title) or anime.title
            results.append(anime)
    return results


async def chinese_title(native: str | None) -> str | None:
    """Traditional Chinese title for an anime by its Japanese title, or None. Never raises."""
    if not native:
        return None
    try:
        return _chinese_name(await bangumi.search_anime(native), native)
    except bangumi.BangumiError:
        return None


async def enrich_titles(session: Session, limit: int = 10) -> int:
    """Give collected anime their Chinese title, most-collected first. Returns works processed."""
    candidates = session.exec(
        select(Work)
        .join(CollectionEntry, col(CollectionEntry.work_id) == Work.id)
        .where(Work.category == Category.anime, col(Work.zh_checked_at).is_(None))
        .group_by(col(Work.id))
        .order_by(func.count(CollectionEntry.id).desc(), col(Work.id))
        .limit(limit)
    ).all()
    for work in candidates:
        try:
            subjects = await bangumi.search_anime(work.original_title) if work.original_title else []
        except bangumi.BangumiError:
            log.warning("Bangumi lookup failed for work %s", work.id)
            continue  # retried on a later pass
        name = _chinese_name(subjects, work.original_title)
        if name:
            work.title = name
        work.zh_checked_at = utcnow()
        session.add(work)
        session.commit()
        await asyncio.sleep(BANGUMI_DELAY)
    return len(candidates)
