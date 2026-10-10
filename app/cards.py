"""Recap card data: what a user listened to, played and added in a month, a year, or ever."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlmodel import Session, col, func, select

from app.anime import tier_rank
from app.importers.youtube import TAIPEI
from app.models import Category, CollectionEntry, MonthlyPlays, MonthlyPlaytime, User, Work
from app.music import ArtistStat, top_artists, top_songs

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class Period:
    kind: str  # "month" | "year" | "all"
    key: str  # "2026-10" | "2026" | "all"

    @classmethod
    def parse(cls, kind: str, key: str) -> "Period | None":
        if kind == "month" and _MONTH_RE.match(key):
            return cls(kind, key)
        if kind == "year" and _YEAR_RE.match(key):
            return cls(kind, key)
        if kind == "all":
            return cls("all", "all")
        return None

    @property
    def label(self) -> str:
        if self.kind == "month":
            year, month = self.key.split("-")
            return f"{year} 年 {int(month)} 月"
        return f"{self.key} 年" if self.kind == "year" else "有史以來"

    @property
    def prefix(self) -> str:
        """Section-title prefix: 本月最常聽 / 今年最常聽 / 最常聽."""
        return {"month": "本月", "year": "今年", "all": ""}[self.kind]

    def contains(self, month: str) -> bool:
        if self.kind == "all":
            return True
        return month == self.key if self.kind == "month" else month.startswith(self.key + "-")

    def month_filter(self, column):
        """SQL condition on a "YYYY-MM" column, or None for all time."""
        if self.kind == "month":
            return column == self.key
        if self.kind == "year":
            return col(column).startswith(self.key + "-")
        return None


@dataclass
class RecapStats:
    period: Period
    artists: list[ArtistStat] = field(default_factory=list)
    songs: list[tuple[SimpleNamespace, Work]] = field(default_factory=list)  # .play_count = plays in the period
    total_plays: int = 0
    games: list[tuple[Work, int]] = field(default_factory=list)  # (game, minutes in the period)
    games_minutes: int = 0  # all games, not just the listed ones
    games_count: int = 0
    anime: list[tuple[CollectionEntry, Work]] = field(default_factory=list)
    anime_count: int = 0

    @property
    def label(self) -> str:
        return self.period.label

    def has(self, category: Category) -> bool:
        # Recap covers games, anime and music; other categories simply have no section.
        return bool({Category.music: self.songs, Category.game: self.games, Category.anime: self.anime}.get(category))

    @property
    def empty(self) -> bool:
        return not any(self.has(c) for c in Category)


@dataclass
class AvailablePeriods:
    months: list[str]  # newest first
    years: list[str]
    all_time: bool


def _visible(query):
    return query.where(col(CollectionEntry.hidden).is_(False), col(CollectionEntry.pending_review).is_(False))


def _month_of(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite hands back naive UTC datetimes
    return dt.astimezone(TAIPEI).strftime("%Y-%m")


def available_periods(session: Session, user: User) -> AvailablePeriods:
    months = set(session.exec(select(MonthlyPlays.month).where(MonthlyPlays.user_id == user.id).distinct()))
    months |= set(session.exec(select(MonthlyPlaytime.month).where(MonthlyPlaytime.user_id == user.id).distinct()))
    added = session.exec(
        select(CollectionEntry.added_at)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, Work.category == Category.anime)
    )
    months |= {_month_of(dt) for dt in added}
    # Steam games synced before monthly tracking existed still have lifetime playtime.
    lifetime_games = session.exec(
        select(CollectionEntry.id).where(CollectionEntry.user_id == user.id, col(CollectionEntry.playtime_minutes) > 0)
    ).first()
    return AvailablePeriods(
        months=sorted(months, reverse=True),
        years=sorted({m[:4] for m in months}, reverse=True),
        all_time=bool(months or lifetime_games),
    )


def recap_stats(session: Session, user: User, period: Period, top: int = 5) -> RecapStats:
    stats = RecapStats(period=period)

    # Music: plays in the period per song, deduped across sources like the profile rankings.
    query = (
        select(CollectionEntry, Work, func.sum(MonthlyPlays.plays))
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .join(MonthlyPlays, (col(MonthlyPlays.work_id) == Work.id) & (col(MonthlyPlays.user_id) == user.id))
        .where(CollectionEntry.user_id == user.id)
        .group_by(col(CollectionEntry.id), col(Work.id))
    )
    if (cond := period.month_filter(MonthlyPlays.month)) is not None:
        query = query.where(cond)
    # Rank by the period's plays, not lifetime: wrap entries instead of mutating ORM objects.
    plays = [(SimpleNamespace(play_count=n, added_at=e.added_at), w) for e, w, n in session.exec(_visible(query)).all()]
    if plays:
        stats.songs = top_songs(plays, top)
        stats.artists = top_artists(plays, 1)
        stats.total_plays = sum(e.play_count or 0 for e, _ in top_songs(plays, len(plays)))

    # Games: all time uses Steam's lifetime totals; months/years use tracked monthly playtime.
    if period.kind == "all":
        games = [
            (work, entry.playtime_minutes)
            for entry, work in session.exec(
                _visible(
                    select(CollectionEntry, Work)
                    .join(Work, col(Work.id) == CollectionEntry.work_id)
                    .where(CollectionEntry.user_id == user.id, col(CollectionEntry.playtime_minutes) > 0)
                )
            ).all()
        ]
    else:
        minutes = func.sum(col(MonthlyPlaytime.end_minutes) - col(MonthlyPlaytime.start_minutes))
        games = list(
            session.exec(
                _visible(
                    select(Work, minutes)
                    .join(MonthlyPlaytime, (col(MonthlyPlaytime.work_id) == Work.id) & (col(MonthlyPlaytime.user_id) == user.id))
                    .join(CollectionEntry, (col(CollectionEntry.work_id) == Work.id) & (col(CollectionEntry.user_id) == user.id))
                    .where(period.month_filter(MonthlyPlaytime.month))
                    .group_by(col(Work.id))
                    .having(minutes > 0)
                )
            ).all()
        )
    games.sort(key=lambda g: g[1], reverse=True)
    stats.games = games[:top]
    stats.games_minutes = sum(m for _, m in games)
    stats.games_count = len(games)

    # Anime: added to the collection in the period (we don't know watch dates).
    anime = [
        (entry, work)
        for entry, work in session.exec(
            _visible(
                select(CollectionEntry, Work)
                .join(Work, col(Work.id) == CollectionEntry.work_id)
                .where(CollectionEntry.user_id == user.id, Work.category == Category.anime)
            )
        ).all()
        if period.contains(_month_of(entry.added_at))
    ]
    anime.sort(key=lambda r: (tier_rank(r[0].tier), r[0].added_at), reverse=True)
    stats.anime_count = len(anime)
    stats.anime = anime[:8]  # a single-category card shows two rows
    return stats
