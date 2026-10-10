"""Netflix viewing history (Account → Profile → Viewing activity → Download all): a CSV of
"Title,Date" rows. Episodes ("Show: Season 1: Chapter One") are grouped under the show; each
show or movie is matched to TMDB and imported as a film/TV work awaiting review.
"""

import asyncio
import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlmodel import Session, col, select

from app.models import Category, CollectionEntry, MonthlyPlays, User, Work
from app.services import tmdb
from app.works import upsert_work

MAX_TITLES = 150  # TMDB lookups per import, most-watched first
_SEPARATOR = re.compile(r"\s*[:：]\s*")
_EPISODE_HINT = re.compile(
    r"season|series|episode|part\s*\d|chapter|volume|limited|collection|book\s*\d|第.{1,6}[季集部章]|[季集]\s*\d|\d\s*[季集]",
    re.I,
)
DATE_FORMATS = ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y", "%d.%m.%y", "%d.%m.%Y")


class NetflixFormatError(Exception):
    pass


@dataclass
class ViewedTitle:
    name: str
    is_series: bool
    views: int = 0
    months: Counter[str] = field(default_factory=Counter)


def split_title(raw: str) -> tuple[str, bool]:
    """("Stranger Things", True) for an episode, (whole title, False) for a movie."""
    parts = [p for p in _SEPARATOR.split(raw.strip()) if p]
    if len(parts) >= 3 or (len(parts) == 2 and _EPISODE_HINT.search(parts[1])):
        return parts[0], True
    return raw.strip(), False


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
    titles: dict[tuple[str, bool], ViewedTitle] = {}
    for raw, when in ((r[0], r[1].strip()) for r in body):
        name, is_series = split_title(raw)
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


async def _match(title: ViewedTitle, sem: asyncio.Semaphore) -> tmdb.Title | None:
    async with sem:
        results = await tmdb.search(title.name, prefer="tv" if title.is_series else "movie")
    return results[0] if results else None


async def import_netflix(session: Session, user: User, titles: list[ViewedTitle]) -> NetflixResult:
    """Match titles to TMDB and merge them in. New works await review; monthly counts take the
    max of old and new, so re-importing a newer export never double-counts."""
    batch = titles[:MAX_TITLES]
    sem = asyncio.Semaphore(5)
    matches = await asyncio.gather(*(_match(t, sem) for t in batch), return_exceptions=True)
    if matches and all(isinstance(m, tmdb.TmdbError) for m in matches):
        raise matches[0]

    existing_plays = {
        (row.work_id, row.month): row
        for row in session.exec(select(MonthlyPlays).where(MonthlyPlays.user_id == user.id))
    }
    matched, unmatched, new = 0, [], 0
    for viewed, found in zip(batch, matches):
        if isinstance(found, BaseException) or found is None:
            unmatched.append(viewed.name)
            continue
        matched += 1
        work = upsert_work(
            session, category=Category.film, source="tmdb", external_id=found.external_id, title=found.title,
            original_title=found.original_title, cover_url=found.cover_url, year=found.year,
        )
        entry = session.exec(
            select(CollectionEntry).where(CollectionEntry.user_id == user.id, CollectionEntry.work_id == work.id)
        ).first()
        if entry is None:
            entry = CollectionEntry(user_id=user.id, work_id=work.id, pending_review=True)
            new += 1
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
    return NetflixResult(matched, unmatched, new, max(0, len(titles) - MAX_TITLES))


def watched_works(session: Session, user: User) -> bool:
    """Whether the user has any viewing counts from a Netflix import."""
    return session.exec(
        select(CollectionEntry.id)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, Work.category == Category.film, col(CollectionEntry.play_count) > 0)
    ).first() is not None
