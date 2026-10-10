"""Netflix viewing history (Account → Profile → Viewing activity → Download all): a CSV of
"Title,Date" rows. Episodes ("Show: Season 1: Chapter One") are grouped under the show; each
show or movie is matched to TMDB and imported as a film/TV work awaiting review. Japanese
animation is matched on to AniList and filed under 動畫 instead.
"""

import asyncio
import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlmodel import Session, col, select

from app import anime_search, zh
from app.models import Category, CollectionEntry, MonthlyPlays, User, Work, utcnow
from app.services import anilist, tmdb
from app.works import upsert_work

WATCHED = (Category.film, Category.anime)  # categories a Netflix import fills
MAX_TITLES = 150  # TMDB lookups per import, most-watched first
ANILIST_MAX_WAIT = 65  # seconds
_SEPARATOR = re.compile(r"\s*[:：]\s*")
_ASCII_SEPARATOR = re.compile(r"\s*:\s*")
_EPISODE_HINT = re.compile(
    r"season|series|episode|part\s*\d|chapter|volume|limited|collection|book\s*\d|第.{1,6}[季集部章]|[季集]\s*\d|\d\s*[季集]",
    re.I,
)
_FILM_MARKS = re.compile(r"劇場版|[「」『』]")
DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y", "%d.%m.%y", "%d.%m.%Y")


class NetflixFormatError(Exception):
    pass


@dataclass
class ViewedTitle:
    name: str
    is_series: bool
    views: int = 0
    months: Counter[str] = field(default_factory=Counter)


def split_title(raw: str, series_prefixes: frozenset[str] = frozenset()) -> tuple[str, bool]:
    """("Stranger Things", True) for an episode, (whole title, False) for a movie. A "Show: Episode"
    title without an episode number counts as an episode when the show name recurs in the file."""
    parts = [p for p in _SEPARATOR.split(raw.strip()) if p]
    if len(parts) >= 3 or (len(parts) == 2 and (_EPISODE_HINT.search(parts[1]) or parts[0].casefold() in series_prefixes)):
        return parts[0], True
    return raw.strip(), False


def _recurring_prefixes(raw_titles: list[str]) -> frozenset[str]:
    """Show names that start two or more distinct "Show: Episode" titles (坂本日常: 京 / 坂本日常: 三試)."""
    # Only Netflix's own ": " separator: a full-width "：" belongs to the title (比爾·伯爾：紙老虎).
    seen: dict[str, set[str]] = {}
    for raw in raw_titles:
        parts = [p for p in _ASCII_SEPARATOR.split(raw.strip()) if p]
        if len(parts) == 2:
            seen.setdefault(parts[0].casefold(), set()).add(parts[1])
    return frozenset(name for name, episodes in seen.items() if len(episodes) >= 2)


def _pick_date_format(values: list[str]) -> str:
    """The format that parses every row without producing future dates (resolves M/D vs D/M)."""
    today = date.today()
    for fmt in DATE_FORMATS:
        try:
            if all(datetime.strptime(v, fmt).date() <= today for v in values):
                return fmt
        except ValueError:
            continue
    raise NetflixFormatError("unknown date format")


def parse_viewing_history(data: bytes) -> list[ViewedTitle]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise NetflixFormatError("not UTF-8") from e
    rows = [r for r in csv.reader(io.StringIO(text)) if len(r) >= 2 and r[0].strip()]
    if len(rows) < 2:
        raise NetflixFormatError("no rows")
    body = rows[1:]  # first row is the header ("Title,Date" / localized)
    fmt = _pick_date_format([r[1].strip() for r in body])
    series_prefixes = _recurring_prefixes([r[0] for r in body])
    titles: dict[tuple[str, bool], ViewedTitle] = {}
    for raw, when in ((r[0], r[1].strip()) for r in body):
        name, is_series = split_title(raw, series_prefixes)
        item = titles.setdefault((name.casefold(), is_series), ViewedTitle(name, is_series))
        item.views += 1
        item.months[datetime.strptime(when, fmt).strftime("%Y-%m")] += 1
    return sorted(titles.values(), key=lambda t: t.views, reverse=True)


@dataclass
class NetflixResult:
    matched: int
    unmatched: list[str]
    new: int
    skipped: int  # beyond MAX_TITLES
    new_anime: int = 0  # of `new`, filed under 動畫


@dataclass
class Match:
    category: Category
    source: str
    external_id: str
    title: str
    original_title: str | None
    cover_url: str | None
    year: int | None
    chinese_title: bool = False  # title is already the Taiwanese name


