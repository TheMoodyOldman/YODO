from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import Session, col, select

from app.importers.youtube import TAIPEI
from app.activity import record
from app.models import ActivityKind, Category, CollectionEntry, MonthlyPlaytime, User, Work
from app.music import LASTFM, ImportResult, Song, import_music
from app.services import lastfm, steam
from app.works import upsert_work

# Skip games that were only launched briefly, so the library isn't flooded.
MIN_PLAYTIME_MINUTES = 60
# First Last.fm sync covers the current month plus this many previous months.
LASTFM_FIRST_SYNC_MONTHS = 6


def _record_playtime(
    session: Session,
    user: User,
    work_id: int,
    month: str,
    row: MonthlyPlaytime | None,
    previous_total: int | None,
    game: steam.OwnedGame,
) -> None:
    """Track this month's playtime from lifetime totals.

    The month's starting total is the last total we saw, but never earlier than "now minus the
    last two weeks" so that a first sync, or one after months away, doesn't credit old playtime
    to this month.
    """
    if row is not None:
        row.end_minutes = game.playtime_minutes
        session.add(row)
        return
    start = game.playtime_minutes - game.playtime_2weeks
    if previous_total is not None:
        start = max(start, previous_total)
    if game.playtime_minutes > start:
        session.add(
            MonthlyPlaytime(
                user_id=user.id, work_id=work_id, month=month, start_minutes=start, end_minutes=game.playtime_minutes
            )
        )


@dataclass
class SyncResult:
    added: int
    updated: int


async def sync_steam(session: Session, user: User) -> SyncResult | None:
    """Import played Steam games. New ones await review; known ones only get playtime updates.

    Returns None if the user's Steam game details are private. Raises steam.SteamError on API failure.
    """
    assert user.steam_id
    games = await steam.get_owned_games(user.steam_id)
    if games is None:
        return None

    existing = {
        work.external_id: entry
        for entry, work in session.exec(
            select(CollectionEntry, Work)
            .join(Work, col(Work.id) == CollectionEntry.work_id)
            .where(CollectionEntry.user_id == user.id, Work.source == "steam")
        ).all()
    }

    month = datetime.now(TAIPEI).strftime("%Y-%m")
    this_month = {
        row.work_id: row
        for row in session.exec(
            select(MonthlyPlaytime).where(MonthlyPlaytime.user_id == user.id, MonthlyPlaytime.month == month)
        )
    }

    added = updated = 0
    for game in games:
        if game.playtime_minutes < MIN_PLAYTIME_MINUTES:
            continue
        entry = existing.get(str(game.appid))
        previous_total = entry.playtime_minutes if entry is not None else None
        if entry is not None:
            if entry.playtime_minutes != game.playtime_minutes:
                gained = game.playtime_minutes - (entry.playtime_minutes or 0)
                if gained > 0 and not entry.pending_review:
                    record(session, user.id, ActivityKind.played, entry.work_id, minutes=gained)
                entry.playtime_minutes = game.playtime_minutes
                session.add(entry)
                updated += 1
            work_id = entry.work_id
        else:
            work = upsert_work(
                session,
                category=Category.game,
                source="steam",
                external_id=str(game.appid),
                title=game.name,
                cover_url=game.cover_url,
            )
            session.add(
                CollectionEntry(
                    user_id=user.id,
                    work_id=work.id,
                    playtime_minutes=game.playtime_minutes,
                    pending_review=True,
                )
            )
            work_id = work.id
            added += 1
        _record_playtime(session, user, work_id, month, this_month.get(work_id), previous_total, game)
    session.commit()
    return SyncResult(added=added, updated=updated)


def _month_start(dt: datetime, months_back: int = 0) -> datetime:
    """First instant of the month (Taiwan time) containing dt, shifted back N months."""
    local = dt.astimezone(TAIPEI)
    index = local.year * 12 + local.month - 1 - months_back
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=TAIPEI)


@dataclass
class LastfmSyncResult:
    imported: ImportResult
    truncated: bool  # history was longer than one sync fetches; oldest month may be incomplete


async def sync_lastfm(session: Session, user: User) -> LastfmSyncResult:
    """Import Last.fm scrobbles. Re-fetches whole months from the month of the previous sync,
    so stored monthly counts stay complete. Raises lastfm.LastfmPrivate / lastfm.LastfmError.
    """
    assert user.lastfm_username
    now = datetime.now(timezone.utc)
    if user.lastfm_synced_at:
        last = user.lastfm_synced_at
        since = _month_start(last if last.tzinfo else last.replace(tzinfo=timezone.utc))
    else:
        since = _month_start(now, LASTFM_FIRST_SYNC_MONTHS - 1)

    scrobbles = await lastfm.get_scrobbles(user.lastfm_username, since)
    songs = {key: Song(key, title, artist, cover) for key, (title, artist, cover) in scrobbles.songs.items()}
    result = import_music(session, user, LASTFM, songs, scrobbles.plays)
    user.lastfm_synced_at = now
    session.add(user)
    session.commit()
    return LastfmSyncResult(imported=result, truncated=scrobbles.truncated)
