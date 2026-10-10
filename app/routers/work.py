from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlmodel import col, select

from app.anime import status_rank, tier_rank
from app.auth import CurrentUser, is_locked
from app.db import SessionDep
from app.models import Category, CollectionEntry, MonthlyPlays, MonthlyPlaytime, User, Work
from app.privacy import can_view, get_privacy
from app.social import Relation, relation
from app.templating import render
from app.workinfo import get_work_info

router = APIRouter()

HISTORY_MONTHS = 12
# Backdrop tint when the source gives no color of its own.
CATEGORY_COLORS = {
    Category.game: "#3b82f6", Category.anime: "#ec4899", Category.music: "#10b981",
    Category.film: "#f97316", Category.book: "#8b5cf6",
}


def ordered(rows: list[tuple[CollectionEntry, Work]], category: Category) -> list[tuple[CollectionEntry, Work]]:
    """Same order as the profile lists, so the arrows walk through them predictably."""
    if category == Category.game:
        key = lambda r: (r[0].playtime_minutes or 0, r[0].added_at)  # noqa: E731
    elif category == Category.music:
        key = lambda r: (r[0].play_count or 0, r[0].added_at)  # noqa: E731
    elif category == Category.book:
        key = lambda r: (status_rank(r[0].status), tier_rank(r[0].tier), r[0].added_at)  # noqa: E731
    else:
        key = lambda r: (tier_rank(r[0].tier), r[0].added_at)  # noqa: E731
    return sorted(rows, key=key, reverse=True)


@router.get("/u/{username}/w/{work_id}", response_class=HTMLResponse)
async def work_page(request: Request, username: str, work_id: int, session: SessionDep, me: CurrentUser):
    owner = session.exec(select(User).where(User.username == username.lower())).first()
    work = session.get(Work, work_id)
    rel = relation(session, me, owner) if owner else None
    is_owner = rel == Relation.self
    if (
        owner is None
        or work is None
        or rel == Relation.blocked
        or is_locked(owner)
        or not can_view(get_privacy(session, owner.id)[work.category], owner, me, is_friend=rel == Relation.friends)
    ):
        return render(request, "not_found.html", status_code=404, me=me)

    query = (
        select(CollectionEntry, Work)
        .join(Work, col(Work.id) == CollectionEntry.work_id)
        .where(
            CollectionEntry.user_id == owner.id,
            Work.category == work.category,
            col(CollectionEntry.pending_review).is_(False),
        )
    )
    if not is_owner:
        query = query.where(col(CollectionEntry.hidden).is_(False))
    rows = ordered(list(session.exec(query).all()), work.category)
    index = next((i for i, (_, w) in enumerate(rows) if w.id == work.id), None)
    if index is None:
        return render(request, "not_found.html", status_code=404, me=me)
    entry = rows[index][0]

    history: list[tuple[str, int]] = []
    if work.category == Category.game:
        history = [
            (m, end - start)
            for m, start, end in session.exec(
                select(MonthlyPlaytime.month, MonthlyPlaytime.start_minutes, MonthlyPlaytime.end_minutes)
                .where(MonthlyPlaytime.user_id == owner.id, MonthlyPlaytime.work_id == work.id)
            ).all()
            if end > start
        ]
    elif work.category in (Category.music, Category.film, Category.anime):  # film/anime: Netflix views per month
        history = list(
            session.exec(
                select(MonthlyPlays.month, MonthlyPlays.plays)
                .where(MonthlyPlays.user_id == owner.id, MonthlyPlays.work_id == work.id)
            ).all()
        )
    history = sorted(history, reverse=True)[:HISTORY_MONTHS]

    info = await get_work_info(work)
    base = f"/u/{owner.username}/w/"
    return render(
        request,
        "work.html",
        me=me,
        owner=owner,
        is_owner=is_owner,
        work=work,
        entry=entry,
        rank=index + 1,
        total=len(rows),
        prev_href=base + str(rows[index - 1][1].id) if index > 0 else None,
        next_href=base + str(rows[index + 1][1].id) if index + 1 < len(rows) else None,
        history=history,
        history_max=max((v for _, v in history), default=0),
        info=info,
        color=info.color or CATEGORY_COLORS[work.category],
        cover=info.image or work.cover_url,
        back_href=f"/u/{owner.username}#{work.category.value}",
    )