async def _search_anilist(query: str) -> list[anilist.Anime]:
    """AniList search that waits out one rate-limit window (an import can burst past ~30/min)."""
    try:
        return await anilist.search_anime(query)
    except anilist.AniListError as e:
        if e.retry_after is None or e.retry_after > ANILIST_MAX_WAIT:
            raise
        await asyncio.sleep(e.retry_after + 1)
        return await anilist.search_anime(query)


async def _match_anime(found: tmdb.Title, sem: asyncio.Semaphore) -> Match | None:
    """The AniList entry for a TMDB anime, by its Japanese title. None if AniList has no match."""
    native = found.original_title or found.title
    try:
        async with sem:
            hits = await _search_anilist(native)
            if not hits and _FILM_MARKS.search(native):  # 劇場版「オーバーロード」聖王国編 → オーバーロード 聖王国編
                hits = await _search_anilist(_FILM_MARKS.sub(" ", native).strip())
    except anilist.AniListError:
        return None
    if not hits:
        return None
    hit = next((h for h in hits if anime_search.same_title(h.original_title, native)), hits[0])
    # Netflix Taiwan's name (from TMDB zh-TW) beats Bangumi's, which is often the mainland one.
    title = found.title if zh.is_chinese(found.title) else await anime_search.chinese_title(hit.original_title)
    return Match(Category.anime, "anilist", str(hit.id), title or hit.title, hit.original_title,
                 hit.cover_url, hit.year, chinese_title=bool(title))


async def _match(title: ViewedTitle, sem: asyncio.Semaphore, anime_sem: asyncio.Semaphore) -> Match | None:
    async with sem:
        results = await tmdb.search(title.name, prefer="tv" if title.is_series else "movie")
        show, _ = split_title(title.name, frozenset([_SEPARATOR.split(title.name, 1)[0].casefold()]))
        if not results and show != title.name:  # a lone episode, e.g. "Show: Some Episode" watched once
            results = await tmdb.search(show, prefer="tv")
    if not results:
        return None
    found = results[0]
    if found.is_anime and (anime := await _match_anime(found, anime_sem)):
        return anime
    return Match(Category.film, "tmdb", found.external_id, found.title, found.original_title, found.cover_url, found.year)


async def import_netflix(session: Session, user: User, titles: list[ViewedTitle]) -> NetflixResult:
    """Match titles to TMDB and merge them in. New works await review; monthly counts take the
    max of old and new, so re-importing a newer export never double-counts."""
    batch = titles[:MAX_TITLES]
    sem, anime_sem = asyncio.Semaphore(5), asyncio.Semaphore(2)  # AniList allows ~90 requests/min
    matches = await asyncio.gather(*(_match(t, sem, anime_sem) for t in batch), return_exceptions=True)
    if matches and all(isinstance(m, tmdb.TmdbError) for m in matches):
        raise matches[0]

    existing_plays = {
        (row.work_id, row.month): row
        for row in session.exec(select(MonthlyPlays).where(MonthlyPlays.user_id == user.id))
    }
    matched, unmatched, new, new_anime = 0, [], 0, 0
    for viewed, found in zip(batch, matches):
        if isinstance(found, BaseException) or found is None:
            unmatched.append(viewed.name)
            continue
        matched += 1
        work = upsert_work(
            session, category=found.category, source=found.source, external_id=found.external_id, title=found.title,
            original_title=found.original_title, cover_url=found.cover_url, year=found.year,
        )
        if found.chinese_title:
            work.zh_checked_at = utcnow()  # keep the Taiwanese name; skip the Bangumi lookup
        entry = session.exec(
            select(CollectionEntry).where(CollectionEntry.user_id == user.id, CollectionEntry.work_id == work.id)
        ).first()
        if entry is None:
            entry = CollectionEntry(user_id=user.id, work_id=work.id, pending_review=True)
            new += 1
            new_anime += found.category == Category.anime
        for month, count in viewed.months.items():
            row = existing_plays.get((work.id, month))
            if row is None:
                row = existing_plays[(work.id, month)] = MonthlyPlays(user_id=user.id, work_id=work.id, month=month, plays=count)
            row.plays = max(row.plays, count)
            session.add(row)
        session.flush()
        entry.play_count = sum(r.plays for (wid, _), r in existing_plays.items() if wid == work.id)
        session.add(entry)
    session.commit()
    return NetflixResult(matched, unmatched, new, max(0, len(titles) - MAX_TITLES), new_anime)


def watched_works(session: Session, user: User) -> bool:
    """Whether the user has any viewing counts from a Netflix import."""
    return session.exec(
        select(CollectionEntry.id)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, col(Work.category).in_(WATCHED), col(CollectionEntry.play_count) > 0)
    ).first() is not None
