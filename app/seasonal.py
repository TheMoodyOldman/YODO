"""本季新番快速勾選: tick the shows you're following this season, no episode tracking.

A pick is a normal anime CollectionEntry with `season` set ("2026-FALL"). Entries the quick pick
itself created carry `quick_pick`, so un-ticking one that was never rated or tagged removes
it instead of leaving an empty shell; un-ticking anything else only clears `season`. Past seasons
keep their label (「2026 秋季」). Friends see one merged feed item per person per season.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlmodel import Session, col, select

from app import anime_search
from app.activity import today
from app.config import settings
from app.importers.youtube import TAIPEI
from app.models import Activity, ActivityKind, Category, CollectionEntry, User, Work, utcnow
from app.services import anilist
from app.services.cache import ttl_cache

log = logging.getLogger(__name__)

SEASONS = ("WINTER", "SPRING", "SUMMER", "FALL")
SEASON_LABELS = {"WINTER": "冬季", "SPRING": "春季", "SUMMER": "夏季", "FALL": "秋季"}
START_MONTH = {"WINTER": 1, "SPRING": 4, "SUMMER": 7, "FALL": 10}
BANNER_WEEKS = 8  # the 探索 banner shows during a season's first 8 weeks
LIST_SIZE = 50
LIST_CACHE_SECONDS = 12 * 3600
FEED_TITLES = 2  # titles named in the feed sentence before 「等 N 部」


def local_today() -> date:
    return datetime.now(TAIPEI).date()


def key_for(day: date) -> str:
    season = SEASONS[(day.month - 1) // 3]
    return f"{day.year}-{season}"


def current_key() -> str:
    return key_for(local_today())


def parse(key: str | None) -> tuple[int, str] | None:
    try:
        year, season = (key or "").split("-")
        return (int(year), season) if season in SEASON_LABELS else None
    except ValueError:
        return None


def label(key: str | None) -> str:
    """「2026 秋季」 for "2026-FALL" (empty for anything unparseable)."""
    parsed = parse(key)
    return f"{parsed[0]} {SEASON_LABELS[parsed[1]]}" if parsed else ""


def season_start(key: str) -> date:
    year, season = parse(key)
    return date(year, START_MONTH[season], 1)


def banner_open(day: date | None = None) -> bool:
    day = day or local_today()
    return day - season_start(key_for(day)) < timedelta(weeks=BANNER_WEEKS)


def show_banner(user: User, day: date | None = None) -> bool:
    day = day or local_today()
    return banner_open(day) and user.season_banner_dismissed != key_for(day)


def dismiss_banner(session: Session, user: User) -> None:
    user.season_banner_dismissed = current_key()
    session.add(user)
    session.commit()


# ---------- this season's list (AniList, cached) ----------


@dataclass
class SeasonAnime:
    id: int
    title: str
    original_title: str | None
    cover_url: str | None
    year: int | None
    format: str | None


# AniList id -> Traditional Chinese title (None = looked up, none found). Filled in the background.
_zh_titles: dict[int, str | None] = {}
_warming: set[int] = set()


@ttl_cache(LIST_CACHE_SECONDS)
async def _fetch(key: str) -> list[anilist.Anime]:
    year, season = parse(key)
    return await anilist.season_anime(season, year, LIST_SIZE)


async def _warm_titles(items: list[anilist.Anime]) -> None:
    """Look up Chinese titles one by one (Bangumi is rate limited); the next page load shows them."""
    try:
        for a in items:
            if a.id in _zh_titles:
                continue
            _zh_titles[a.id] = await anime_search.chinese_title(a.original_title)
            await asyncio.sleep(anime_search.BANGUMI_DELAY)
    finally:
        _warming.difference_update(a.id for a in items)


async def season_list(session: Session, key: str) -> list[SeasonAnime]:
    """This season's TV/ONA shows by popularity, with Chinese titles where we know them.
    Raises anilist.AniListError when AniList is unreachable and nothing is cached."""
    try:
        items = await _fetch(key)
    except anilist.AniListError as e:
        if e.retry_after is None or e.retry_after > 5:
            raise
        await asyncio.sleep(e.retry_after)
        items = await _fetch(key)

    ids = [str(a.id) for a in items]
    known = {
        int(w.external_id): w.title
        for w in session.exec(select(Work).where(Work.source == "anilist", col(Work.external_id).in_(ids)))
        if w.zh_checked_at is not None
    }
    missing = [a for a in items if a.id not in known and a.id not in _zh_titles and a.id not in _warming]
    if missing and settings.background_jobs:
        _warming.update(a.id for a in missing)
        asyncio.get_running_loop().create_task(_warm_titles(missing))

    return [
        SeasonAnime(a.id, known.get(a.id) or _zh_titles.get(a.id) or a.title, a.original_title, a.cover_url, a.year, a.format)
        for a in items
    ]


def _work_for(session: Session, a: SeasonAnime) -> Work:
    """The Work for a listed show, created if new. Never overwrites a title we already have."""
    work = session.exec(select(Work).where(Work.source == "anilist", Work.external_id == str(a.id))).first()
    if work is not None:
        return work
    work = Work(
        category=Category.anime, source="anilist", external_id=str(a.id), title=a.title,
        original_title=a.original_title, cover_url=a.cover_url, year=a.year,
    )
    if a.id in _zh_titles:  # looked up already; otherwise the background title pass does it
        work.zh_checked_at = utcnow()
    session.add(work)
    session.flush()
    return work


# ---------- reading and saving picks ----------


def picks(session: Session, user_id: int, key: str, *, public_only: bool = False) -> list[tuple[CollectionEntry, Work]]:
    """A user's picks for a season, in the order they were added. public_only drops hidden and
    awaiting-review entries (what other people may see)."""
    query = (
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user_id, CollectionEntry.season == key, Work.category == Category.anime)
        .order_by(col(CollectionEntry.added_at), col(CollectionEntry.id))
    )
    if public_only:
        query = query.where(col(CollectionEntry.hidden).is_(False), col(CollectionEntry.pending_review).is_(False))
    return list(session.exec(query).all())


def is_empty_shell(entry: CollectionEntry) -> bool:
    """Added by the quick pick and never rated, tagged or otherwise filled in."""
    return bool(entry.quick_pick) and not (entry.tier or entry.tag or entry.rating or entry.status or entry.play_count)


@dataclass
class SaveResult:
    added: int  # new to the collection
    marked: int  # already collected, now marked for this season
    removed: int  # quick-pick shells taken out of the collection
    unmarked: int  # still collected, no longer marked for this season

    @property
    def total_new(self) -> int:
        return self.added + self.marked


def save(session: Session, user: User, key: str, chosen: list[SeasonAnime]) -> SaveResult:
    """Make the user's picks for `key` exactly `chosen`. Commits."""
    result = SaveResult(0, 0, 0, 0)
    chosen_work_ids: set[int] = set()
    for a in chosen:
        work = _work_for(session, a)
        chosen_work_ids.add(work.id)
        entry = session.exec(
            select(CollectionEntry).where(CollectionEntry.user_id == user.id, CollectionEntry.work_id == work.id)
        ).first()
        if entry is None:
            session.add(CollectionEntry(user_id=user.id, work_id=work.id, season=key, quick_pick=True))
            result.added += 1
        elif entry.season != key:
            entry.season = key
            session.add(entry)
            result.marked += 1

    for entry, _ in picks(session, user.id, key):
        if entry.work_id in chosen_work_ids:
            continue
        if is_empty_shell(entry):
            session.delete(entry)
            result.removed += 1
        else:
            entry.season = None
            session.add(entry)
            result.unmarked += 1

    if result.total_new:
        _record_activity(session, user.id, key)
    session.commit()
    return result


def _record_activity(session: Session, user_id: int, key: str) -> None:
    """One feed item per person per season, bumped to the top when they pick more."""
    act = session.exec(
        select(Activity).where(Activity.user_id == user_id, Activity.kind == ActivityKind.season_picks, Activity.note == key)
    ).first()
    if act is None:
        act = Activity(user_id=user_id, kind=ActivityKind.season_picks, work_id=None, day=today(), note=key)
    act.day = today()
    act.updated_at = utcnow()
    session.add(act)


def feed_sentence(key: str, titles: list[str], total: int) -> str:
    """「這季在追《A》、《B》等 5 部新番」 (「2026 夏季在追…」 once that season is over)."""
    when = "這季" if key == current_key() else f"{label(key)}"
    named = "、".join(f"《{t}》" for t in titles[:FEED_TITLES])
    if total <= FEED_TITLES:
        return f"{when}在追{named}"
    return f"{when}在追{named}等 {total} 部新番"
