"""Music imports (YouTube Takeout, Last.fm) and ranking helpers."""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import delete
from sqlmodel import Session, col, func, select

from app.importers.youtube import Track, WatchHistory
from app.models import Category, CollectionEntry, MonthlyPlays, User, Work

YOUTUBE = "youtube"
LASTFM = "lastfm"


@dataclass
class Song:
    external_id: str  # unique within its source
    title: str
    artist: str
    cover_url: str | None


@dataclass
class ImportResult:
    new_songs: int
    songs_with_plays: int
    total_plays: int


def import_music(
    session: Session,
    user: User,
    source: str,
    songs: dict[str, Song],
    plays: Counter[tuple[str, str]],
) -> ImportResult:
    """Merge songs and (external_id, "YYYY-MM") play counts from one source into the collection.

    New songs await review. For each month the stored count becomes max(old, new): every import
    must therefore contain complete counts for the months it covers, and re-importing overlapping
    data never double-counts.
    """
    works: dict[str, Work] = {}
    ids = list(songs)
    for i in range(0, len(ids), 500):
        for work in session.exec(select(Work).where(Work.source == source, col(Work.external_id).in_(ids[i : i + 500]))):
            works[work.external_id] = work
    for external_id, song in songs.items():
        if external_id in works:
            # Works are shared between users and this metadata may come from an uploaded file,
            # so never let one user's import rename an existing song for everyone else.
            continue
        works[external_id] = Work(
            category=Category.music,
            source=source,
            external_id=external_id,
            title=song.title,
            creator=song.artist or None,
            cover_url=song.cover_url,
        )
        session.add(works[external_id])
    session.flush()

    entries: dict[int, CollectionEntry] = {
        entry.work_id: entry
        for entry in session.exec(
            select(CollectionEntry)
            .join(Work, col(Work.id) == CollectionEntry.work_id)
            .where(CollectionEntry.user_id == user.id, Work.source == source)
        )
    }
    new_songs = 0
    for work in works.values():
        if work.id not in entries:
            entries[work.id] = CollectionEntry(user_id=user.id, work_id=work.id, pending_review=True)
            session.add(entries[work.id])
            new_songs += 1

    if plays:
        existing = {
            (row.work_id, row.month): row
            for row in session.exec(select(MonthlyPlays).where(MonthlyPlays.user_id == user.id))
        }
        for (external_id, month), count in plays.items():
            work_id = works[external_id].id
            row = existing.get((work_id, month))
            if row is None:
                session.add(MonthlyPlays(user_id=user.id, work_id=work_id, month=month, plays=count))
            elif count > row.plays:
                row.plays = count
                session.add(row)
        session.flush()

    totals: dict[int, int] = dict(
        session.exec(
            select(MonthlyPlays.work_id, func.sum(MonthlyPlays.plays))
            .join(Work, col(Work.id) == MonthlyPlays.work_id)
            .where(MonthlyPlays.user_id == user.id, Work.source == source)
            .group_by(MonthlyPlays.work_id)
        ).all()
    )
    for work_id, entry in entries.items():
        if entry.play_count != totals.get(work_id):
            entry.play_count = totals.get(work_id)
            session.add(entry)
    session.commit()
    return ImportResult(new_songs=new_songs, songs_with_plays=len(totals), total_plays=sum(totals.values()))


def import_youtube(session: Session, user: User, history: WatchHistory | None, library: list[Track]) -> ImportResult:
    tracks: dict[str, Track] = dict(history.tracks) if history else {}
    for track in library:  # library metadata (proper title + artist) beats watch-history titles
        tracks[track.video_id] = track
    songs = {vid: Song(vid, t.title, t.artist, t.cover_url) for vid, t in tracks.items()}
    return import_music(session, user, YOUTUBE, songs, history.plays if history else Counter())


def clear_source(session: Session, user: User, source: str) -> int:
    """Delete the user's songs and play counts imported from one source."""
    work_ids = select(Work.id).where(Work.source == source)
    session.execute(
        delete(MonthlyPlays).where(col(MonthlyPlays.user_id) == user.id, col(MonthlyPlays.work_id).in_(work_ids))
    )
    entries = session.exec(
        select(CollectionEntry)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(CollectionEntry.user_id == user.id, Work.source == source)
    ).all()
    for entry in entries:
        session.delete(entry)
    session.commit()
    return len(entries)


def _song_key(work: Work) -> tuple[str, str]:
    return ((work.creator or "").casefold().strip(), work.title.casefold().strip())


def dedupe_songs(rows: list[tuple[CollectionEntry, Work]]) -> list[tuple[CollectionEntry, Work]]:
    """Collapse the same song imported from several sources (e.g. YouTube Music also scrobbled
    to Last.fm), keeping the copy with the most plays rather than adding them up."""
    best: dict[tuple[str, str], tuple[CollectionEntry, Work]] = {}
    for entry, work in rows:
        key = _song_key(work)
        if key not in best or (entry.play_count or 0) > (best[key][0].play_count or 0):
            best[key] = (entry, work)
    return list(best.values())


@dataclass
class ArtistStat:
    key: str  # casefolded name, used to group spelling variants
    name: str
    plays: int
    songs: int
    cover_url: str | None  # cover of their most-played song


def top_artists(rows: list[tuple[CollectionEntry, Work]], limit: int) -> list[ArtistStat]:
    groups: dict[str, dict] = {}
    for entry, work in dedupe_songs(rows):
        if not work.creator:
            continue
        g = groups.setdefault(work.creator.casefold(), {"names": Counter(), "plays": 0, "songs": 0, "best": (-1, None)})
        plays = entry.play_count or 0
        g["names"][work.creator] += 1
        g["plays"] += plays
        g["songs"] += 1
        if plays > g["best"][0]:
            g["best"] = (plays, work.cover_url)
    stats = [
        ArtistStat(key=key, name=g["names"].most_common(1)[0][0], plays=g["plays"], songs=g["songs"], cover_url=g["best"][1])
        for key, g in groups.items()
    ]
    stats.sort(key=lambda s: (s.plays, s.songs), reverse=True)
    return stats[:limit]


def top_songs(rows: list[tuple[CollectionEntry, Work]], limit: int) -> list[tuple[CollectionEntry, Work]]:
    return sorted(dedupe_songs(rows), key=lambda r: (r[0].play_count or 0, r[0].added_at), reverse=True)[:limit]
