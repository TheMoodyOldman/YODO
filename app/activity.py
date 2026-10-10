"""Write feed activities. Entries are merged per user/kind/work/day so a sync, an import or a
burst of verdict taps produces one feed item, not dozens. Callers commit."""

from datetime import datetime

from sqlmodel import Session, select

from app.importers.youtube import TAIPEI
from app.models import Activity, ActivityKind, utcnow


def today() -> str:
    return datetime.now(TAIPEI).strftime("%Y-%m-%d")


def record(
    session: Session,
    user_id: int,
    kind: ActivityKind,
    work_id: int | None,
    *,
    minutes: int = 0,
    plays: int = 0,
    songs: int = 0,
) -> Activity:
    day = today()
    query = select(Activity).where(Activity.user_id == user_id, Activity.kind == kind, Activity.day == day)
    if kind != ActivityKind.listened:  # listening is one item per day; work_id is just its top song
        query = query.where(Activity.work_id == work_id)
    act = session.exec(query).first()
    if act is None:
        act = Activity(user_id=user_id, kind=kind, work_id=work_id, day=day)
    if minutes:
        act.minutes = (act.minutes or 0) + minutes
    if plays:
        act.plays = (act.plays or 0) + plays
    if songs:
        act.songs = max(act.songs or 0, songs)
    if kind == ActivityKind.listened and work_id is not None:
        act.work_id = work_id
    act.updated_at = utcnow()
    session.add(act)
    return act


def has_today(session: Session, user_id: int, kind: ActivityKind, work_id: int) -> Activity | None:
    return session.exec(
        select(Activity).where(
            Activity.user_id == user_id, Activity.kind == kind, Activity.work_id == work_id, Activity.day == today()
        )
    ).first()
